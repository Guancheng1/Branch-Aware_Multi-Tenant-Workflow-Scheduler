# 分支感知多租户工作流调度器

一个为大规模图像处理（特别是病理学全切片图像WSI）设计的高性能工作流调度系统。

## 🌟 核心特性

### 1. 分支感知调度
- **串行执行**：同一分支内的任务按FIFO顺序串行执行
- **并行执行**：不同分支的任务可以并行执行，受全局worker限制
- **故障隔离**：一个分支的失败不会影响其他分支

### 2. 多租户隔离
- 每个请求通过 `X-User-ID` 头部标识用户
- 最多3个用户可以同时运行任务
- 第4个及之后的用户自动进入等待队列
- 高QPS场景下的速率限制和稳定性保证

### 3. InstanSeg集成
- 使用InstanSeg进行细胞分割
- 支持超大图像（千兆像素级）的瓦片化处理
- 瓦片重叠和混合以避免边界接缝
- 批处理优化以提高吞吐量

### 4. 实时进度跟踪
- WebSocket实时更新
- 任务级和工作流级进度跟踪
- 瓦片处理进度可视化
- 任务状态转换：`PENDING → RUNNING → SUCCEEDED/FAILED`

### 5. 工作流DAG支持
- 定义复杂的任务依赖图
- 自动拓扑排序和执行
- 节点级故障处理
- 并行执行独立分支

### 6. 监控和可观测性
- Prometheus指标导出
- 队列深度、活跃worker、任务延迟等指标
- Grafana仪表板
- 系统健康检查

## 🏗️ 架构设计

```
┌─────────────┐
│   用户请求   │
└──────┬──────┘
       │
       v
┌─────────────────────────────────┐
│      FastAPI + WebSocket        │
│  (API端点、实时更新、文件上传)   │
└──────────┬──────────────────────┘
           │
           v
┌─────────────────────────────────┐
│   BranchAwareScheduler          │
│  - 分支队列管理                  │
│  - 多租户隔离 (最多3个活跃用户)  │
│  - 全局worker池 (信号量控制)    │
└──────────┬──────────────────────┘
           │
           v
┌─────────────────────────────────┐
│      WorkflowManager            │
│  - DAG验证和拓扑排序             │
│  - 依赖关系管理                  │
│  - 工作流级进度跟踪              │
└──────────┬──────────────────────┘
           │
           v
┌─────────────────────────────────┐
│       JobExecutor               │
│  - InstanSeg集成                │
│  - 瓦片化图像处理                │
│  - 进度回调                      │
└──────────┬──────────────────────┘
           │
           v
┌─────────────────────────────────┐
│     InstanSegService            │
│  - 大图像分割                    │
│  - 组织掩码生成                  │
│  - 结果合并和可视化              │
└─────────────────────────────────┘
```

## 📋 任务类型

### 1. 细胞分割 (Cell Segmentation)
- 使用InstanSeg分割图像中的所有细胞
- 支持瓦片化处理大图像
- 输出JSON格式的多边形坐标
- 生成带有分割叠加的可视化图像

### 2. 组织掩码生成 (Tissue Mask)
- 生成二进制组织掩码以跳过背景瓦片
- 使用Otsu阈值和形态学操作
- 输出掩码图像和叠加可视化

## 🚀 快速开始

### 使用Docker Compose（推荐）

```bash
# 克隆仓库
git clone <your-repo-url>
cd Branch-Aware_Multi-Tenant-Workflow-Scheduler

# 启动所有服务
docker-compose up -d

# 查看日志
docker-compose logs -f app

# 停止服务
docker-compose down
```

> **InstanSeg运行提示**  
> 官方Docker镜像会安装 `instanseg-torch[full]` 以及所需的系统库（`libglib2.0-0`、`libgl1`、`libsm6`、`libxrender1`、`libxext6`），以保证真正的InstanSeg模型可以加载。  
> 如果你自行构建镜像或本地安装依赖，请务必安装同样的额外依赖，否则服务会退回到Mock模式。

服务地址：
- **应用主界面**: http://localhost:8000
- **API文档**: http://localhost:8000/docs
- **Prometheus**: http://localhost:9090
- **Grafana**: http://localhost:3000 (admin/admin)

### 本地开发

```bash
# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 启动Redis（使用Docker）
docker run -d -p 6379:6379 redis:7-alpine

# 启动应用
python main.py
```

## 📖 API使用示例

### 1. 创建单个任务

```bash
curl -X POST "http://localhost:8000/api/v1/jobs" \
  -H "X-User-ID: user-001" \
  -H "Content-Type: application/json" \
  -d '{
    "job_type": "cell_segmentation",
    "branch": "main",
    "image_path": "/path/to/image.svs",
    "parameters": {
      "tile_size": 1024,
      "overlap": 128
    }
  }'
```

### 2. 创建工作流（DAG）

```bash
curl -X POST "http://localhost:8000/api/v1/workflows" \
  -H "X-User-ID: user-001" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Complete Analysis Pipeline",
    "description": "Generate tissue mask then segment cells",
    "nodes": [
      {
        "node_id": "node-1",
        "job_type": "tissue_mask",
        "branch": "preprocessing",
        "image_path": "/path/to/image.svs",
        "parameters": {},
        "depends_on": []
      },
      {
        "node_id": "node-2",
        "job_type": "cell_segmentation",
        "branch": "segmentation",
        "image_path": "/path/to/image.svs",
        "parameters": {"tile_size": 1024, "overlap": 128},
        "depends_on": ["node-1"]
      }
    ]
  }'
```

### 3. 查询任务状态

