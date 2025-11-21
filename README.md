# Branch-Aware Multi-Tenant Workflow Scheduler

A high-performance workflow scheduling system designed for large-scale image processing, particularly for whole slide images (WSI) in pathology.

[中文文档](README_CN.md)

---

## ⚠️ Important Note on Resolution Settings

**Current Configuration**: Due to hardware limitations (single CPU for demonstration purposes), this project uses **resolution level 2** for cell segmentation processing. This results in:
- **Lower cell detection counts** than expected
- **Higher noise-to-signal ratio** in the segmentation results
- **Faster processing times** suitable for demonstration

**Production Recommendation**: With multi-GPU infrastructure, it is **strongly recommended** to use **resolution level 0** (highest resolution) for:
- **More accurate cell detection** with significantly higher cell counts
- **Better segmentation quality** with reduced noise
- **Clinically relevant results** suitable for pathology analysis

The current implementation can be easily configured to use level 0 by modifying the `resolution_level` parameter in `backend/core/config.py` or passing it in job parameters. The trade-off is longer processing times that require GPU acceleration for practical use.

---

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
- **User-level branch isolation**: Each user's branches are independent (e.g., User1's "main" ≠ User2's "main")

### 3. InstanSeg Integration (⚡ Optimized)

#### Two-Stage Acceleration Strategy
1. **Stage 1 - Fast Tissue Detection** (Low Resolution)
   - Quick tissue mask generation at low resolution (level 2-3)
   - Identifies regions of interest (ROI) containing actual tissue
   - Filters out 70-80% of background tiles in ~100ms

2. **Stage 2 - Selective High-Resolution Segmentation**
   - Only processes tissue-containing tiles from Stage 1
   - Applies density-based filtering for sparse regions (20-30% reduction)
   - **Result**: ~3-5x speedup on typical WSI samples (CMU-1 dataset)

#### Batch Processing & Result Merging
- **Batch inference**: Process multiple tiles simultaneously using `torch.inference_mode()`
- **Efficient memory management**: Batch size optimization for CPU/GPU constraints
- **Smart tile merging**: 
  - Tiled processing for gigapixel-scale images (512×512 tiles default)
  - Tile overlap (64-128px) with weighted blending to avoid seams
  - Post-processing deduplication for cells at tile boundaries
- **15-20% inference speedup** through optimized batch operations

#### Key Technical Optimizations
- ✅ Dual-layer filtering (mask-based + density-based)
- ✅ `torch.inference_mode()` for inference optimization
- ✅ Noise filtering with minimum cell area threshold
- ✅ Optimal tile size balancing speed and accuracy
- ✅ Parallel processing of independent branches

📖 **[详细优化指南](OPTIMIZATION_GUIDE.md)** | **[性能测试结果](OPTIMIZATION_SUMMARY.md)**

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

### 1. Start with Docker Compose

**Option A: Using start script (Recommended)**

```bash
# Clone the repository
git clone <your-repo-url>
cd Branch-Aware_Multi-Tenant-Workflow-Scheduler

# Make the script executable (first time only)
chmod +x start.sh

# Start all services with automatic checks and setup
./start.sh
```

The script will:
- ✅ Check if Docker is running
- ✅ Verify docker-compose is installed
- ✅ Create necessary directories (uploads, results, logs)
- ✅ Start all services (backend, Redis, Prometheus, Grafana)
- ✅ Display service status and access URLs

**To stop services:**
```bash
./stop.sh
# Or use: docker-compose down
```

**Option B: Direct docker-compose (Alternative)**

```bash
# Clone the repository
git clone <your-repo-url>
cd Branch-Aware_Multi-Tenant-Workflow-Scheduler

# Create directories
mkdir -p uploads results logs

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

### 2. Access the Services

Once started, you can access:
- **Web UI**: http://localhost:8000 (Main interface for job submission and monitoring)
- **API Documentation**: http://localhost:8000/docs (Interactive Swagger UI)
- **Prometheus**: http://localhost:9090 (Metrics collection)
- **Grafana**: http://localhost:3000 (Dashboards, credentials: admin/admin)

### 3. Testing the System

#### Option A: Using the Web UI

1. Open http://localhost:8000 in your browser
2. Enter your User ID (e.g., `user-001`)
3. Select a job type:
   - **Tissue Mask**: Fast tissue detection and background filtering
   - **Cell Segmentation**: Full cell segmentation with InstanSeg
4. Upload a WSI file (`.svs` format) or use the provided sample
5. Click "Submit Job" and watch real-time progress updates
6. View results including visualization and cell counts

#### Option B: Using API (curl)

**Submit a Cell Segmentation Job:**

```bash
curl -X POST "http://localhost:8000/api/v1/jobs" \
  -H "X-User-ID: user-001" \
  -H "Content-Type: application/json" \
  -d '{
    "job_type": "cell_segmentation",
    "branch": "main",
    "image_path": "uploads/CMU-1-JP2K-33005.svs",
    "parameters": {
      "tile_size": 512,
      "overlap": 64,
      "resolution_level": 2
    }
  }'
```

**Check Job Status:**

```bash
# Replace {job_id} with the ID returned from job submission
curl -X GET "http://localhost:8000/api/v1/jobs/{job_id}" \
  -H "X-User-ID: user-001"
