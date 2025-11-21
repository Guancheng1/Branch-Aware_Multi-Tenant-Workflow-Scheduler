# 🔧 Branch隔离修复文档

## 🐛 问题描述

### 发现的Bug
在原始实现中，branch队列是**全局共享**的，不同用户如果使用相同的branch名称，会被放入同一个队列并串行执行。

**问题示例：**
```
User 1 创建任务 -> branch: "main"
User 2 创建任务 -> branch: "main"

❌ 错误行为：两个任务被放入同一个 "main" 队列，串行执行
✅ 期望行为：两个用户的任务应该并行执行（不同用户的branch应该独立）
```

### 代码问题
```python
# ❌ 原始实现（错误）
self.branch_queues: Dict[str, deque] = defaultdict(deque)
self.branch_running: Dict[str, Optional[str]] = {}

# 提交任务时
self.branch_queues[job.branch].append(job_id)  # 只用 branch 作为key
```

这导致：
- `branch_queues["main"]` 包含所有用户的 "main" branch任务
- 不同用户的同名branch任务会串行化
- **违反多租户隔离原则** 🚨

## ✅ 解决方案

### 核心改进
将branch的key从 `branch_name` 改为 `(user_id, branch_name)` 元组，确保**用户级别的branch隔离**。

```python
# ✅ 修复后的实现（正确）
self.branch_queues: Dict[tuple, deque] = defaultdict(deque)
self.branch_running: Dict[tuple, Optional[str]] = {}

# 提交任务时
branch_key = (job.user_id, job.branch)  # 使用 (user_id, branch) 元组
self.branch_queues[branch_key].append(job_id)
```

### 修改的文件
📁 `backend/core/scheduler.py`

### 修改的方法

#### 1. `__init__` - 数据结构定义
```python
# 修改前
self.branch_queues: Dict[str, deque] = defaultdict(deque)
self.branch_running: Dict[str, Optional[str]] = {}

# 修改后
self.branch_queues: Dict[tuple, deque] = defaultdict(deque)  # key: (user_id, branch)
self.branch_running: Dict[tuple, Optional[str]] = {}          # key: (user_id, branch)
```

#### 2. `submit_job` - 任务提交
```python
# 修改前
self.branch_queues[job.branch].append(job_id)

# 修改后
branch_key = (job.user_id, job.branch)
self.branch_queues[branch_key].append(job_id)
```

#### 3. `cancel_job` - 任务取消
```python
# 修改前
self.branch_queues[job.branch].remove(job_id)

# 修改后
branch_key = (job.user_id, job.branch)
self.branch_queues[branch_key].remove(job_id)
```

#### 4. `_schedule_next_jobs` - 任务调度
```python
# 修改前
for branch, queue in list(self.branch_queues.items()):
    if self.branch_running.get(branch):
        continue

# 修改后
for branch_key, queue in list(self.branch_queues.items()):
    user_id, branch_name = branch_key
    if self.branch_running.get(branch_key):
        continue
```

#### 5. `_execute_job` - 任务执行
```python
# 修改前
self.branch_running[job.branch] = job.job_id

# 修改后
branch_key = (job.user_id, job.branch)
self.branch_running[branch_key] = job.job_id
```

#### 6. `_run_job_with_semaphore` - 清理
```python
# 修改前
if self.branch_running.get(job.branch) == job.job_id:
    self.branch_running[job.branch] = None

# 修改后
branch_key = (job.user_id, job.branch)
if self.branch_running.get(branch_key) == job.job_id:
    self.branch_running[branch_key] = None
```

#### 7. `get_system_stats` - 统计信息
```python
# 修改前
per_branch_depth = {
    branch: len(queue)
    for branch, queue in self.branch_queues.items()
    if queue
}

# 修改后
per_branch_depth = {
    f"{user_id}:{branch}": len(queue)
    for (user_id, branch), queue in self.branch_queues.items()
    if queue
}
```

## 🎯 修复效果

### 修复前
```
User 1 -> "main" branch -> Task A ─┐
                                   ├─> 串行执行（错误！）
User 2 -> "main" branch -> Task B ─┘
```

### 修复后
```
User 1 -> "main" branch -> Task A ─> 并行执行 ✅
                                     
User 2 -> "main" branch -> Task B ─> 并行执行 ✅
```

### 行为对比表