```bash
curl -X GET "http://localhost:8000/api/v1/jobs/{job_id}" \
  -H "X-User-ID: user-001"
```

### 4. 获取系统统计

```bash
curl -X GET "http://localhost:8000/api/v1/stats/system"
```

### 5. WebSocket连接

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/user-001');

ws.onopen = () => {
  // 订阅任务更新
  ws.send(JSON.stringify({
    action: 'subscribe_job',
    job_id: 'your-job-id'
  }));
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Job update:', data);
};
```

## 🎨 前端界面

现代化、美观的Web界面，包含：

- **任务管理**：创建、监控和管理任务
- **工作流管理**：创建和管理DAG工作流
- **实时统计**：活跃用户、worker、队列深度等
- **文件上传**：拖拽上传WSI图像文件
- **实时更新**：通过WebSocket自动更新进度

## 📊 监控指标

### Prometheus指标

- `jobs_total`: 任务总数（按用户、类型、状态）
- `jobs_active`: 活跃任务数（按用户、分支）
- `job_duration_seconds`: 任务执行时长
- `queue_depth`: 队列深度（按分支）
- `active_users`: 活跃用户数
- `waiting_users`: 等待中的用户数
- `active_workers`: 活跃worker数
- `system_errors_total`: 系统错误总数

### Grafana仪表板

访问 http://localhost:3000 查看：
- 任务吞吐量和延迟
- 队列深度趋势
- 用户活动
- 系统资源使用

## 🧪 测试

### 下载测试数据

```bash
# 从CMU OpenSlide下载WSI测试数据
mkdir -p uploads
cd uploads
wget https://openslide.cs.cmu.edu/download/openslide-testdata/Aperio/CMU-1-Small-Region.svs
```

### 运行测试

```python
import requests

# 上传图像
with open('uploads/CMU-1-Small-Region.svs', 'rb') as f:
    files = {'file': f}
    response = requests.post(
        'http://localhost:8000/api/v1/upload',
        headers={'X-User-ID': 'user-001'},
        files=files
    )
    result = response.json()
    image_path = result['path']

# 创建任务
response = requests.post(
    'http://localhost:8000/api/v1/jobs',
    headers={'X-User-ID': 'user-001'},
    json={
        'job_type': 'cell_segmentation',
        'branch': 'main',
        'image_path': image_path,
        'parameters': {'tile_size': 512, 'overlap': 64}
    }
)
job = response.json()
print(f"Job created: {job['job_id']}")
```

## 📈 扩展性设计

### 扩展到10倍的任务/用户量

#### 1. 水平扩展

```yaml
# docker-compose.scale.yml
services:
  app:
    deploy:
      replicas: 3
    
  redis:
    # 使用Redis Cluster
    image: redis:7-cluster
    
  # 添加负载均衡器
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
```

启动：
```bash
docker-compose -f docker-compose.yml -f docker-compose.scale.yml up -d
```

#### 2. 数据库持久化

当前使用内存存储，扩展时应：
- 使用PostgreSQL存储任务和工作流元数据
- 使用Redis仅用于队列和缓存
- 实现数据库连接池

#### 3. 分布式任务队列

- 使用Celery + Redis/RabbitMQ
- 独立的worker进程池
- 动态worker扩展

#### 4. 对象存储

- 使用MinIO或S3存储图像和结果
- CDN加速结果访问
- 实现分片上传

#### 5. 缓存策略

- Redis缓存热点数据
- 任务结果缓存
- 用户会话缓存

#### 6. 监控和告警

- Grafana告警规则
- ELK栈日志聚合
- APM工具（如Datadog）

### 性能优化

1. **GPU加速**
   - 使用CUDA进行InstanSeg推理
   - 批处理优化
   - 模型量化

2. **I/O优化**
   - 异步I/O操作
   - 预取和缓冲
   - 并行读写

3. **内存管理**
   - 大图像流式处理
   - 瓦片缓存
   - 垃圾回收优化

## 🔒 生产环境考虑

### 1. 安全性

- [ ] JWT身份验证
- [ ] API速率限制
- [ ] HTTPS/TLS加密
- [ ] 输入验证和清理
- [ ] CORS策略
- [ ] 密钥管理（使用Vault）

### 2. 可靠性

- [ ] 任务持久化和恢复
- [ ] 重试机制
- [ ] 断路器模式
- [ ] 优雅关闭
- [ ] 健康检查
- [ ] 备份策略

### 3. 监控和日志

- [ ] 结构化日志（JSON）
- [ ] 分布式追踪（Jaeger）
- [ ] 告警规则
- [ ] SLA监控
- [ ] 审计日志

### 4. 测试

```bash
# 单元测试
pytest tests/unit/

# 集成测试
pytest tests/integration/

# 负载测试
locust -f tests/load/locustfile.py --host=http://localhost:8000
```

## 📝 项目结构

```
.
├── backend/
│   ├── api/              # API路由和WebSocket
│   ├── core/             # 核心调度器和配置
│   ├── models/           # 数据模型
│   ├── services/         # 业务逻辑服务
│   └── utils/            # 工具函数
├── static/               # 前端静态文件
│   ├── index.html
│   ├── style.css
│   └── app.js
├── uploads/              # 上传的图像
├── results/              # 处理结果
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── main.py              # 应用入口
└── README.md
```

## 🤝 贡献

欢迎提交问题和拉取请求！

## 📄 许可证

MIT License

## 📧 联系方式

如有问题，请通过GitHub Issues联系。

---

**注意**：这是一个演示项目。生产环境使用前请进行充分测试并实现必要的安全措施。


