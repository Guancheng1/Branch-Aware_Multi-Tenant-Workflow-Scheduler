# 快速开始指南

本指南将帮助您在5分钟内启动并运行系统。

## 前置要求

- Docker和Docker Compose已安装
- Python 3.10+（仅本地开发需要）
- 8GB以上内存推荐

## 方法1：使用Docker Compose（推荐）

### 1. 启动服务

```bash
# 使用启动脚本（Linux/Mac）
./start.sh

# 或手动启动
docker-compose up -d
```

### 2. 验证服务

```bash
# 检查服务状态
docker-compose ps

# 查看日志
docker-compose logs -f app
```

### 3. 访问应用

- **Web界面**: http://localhost:8000
- **API文档**: http://localhost:8000/docs
- **Prometheus**: http://localhost:9090
- **Grafana**: http://localhost:3000

### 4. 停止服务

```bash
# 使用停止脚本
./stop.sh

# 或手动停止
docker-compose down
```

## 方法2：本地开发

### 1. 安装依赖

```bash
# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

### 2. 启动Redis

```bash
docker run -d -p 6379:6379 --name redis redis:7-alpine
```

### 3. 启动应用

```bash
python main.py
```

### 4. 访问应用

访问 http://localhost:8000

## 快速测试

### 使用Web界面

1. 打开 http://localhost:8000
2. 在左侧输入用户ID（例如：user-001）
3. 点击"上传图像"标签
4. 上传一张图像文件
5. 点击"任务管理"标签
6. 点击"+ 创建任务"
7. 填写表单并提交
8. 查看实时进度更新

### 使用API测试脚本

```bash
# 运行基本测试
python test_api.py

# 使用图像文件运行完整测试
python test_api.py path/to/your/image.jpg
```

### 使用cURL

```bash
# 健康检查
curl http://localhost:8000/health

# 系统统计
curl http://localhost:8000/api/v1/stats/system

# 创建任务
curl -X POST "http://localhost:8000/api/v1/jobs" \
  -H "X-User-ID: user-001" \
  -H "Content-Type: application/json" \
  -d '{
    "job_type": "cell_segmentation",
    "branch": "main",
    "image_path": "/path/to/image.jpg",
    "parameters": {
      "tile_size": 512,
      "overlap": 64
    }
  }'
```

## 测试多用户场景

### 场景1：多用户并发

打开3个浏览器窗口（或使用不同的浏览器）：
- 窗口1：使用用户ID "user-001"
- 窗口2：使用用户ID "user-002"
- 窗口3：使用用户ID "user-003"

在每个窗口创建任务，观察：
- 前3个用户可以同时运行任务
- 第4个用户会进入等待队列

### 场景2：分支并行

创建多个任务，使用不同的分支：
- 任务1：branch="main"
- 任务2：branch="feature-1"
- 任务3：branch="feature-2"

观察：
- 不同分支的任务可以并行执行
- 同一分支的任务串行执行

### 场景3：工作流DAG

使用API创建包含依赖关系的工作流：

```bash
curl -X POST "http://localhost:8000/api/v1/workflows" \
  -H "X-User-ID: user-001" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Complete Pipeline",
    "nodes": [
      {
        "node_id": "node-1",
        "job_type": "tissue_mask",
        "branch": "preprocess",
        "image_path": "/path/to/image.jpg",
        "depends_on": []
      },
      {
        "node_id": "node-2",
        "job_type": "cell_segmentation",
        "branch": "segment",
        "image_path": "/path/to/image.jpg",
        "depends_on": ["node-1"]
      }
    ]
  }'
```

## 下载测试数据

```bash
# 创建上传目录
mkdir -p uploads

# 下载WSI测试数据
cd uploads
wget https://openslide.cs.cmu.edu/download/openslide-testdata/Aperio/CMU-1-Small-Region.svs
```

## 监控和调试

### 查看日志

```bash
# 应用日志
docker-compose logs -f app

# 所有服务日志
docker-compose logs -f

# Redis日志
docker-compose logs -f redis
```

### 查看指标

访问 http://localhost:8000/metrics 查看Prometheus指标

### 查看仪表板

访问 http://localhost:3000（Grafana）：
- 用户名：admin
- 密码：admin

## 常见问题

### Q: 服务启动失败

A: 检查端口是否被占用：
```bash
# 检查端口占用
lsof -i :8000
lsof -i :6379
lsof -i :9090
lsof -i :3000
```

### Q: 无法连接WebSocket

A: 确保：
1. 应用正常运行
2. 浏览器支持WebSocket
3. 没有代理或防火墙阻止

### Q: 任务一直处于PENDING状态

A: 可能原因：
1. Worker已满（等待其他任务完成）
2. 用户在等待队列中（已有3个活跃用户）
3. 同一分支有其他任务在运行

查看系统统计确认：
```bash
curl http://localhost:8000/api/v1/stats/system
```

### Q: InstanSeg模型加载失败

A: 
1. 首次运行会自动下载模型（需要网络连接）
2. 如果网络问题，系统会使用mock模式
3. 查看日志确认：`docker-compose logs -f app`

## 下一步

- 阅读 [README.md](README.md) 了解完整功能
- 阅读 [ARCHITECTURE.md](ARCHITECTURE.md) 了解系统架构
- 查看 [API文档](http://localhost:8000/docs)
- 探索示例代码和测试脚本

## 获取帮助

如有问题，请：
1. 查看日志：`docker-compose logs -f`
2. 检查健康状态：`curl http://localhost:8000/health`
3. 提交GitHub Issue

祝使用愉快！🚀


