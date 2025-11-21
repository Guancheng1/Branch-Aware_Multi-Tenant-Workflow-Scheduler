# Branch-Aware Multi-Tenant Workflow Scheduler

A high-performance workflow scheduling system designed for large-scale image processing, particularly for whole slide images (WSI) in pathology.

[中文文档](README_CN.md)

## 🌟 Key Features

### 1. Branch-Aware Scheduling
- **Serial Execution**: Jobs within the same branch execute serially in FIFO order
- **Parallel Execution**: Jobs from different branches can run in parallel, bounded by global worker limit
- **Failure Isolation**: One branch's failure doesn't block other branches

### 2. Multi-Tenant Isolation
- Each request identified by `X-User-ID` header
- Maximum of 3 users can have running jobs concurrently
- 4th and later users automatically queued
- Rate limiting and stability guarantees for high QPS scenarios

### 3. InstanSeg Integration
- Cell segmentation using InstanSeg
- Tiled processing for gigapixel-scale images
- Tile overlap with blending to avoid seams
- Batch processing optimization for throughput

### 4. Real-Time Progress Tracking
- WebSocket real-time updates
- Job-level and workflow-level progress tracking
- Tile processing progress visualization
- State transitions: `PENDING → RUNNING → SUCCEEDED/FAILED`

### 5. Workflow DAG Support
- Define complex task dependency graphs
- Automatic topological sorting and execution
- Node-level failure handling
- Parallel execution of independent branches

### 6. Monitoring and Observability
- Prometheus metrics export
- Queue depth, active workers, job latency metrics
- Grafana dashboards
- System health checks

## 🏗️ Architecture

```
┌─────────────┐
│ User Request │
└──────┬──────┘
       │
       v
┌─────────────────────────────────┐
│      FastAPI + WebSocket        │
│  (API endpoints, real-time,     │
│   file upload)                  │
└──────────┬──────────────────────┘
           │
           v
┌─────────────────────────────────┐
│   BranchAwareScheduler          │
│  - Branch queue management      │
│  - Multi-tenant isolation       │
│    (max 3 active users)         │
│  - Global worker pool           │
│    (semaphore control)          │
└──────────┬──────────────────────┘
           │
           v
┌─────────────────────────────────┐
│      WorkflowManager            │
│  - DAG validation & topo sort   │
│  - Dependency management        │
│  - Workflow-level progress      │
└──────────┬──────────────────────┘
           │
           v
┌─────────────────────────────────┐
│       JobExecutor               │
│  - InstanSeg integration        │
│  - Tiled image processing       │
│  - Progress callbacks           │
└──────────┬──────────────────────┘
           │
           v
┌─────────────────────────────────┐
│     InstanSegService            │
│  - Large image segmentation     │
│  - Tissue mask generation       │
│  - Result merging & viz         │
└─────────────────────────────────┘
```

## 🚀 Quick Start

### Using Docker Compose (Recommended)

```bash
# Clone the repository
git clone <your-repo-url>
cd Branch-Aware_Multi-Tenant-Workflow-Scheduler

# Start all services
docker-compose up -d

# View logs
docker-compose logs -f app

# Stop services
docker-compose down
```

> **InstanSeg runtime note**  
> The Docker image installs `instanseg-torch[full]` together with the OpenCV/OpenSlide native libraries (`libglib2.0-0`, `libgl1`, `libsm6`, `libxrender1`, `libxext6`).  
> If you rebuild the image or manage dependencies manually, make sure to install the same extras; otherwise the backend falls back to the mock InstanSeg implementation.

Access:
- **Web UI**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **Prometheus**: http://localhost:9090
- **Grafana**: http://localhost:3000 (admin/admin)

### Local Development

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Start Redis (using Docker)
docker run -d -p 6379:6379 redis:7-alpine

# Start application
python main.py
```

## 📖 API Examples

### 1. Create a Job

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

### 2. Create a Workflow (DAG)

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

### 3. Query Job Status

```bash
curl -X GET "http://localhost:8000/api/v1/jobs/{job_id}" \
  -H "X-User-ID: user-001"
```

### 4. WebSocket Connection

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/user-001');

ws.onopen = () => {
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

## 📊 Monitoring Metrics

### Prometheus Metrics

- `jobs_total`: Total jobs (by user, type, status)
- `jobs_active`: Active jobs (by user, branch)
- `job_duration_seconds`: Job execution duration
- `queue_depth`: Queue depth (by branch)
- `active_users`: Number of active users
- `waiting_users`: Number of waiting users
- `active_workers`: Number of active workers
- `system_errors_total`: Total system errors

## 📈 Scaling Strategy

### Scaling to 10× Jobs/Users

#### 1. Horizontal Scaling

```yaml
services:
  app:
    deploy:
      replicas: 3
    
  redis:
    image: redis:7-cluster
    
  nginx:
    image: nginx:alpine
```

#### 2. Database Persistence

- PostgreSQL for job/workflow metadata
- Redis for queues and caching only
- Connection pooling

#### 3. Distributed Task Queue

- Celery + Redis/RabbitMQ
- Separate worker process pools
- Dynamic worker scaling

#### 4. Object Storage

- MinIO or S3 for images and results
- CDN for result access
- Multipart upload

#### 5. Caching Strategy

- Redis cache for hot data
- Result caching
- User session caching

## 🔒 Production Considerations

### Security
- JWT authentication
- API rate limiting
- HTTPS/TLS
- Input validation
- Secret management (Vault)

### Reliability
- Task persistence and recovery
- Retry mechanisms
- Circuit breaker pattern
- Graceful shutdown
- Health checks
- Backup strategy

### Testing
```bash
# Unit tests
pytest tests/unit/

# Integration tests
pytest tests/integration/

# Load testing
locust -f tests/load/locustfile.py
```

## 📝 Project Structure

```
.
├── backend/
│   ├── api/              # API routes and WebSocket
│   ├── core/             # Core scheduler and config
│   ├── models/           # Data models
│   ├── services/         # Business logic
│   └── utils/            # Utilities
├── static/               # Frontend static files
├── uploads/              # Uploaded images
├── results/              # Processing results
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── main.py
└── README.md
```

## 🧪 Testing with Sample Data

```bash
# Download WSI test data from CMU OpenSlide
mkdir -p uploads
cd uploads
wget https://openslide.cs.cmu.edu/download/openslide-testdata/Aperio/CMU-1-Small-Region.svs
```

## 🤝 Contributing

Issues and pull requests are welcome!

## 📄 License

MIT License

## 📧 Contact

For questions, please open an issue on GitHub.

---

**Note**: This is a demonstration project. Please conduct thorough testing and implement necessary security measures before production use.
