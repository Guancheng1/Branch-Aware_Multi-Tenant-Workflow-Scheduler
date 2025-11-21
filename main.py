"""
主应用入口
"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from backend.api.routes import router as api_router
from backend.api.websocket import websocket_endpoint, manager as ws_manager
from backend.core.scheduler import scheduler
from backend.core.config import settings
from backend.services.instanseg_service import instanseg_service

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    logger.info("Starting application...")
    
    # 初始化InstanSeg模型
    try:
        await instanseg_service.initialize()
    except Exception as e:
        logger.warning(f"Failed to initialize InstanSeg: {e}")
    
    # 启动调度器
    await scheduler.start()
    
    # 启动WebSocket广播
    await ws_manager.start_broadcasting()
    
    logger.info("Application started successfully")
    
    yield
    
    # 关闭时
    logger.info("Shutting down application...")
    
    await scheduler.stop()
    await ws_manager.stop_broadcasting()
    
    logger.info("Application shutdown complete")


# 创建FastAPI应用
app = FastAPI(
    title="Branch-Aware Multi-Tenant Workflow Scheduler",
    description="大图像处理的工作流调度系统",
    version="1.0.0",
    lifespan=lifespan
)

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应该限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载静态文件（必须在API路由之前）
try:
    app.mount("/static", StaticFiles(directory="static"), name="static")
    logger.info("Static files mounted at /static")
except RuntimeError:
    logger.warning("Static directory not found, skipping static files mounting")

# 挂载结果文件目录（必须在API路由之前）
try:
    app.mount("/results", StaticFiles(directory="results"), name="results")
    logger.info("Results files mounted at /results")
except RuntimeError:
    logger.warning("Results directory not found, skipping results files mounting")

# 注册API路由
app.include_router(api_router, prefix="/api/v1", tags=["API"])

# WebSocket路由
@app.websocket("/ws/{user_id}")
async def websocket_route(websocket: WebSocket, user_id: str):
    """WebSocket端点"""
    await websocket_endpoint(websocket, user_id)

# 添加Prometheus监控
instrumentator = Instrumentator()
instrumentator.instrument(app).expose(app, endpoint="/metrics")


@app.get("/health")
async def health():
    """健康检查端点"""
    return {"status": "healthy"}


@app.get("/")
async def root():
    """根路径 - 重定向到前端页面"""
    return RedirectResponse(url="/static/index.html")


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True,
        log_level="info"
    )

