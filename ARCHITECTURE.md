# 架构设计文档

## 系统概览

本系统是一个为大规模图像处理设计的分支感知多租户工作流调度器。核心设计理念是：

1. **分支感知调度**：同一分支串行，不同分支并行
2. **多租户隔离**：用户级别的资源隔离和公平性
3. **高并发处理**：支持高QPS场景
4. **实时反馈**：WebSocket实时进度更新

## 核心组件

### 1. BranchAwareScheduler（分支感知调度器）

**职责**：
- 管理所有任务的调度
- 实现分支级别的FIFO队列
- 控制全局worker并发数
- 管理用户级别的并发限制

**关键设计**：

```python
class BranchAwareScheduler:
    # 分支队列：每个分支一个FIFO队列
    branch_queues: Dict[str, deque]
    
    # 分支运行状态：每个分支最多一个运行中的任务
    branch_running: Dict[str, Optional[str]]
    
    # 用户管理
    active_users: Set[str]  # 最多3个
    waiting_users: deque     # FIFO等待队列
    
    # 全局worker控制
    worker_semaphore: asyncio.Semaphore  # 限制并发数
```

**调度算法**：

1. 清理已完成用户（没有运行中任务的用户）
2. 激活等待队列中的用户（直到active_users达到3个）
3. 对每个分支：
   - 如果该分支有运行中的任务，跳过
   - 获取队列头部任务
   - 检查用户是否在active_users中
   - 检查全局worker是否有空闲
   - 满足条件则执行任务

**时间复杂度**：O(B + J)，其中B是分支数，J是任务数

### 2. WorkflowManager（工作流管理器）

**职责**：
- 验证DAG的有效性（无环检测）
- 拓扑排序节点
- 管理节点间依赖关系
- 追踪工作流整体进度

**DAG执行流程**：

```
1. 验证DAG（检测环）
2. 识别可执行节点（依赖已满足）
3. 为每个可执行节点创建任务
4. 提交任务到调度器
5. 等待任务完成
6. 更新完成节点集合
7. 重复步骤2-6直到所有节点完成
```

**环检测算法**：使用DFS + 递归栈

### 3. JobExecutor（任务执行器）

**职责**：
- 执行具体的图像处理任务
- 调用InstanSeg服务
- 管理任务生命周期
- 报告进度更新

**任务类型**：

1. **Cell Segmentation（细胞分割）**
   - 瓦片化大图像
   - 批处理瓦片
   - 合并结果
   - 去重处理

2. **Tissue Mask（组织掩码）**
   - Otsu阈值
   - 形态学操作
   - 生成掩码

### 4. InstanSegService（InstanSeg服务）

**职责**：
- 加载和管理InstanSeg模型
- 处理大图像（支持WSI格式）
- 瓦片化处理
- 结果合并和去重

**瓦片处理流程**：

```
1. 加载图像（OpenSlide或OpenCV）
2. 计算瓦片坐标
   - tile_size: 瓦片大小（如1024x1024）
   - overlap: 重叠区域（如128像素）
   - stride = tile_size - overlap
3. 对每个瓦片：
   - 提取瓦片图像
   - InstanSeg推理
   - 调整坐标偏移
4. 合并结果：
   - 基于中心点距离去重
   - 阈值 = overlap / 2
5. 保存结果（JSON + 可视化）
```

**性能优化**：

- 批处理：同时处理多个瓦片
- GPU加速：使用CUDA
- 异步I/O：避免阻塞
- 流式处理：不将整个图像加载到内存

## 数据流

### 任务创建流程

```
用户请求
  ↓
FastAPI端点（验证X-User-ID）
  ↓
创建Job对象
  ↓
提交到Scheduler
  ↓
加入branch_queue
  ↓
调度器主循环检测
  ↓
满足条件时执行
  ↓
JobExecutor处理
  ↓
更新状态和进度
  ↓
WebSocket广播更新
```

### 工作流执行流程

```
用户创建Workflow
  ↓
WorkflowManager验证DAG
  ↓
启动执行协程
  ↓
拓扑排序节点
  ↓
识别可执行节点
  ↓
为节点创建Job
  ↓
提交到Scheduler
  ↓
等待Job完成
  ↓
更新依赖关系
  ↓
继续下一批节点
```

## 并发控制

### 1. 全局Worker限制

使用 `asyncio.Semaphore` 控制最大并发数：

```python
worker_semaphore = asyncio.Semaphore(MAX_WORKERS)

async with worker_semaphore:
    # 执行任务
    await execute_job(job)
```