| 场景 | 修复前 | 修复后 |
|------|--------|--------|
| User1 "main" + User2 "main" | ❌ 串行 | ✅ 并行 |
| User1 "main" + User1 "main" | ✅ 串行 | ✅ 串行 |
| User1 "main" + User1 "dev" | ✅ 并行 | ✅ 并行 |
| User1 "main" + User2 "dev" | ✅ 并行 | ✅ 并行 |

## 🧪 测试验证

### 运行测试
```bash
python test_multi_tenant_branch_isolation.py
```

### 测试场景

#### 场景1: 不同用户同名branch（关键测试）
```python
User 1 -> "main" branch -> Task A
User 2 -> "main" branch -> Task B

预期结果: 两个任务几乎同时开始执行（并行）
```

#### 场景2: 同用户不同branch
```python
User 1 -> "branch-a" -> Task A
User 1 -> "branch-b" -> Task B

预期结果: 两个任务并行执行
```

#### 场景3: 同用户同branch
```python
User 1 -> "main" -> Task A
User 1 -> "main" -> Task B

预期结果: Task B 等待 Task A 完成后执行（串行）
```

### 验证指标
- ✅ 不同用户的同名branch任务启动时间差 < 3秒（并行）
- ✅ 同用户同branch任务启动时间差 > 5秒（串行）
- ✅ 统计信息正确显示 `user_id:branch` 格式

## 📊 统计信息变化

### API响应变化

#### 修复前
```json
{
  "per_branch_queue_depth": {
    "main": 5,      // 所有用户的 "main" 混在一起
    "dev": 3
  }
}
```

#### 修复后
```json
{
  "per_branch_queue_depth": {
    "user-001:main": 2,  // 用户级别的branch统计
    "user-002:main": 3,
    "user-001:dev": 1
  }
}
```

### 前端显示
统计页面的 "Per-Branch Queue Depth" 现在会显示：
```
user-001:main  ████████  2
user-002:main  ████████████  3
user-001:dev   ████  1
```

## 🔒 多租户隔离增强

这个修复强化了系统的多租户隔离：

### 隔离级别

| 资源 | 隔离级别 | 说明 |
|------|----------|------|
| 任务 (Jobs) | ✅ 用户隔离 | 每个用户只能看到自己的任务 |
| Branch队列 | ✅ 用户隔离 | 每个用户的branch独立管理 |
| Workflow | ✅ 用户隔离 | 每个用户只能操作自己的workflow |
| Worker资源 | ⚠️ 共享 | 全局worker池，受MAX_WORKERS限制 |
| 活跃用户槽 | ⚠️ 共享 | 最多3个活跃用户，受MAX_ACTIVE_USERS限制 |

### 安全性
- ✅ 用户A的branch不会影响用户B的branch
- ✅ 防止用户间的资源竞争导致的不公平调度
- ✅ 符合多租户SaaS应用的标准实践

## 🎓 最佳实践

### 1. Branch命名建议
虽然现在branch是用户隔离的，但仍建议使用有意义的名称：
```
✅ 好的命名: "preprocessing", "analysis", "visualization"
❌ 避免: "branch1", "temp", "test"
```

### 2. 资源分配
不同用户的branch现在可以并行，但要注意：
- Worker总数受 `MAX_WORKERS` 限制
- 每个用户的不同branch之间可以并行
- 合理规划branch以最大化并行度

### 3. 监控建议
- 查看 `per_branch_queue_depth` 了解每个用户的每个branch的负载
- 如果某个 `user_id:branch` 队列深度持续很高，可能需要优化

## 🔄 向后兼容性

✅ **完全向后兼容**

- API接口无变化
- 前端无需修改（统计显示略有不同，但格式兼容）
- 现有任务会自动使用新的隔离机制
- 无需数据迁移

## 📝 相关Issue

这个修复解决了多租户环境下的关键隔离问题，符合原始需求：

> "Multi-Tenant Isolation & Active-User Limit" - 每个租户应该独立管理自己的资源

## 🙏 致谢

感谢用户及时发现这个重要的多租户隔离bug！这个修复确保了系统在生产环境中的公平性和可靠性。

---

**修复日期**: 2025-01-21  
**影响范围**: Backend调度器核心逻辑  
**测试状态**: ✅ 已验证  
**部署建议**: 可以安全部署到生产环境

