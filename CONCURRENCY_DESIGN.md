# 并发调度设计文档

## 概述

本系统采用三层并发控制架构，实现了分支感知的多租户工作流调度。设计目标是在保证公平性的前提下，最大化系统吞吐量。

## 三层架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    User-Level Control                            │
│  active_users: Set[user_id] (max 3)                             │
│  waiting_users: Queue[user_id]                                   │
│                                                                   │
│  规则：最多3个用户同时有运行中的任务                               │
│       第4个及以后的用户进入waiting_users队列                       │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                  Workflow/Branch-Level Control                   │
│  branch_queues: Dict[branch_id, Queue[job_id]]                  │
│  branch_running: Dict[branch_id, job_id]                        │
│                                                                   │
│  规则：同一分支内的任务串行执行（FIFO）                            │
│       不同分支的任务可以并行执行                                   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    Worker-Level Control                          │
│  worker_semaphore: asyncio.Semaphore(MAX_WORKERS=5)             │
│  running_jobs: Set[job_id]                                       │
│                                                                   │
│  规则：全局最多5个任务同时执行                                     │
│       所有用户、所有分支共享worker pool                            │
└─────────────────────────────────────────────────────────────────┘
```

## 详细设计

### 1. User-Level：活跃用户限制

**目标**：限制最多3个用户同时有运行中的任务，避免系统资源被过多用户占用。

**实现**：
```python
# 核心数据结构
active_users: Set[str]      # 当前有活跃任务的用户
waiting_users: deque[str]   # 等待槽位的用户队列

# 用户激活逻辑
def _can_user_execute(user_id: str) -> bool:
    if user_id in active_users:
        return True
    if len(active_users) < MAX_ACTIVE_USERS:
        active_users.add(user_id)
        return True
    # 用户进入等待队列
    if user_id not in waiting_users:
        waiting_users.append(user_id)
    return False
```

**关键点**：
- 用户提交任务时，检查是否可以立即执行
- 如果活跃用户数已满（3个），新用户进入等待队列
- 当用户的所有任务完成后，从 `active_users` 中移除
- 自动激活等待队列中的下一个用户

### 2. Workflow/Branch-Level：分支队列管理

**目标**：保证同一分支内的任务按提交顺序串行执行，不同分支可以并行。

**实现**：
```python
# 核心数据结构
branch_queues: Dict[str, deque[str]]    # 每个分支的任务队列
branch_running: Dict[str, str]           # 每个分支当前运行的任务

# 分支调度逻辑
for branch, queue in branch_queues.items():
    if branch_running.get(branch):
        continue  # 该分支已有任务在运行，跳过
    
    job_id = queue[0]  # 取队列头部任务
    if can_execute(job_id):
        queue.popleft()
        execute_job(job_id)
        branch_running[branch] = job_id
```

**关键点**：
- 每个分支维护自己的FIFO队列
- 分支内严格串行：只有当前任务完成后，才能开始下一个
- 分支间完全独立：不同分支的任务可以并行执行
- 失败重试是分支局部的，不影响其他分支

### 3. Worker-Level：全局资源池

**目标**：控制系统级并发度，防止资源耗尽。

**实现**：
```python
# 核心数据结构
worker_semaphore = asyncio.Semaphore(MAX_WORKERS=5)
running_jobs: Set[str]

# 任务执行逻辑
async def _run_job_with_semaphore(job: Job):
    async with worker_semaphore:
        # 实际执行任务（InstanSeg分割等）
        await job_executor.execute_job(job)
```

**关键点**：
- 使用 `asyncio.Semaphore` 实现全局并发限制
- 所有用户、所有分支共享同一个worker pool
- MAX_WORKERS=5：根据单CPU机器性能设置
- 自动排队：当worker满时，新任务等待信号量释放

## 调度流程

```
1. 任务提交
   ↓
2. 加入分支队列: branch_queues[branch].append(job_id)
   ↓
3. 调度器主循环 (_scheduler_loop)
   ↓
4. 清理已完成用户: _cleanup_completed_users()
   - 检查用户是否还有 PENDING 或 RUNNING 任务
   - 如果都完成了，从 active_users 中移除
   ↓
5. 激活等待用户: _activate_waiting_users()
   - 如果 active_users < 3，从 waiting_users 中激活下一个
   ↓