### 2. 分支级别串行

每个分支维护一个运行状态：

```python
if branch_running[branch] is not None:
    # 该分支已有任务在运行，跳过
    continue
```

### 3. 用户级别限制

使用集合和队列管理活跃用户：

```python
if len(active_users) >= MAX_ACTIVE_USERS:
    if user_id not in waiting_users:
        waiting_users.append(user_id)
    return False  # 用户需要等待
```

## 实时更新机制

### WebSocket连接管理

```python
class ConnectionManager:
    # 用户连接
    active_connections: Dict[user_id, Set[WebSocket]]
    
    # 任务订阅
    job_subscriptions: Dict[job_id, Set[WebSocket]]
    
    # 工作流订阅
    workflow_subscriptions: Dict[workflow_id, Set[WebSocket]]
```

### 更新广播流程

1. 客户端连接并订阅
2. 后台任务定期检查更新（1秒间隔）
3. 发现变化时推送JSON消息
4. 客户端接收并更新UI

## 容错机制

### 1. 任务级别

- 任务失败不影响其他任务
- 错误信息记录在Job对象中
- 支持任务取消（仅PENDING状态）

### 2. 分支级别

- 分支间完全隔离
- 一个分支失败不影响其他分支

### 3. 用户级别

- 用户间资源隔离
- 公平调度（FIFO队列）

### 4. 系统级别

- 健康检查端点
- 优雅关闭
- 异常捕获和日志记录

## 扩展性设计

### 水平扩展

当前实现使用内存存储，扩展方案：

1. **引入Redis作为共享存储**
   ```python
   # 使用Redis存储任务状态
   await redis.set(f"job:{job_id}", json.dumps(job))
   
   # 使用Redis队列
   await redis.lpush(f"branch:{branch}", job_id)
   ```

2. **分布式锁**
   ```python
   # 确保同一分支只有一个worker处理
   async with redis_lock(f"branch:{branch}"):
       job_id = await redis.rpop(f"branch:{branch}")
       await process_job(job_id)
   ```

3. **多实例部署**
   - 无状态API服务器（多个实例）
   - 共享Redis队列
   - 独立Worker进程池

### 垂直扩展

1. **GPU加速**
   - 使用CUDA加速推理
   - 批处理优化
   - 模型量化

2. **I/O优化**
   - 并行读写
   - 预取和缓存
   - SSD存储

3. **内存优化**
   - 流式处理
   - 瓦片缓存策略
   - 及时释放

## 监控指标

### 关键指标

1. **吞吐量**
   - jobs_total: 已处理任务总数
   - job_duration_seconds: 任务处理时间

2. **并发性**
   - active_workers: 当前活跃worker数
   - active_users: 当前活跃用户数
   - queue_depth: 队列深度

3. **性能**
   - average_job_latency: 平均任务延迟
   - per_branch_queue_depth: 各分支队列深度

4. **可用性**
   - system_errors_total: 系统错误数
   - health_check: 健康状态

## 安全考虑

### 当前实现

- 基于Header的用户识别
- 用户级别的任务隔离
- 输入验证

### 生产环境需要

1. **身份认证**
   - JWT Token
   - OAuth2
   - API Key

2. **授权**
   - RBAC（基于角色的访问控制）
   - 资源级别权限

3. **速率限制**
   - 用户级别QPS限制
   - IP级别限制
   - 令牌桶算法

4. **数据安全**
   - HTTPS
   - 数据加密
   - 审计日志

## 性能基准

### 预期性能

- **单实例**
  - 8个并发worker
  - 3个活跃用户
  - ~100 jobs/hour（取决于图像大小）

- **扩展后**
  - 3个实例 x 8 workers = 24并发
  - 10+活跃用户
  - ~300 jobs/hour

### 瓶颈分析

1. **CPU密集型**：InstanSeg推理
2. **I/O密集型**：大图像读写
3. **内存密集型**：图像数据

### 优化建议

1. GPU加速推理（3-10倍速提升）
2. SSD存储（2-5倍I/O提升）
3. 结果缓存（避免重复计算）
4. CDN分发结果（加速访问）

## 总结

本系统通过分支感知调度、多租户隔离、实时更新等机制，实现了一个高性能、可扩展的工作流调度系统。核心设计原则：

1. **简单性**：清晰的组件职责
2. **可靠性**：故障隔离和容错
3. **可扩展性**：水平和垂直扩展
4. **可观测性**：完整的监控和日志

未来可以通过引入分布式队列、数据库持久化、GPU加速等方式进一步提升性能和可靠性。