```

**Submit a Workflow (DAG) with Dependencies:**

```bash
curl -X POST "http://localhost:8000/api/v1/workflows" \
  -H "X-User-ID: user-001" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Complete Analysis Pipeline",
    "description": "Tissue mask followed by cell segmentation",
    "nodes": [
      {
        "node_id": "tissue-detection",
        "job_type": "tissue_mask",
        "branch": "preprocessing",
        "image_path": "uploads/CMU-1-JP2K-33005.svs",
        "parameters": {},
        "depends_on": []
      },
      {
        "node_id": "cell-segmentation",
        "job_type": "cell_segmentation",
        "branch": "segmentation",
        "image_path": "uploads/CMU-1-JP2K-33005.svs",
        "parameters": {"tile_size": 512, "overlap": 64},
        "depends_on": ["tissue-detection"]
      }
    ]
  }'
```

**Upload an Image File:**

```bash
curl -X POST "http://localhost:8000/api/v1/upload" \
  -H "X-User-ID: user-001" \
  -F "file=@/path/to/your/image.svs"
```

**Query User's Job History:**

```bash
curl -X GET "http://localhost:8000/api/v1/jobs" \
  -H "X-User-ID: user-001"
```

#### Testing Multi-Tenant Behavior

Test the 3-user concurrency limit by submitting jobs from different users:

```bash
# User 1
curl -X POST "http://localhost:8000/api/v1/jobs" \
  -H "X-User-ID: user-001" \
  -H "Content-Type: application/json" \
  -d '{"job_type": "cell_segmentation", "branch": "main", "image_path": "uploads/CMU-1-JP2K-33005.svs", "parameters": {}}'

# User 2
curl -X POST "http://localhost:8000/api/v1/jobs" \
  -H "X-User-ID: user-002" \
  -H "Content-Type: application/json" \
  -d '{"job_type": "cell_segmentation", "branch": "main", "image_path": "uploads/CMU-1-JP2K-33005.svs", "parameters": {}}'

# User 3
curl -X POST "http://localhost:8000/api/v1/jobs" \
  -H "X-User-ID: user-003" \
  -H "Content-Type: application/json" \
  -d '{"job_type": "cell_segmentation", "branch": "main", "image_path": "uploads/CMU-1-JP2K-33005.svs", "parameters": {}}'

# User 4 (will be queued)
curl -X POST "http://localhost:8000/api/v1/jobs" \
  -H "X-User-ID: user-004" \
  -H "Content-Type: application/json" \
  -d '{"job_type": "cell_segmentation", "branch": "main", "image_path": "uploads/CMU-1-JP2K-33005.svs", "parameters": {}}'
```

The 4th user will be automatically queued until one of the first 3 users completes their jobs.

### 4. Real-Time Updates via WebSocket

The Web UI automatically connects to WebSocket for real-time progress updates. You can also connect programmatically:

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
  // Receive real-time updates: state changes, progress percentage, tile completion
};
```

### 5. Download Sample WSI Data (Optional)

If you need test images, download from CMU OpenSlide:

```bash
# Download sample WSI files
mkdir -p uploads
cd uploads

# Small sample (~100MB)
wget https://openslide.cs.cmu.edu/download/openslide-testdata/Aperio/CMU-1-Small-Region.svs

# Or larger samples for more comprehensive testing
wget https://openslide.cs.cmu.edu/download/openslide-testdata/Aperio/CMU-1.svs
```

Then use the file path in your job submissions: `"image_path": "uploads/CMU-1-Small-Region.svs"`

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

#### 1. InstanSeg Optimization (Already Implemented ✅)

Our **two-stage processing pipeline with batch merging** significantly reduces computational load:

**Before Optimization:**
- Process all tiles at full resolution
- Sequential tile processing
- Typical WSI: ~1000 tiles
- Total time: ~45 minutes

**After Optimization:**
- Stage 1: Fast tissue mask at low resolution (~100ms)
- Stage 2: Batch processing of filtered tiles with intelligent merging
- Typical WSI: ~200 tiles actually processed (80% reduction)
- Total time: ~12 minutes (**3-5x speedup**)

**Key Optimizations:**
1. **Two-Stage Acceleration**:
   - **Stage 1**: Fast tissue detection at low resolution to identify ROI
   - **Stage 2**: Selective high-resolution segmentation only on tissue regions
   
2. **Batch Processing & Merging**:
   - Process multiple tiles in batches using `torch.inference_mode()`
   - Efficient GPU/CPU memory utilization
   - Weighted blending at tile boundaries to eliminate seams
   - Post-processing deduplication for overlapping regions
   - 15-20% additional speedup through batch operations

3. **Dual-layer tile filtering**:
   - Mask-based: Filter out background tiles (70-80% reduction)
   - Density-based: Filter low-density tiles (20-30% reduction)

4. **Inference Optimizations**:
   - `torch.inference_mode()` for faster computation
   - Noise filtering with minimum cell area threshold
   - Optimal tile size (512×512) balancing speed and accuracy

**Impact**: With these optimizations, each worker can handle **3-5x more WSI** per hour, making the system highly efficient even with limited hardware resources.

📖 See [OPTIMIZATION_GUIDE.md](OPTIMIZATION_GUIDE.md) for detailed technical explanation.

#### 2. Horizontal Scaling

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

#### 3. Database Persistence

- PostgreSQL for job/workflow metadata
- Redis for queues and caching only
- Connection pooling

#### 4. Distributed Task Queue

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

## 🤝 Contributing

Issues and pull requests are welcome!

## 📄 License

MIT License

## 📧 Contact

For questions, please open an issue on GitHub.

---

**Note**: This is a demonstration project. Please conduct thorough testing and implement necessary security measures before production use.