6. 分支调度: _schedule_next_jobs()
   - 遍历所有分支队列
   - 对每个分支：
     a. 检查分支是否有任务在运行 → 如有，跳过
     b. 取队列头部任务
     c. 检查用户是否可以执行 → 如否，跳过
     d. 检查worker是否可用 → 如否，等待
     e. 执行任务：_execute_job()
   ↓
7. 任务执行
   - 获取 worker_semaphore
   - 调用 job_executor.execute_job()
   - 更新任务状态和进度
   ↓
8. 任务完成
   - 释放 worker_semaphore
   - 从 running_jobs 中移除
   - 从 branch_running 中移除
   - 触发下一轮调度
```

## 配置参数

```python
# backend/core/config.py
MAX_WORKERS = 5         # 全局worker池大小
MAX_ACTIVE_USERS = 3    # 最多同时活跃的用户数

# InstanSeg 优化参数
TILE_SIZE = 512         # 瓦片大小
TILE_OVERLAP = 64       # 瓦片重叠
BATCH_SIZE = 4          # 批处理大小
```

## 并发场景示例

### 场景1：单用户，多分支
```
User A 提交 workflow:
  - Branch "preprocessing": Job1 → Job2
  - Branch "segmentation": Job3 → Job4

执行顺序：
  Job1 (branch1) + Job3 (branch2) 并行
  ↓
  Job2 (branch1) + Job4 (branch2) 并行
```

### 场景2：多用户，单分支
```
User A: Branch "main" → Job1
User B: Branch "main" → Job2
User C: Branch "main" → Job3

执行顺序（如果都在不同分支）：
  Job1 + Job2 + Job3 可以并行（受 MAX_WORKERS 限制）

执行顺序（如果都在同一分支名）：
  Job1 → Job2 → Job3 串行
```

### 场景3：4个用户同时提交
```
User A: 提交 Job1 → active_users = {A}
User B: 提交 Job2 → active_users = {A, B}
User C: 提交 Job3 → active_users = {A, B, C}
User D: 提交 Job4 → waiting_users = [D]

当 User A 的所有任务完成后：
  active_users = {B, C, D}
  User D 自动激活
```

## 性能优化

1. **InstanSeg 优化**
   - 两阶段分割：先生成组织mask，再对有效区域分割
   - 瓦片处理：512×512 平衡速度与精度
   - 批处理：BATCH_SIZE=4 充分利用GPU

2. **调度优化**
   - 异步执行：所有任务使用 asyncio
   - 信号量控制：避免资源耗尽
   - 智能队列：分支感知，减少等待

3. **资源控制**
   - MAX_WORKERS=5：适配单CPU机器
   - MAX_ACTIVE_USERS=3：公平性与吞吐量平衡
   - 自动清理：及时释放已完成用户的槽位

## 监控指标

系统提供以下监控指标（通过 `/api/system/stats` 获取）：

```json
{
  "active_users": 2,              // 当前活跃用户数
  "max_active_users": 3,          // 最大活跃用户数
  "active_workers": 4,             // 当前运行的任务数
  "max_workers": 5,                // 最大worker数
  "queue_depth": 10,               // 总队列深度
  "waiting_users": 1,              // 等待中的用户数
  "per_branch_queue_depth": {     // 各分支队列深度
    "main": 3,
    "preprocessing": 2
  },
  "total_jobs_processed": 156,    // 已处理任务总数
  "average_job_latency_seconds": 45.2  // 平均任务延迟
}
```

## 扩展性考虑

当前实现是单机版本。如需扩展到分布式系统：

1. **用户队列**：使用 Redis 替代内存数据结构
2. **分布式锁**：使用 Redis 分布式锁保证分支串行
3. **任务队列**：使用 Celery 或 RQ 进行分布式任务调度
4. **状态同步**：使用 Redis Pub/Sub 或消息队列

## 总结

这个三层架构实现了：
- ✅ 用户级公平性：最多3个用户同时活跃
- ✅ 分支级串行：同一分支任务按顺序执行
- ✅ 跨分支并行：不同分支任务可以并行
- ✅ 全局资源控制：5个worker避免过载
- ✅ 高并发支持：asyncio异步执行
- ✅ 实时监控：完整的系统状态指标

