"""
Main application entry point
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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle management"""
    # On startup
    logger.info("Starting application...")
    
    # Initialize InstanSeg model
    try:
        await instanseg_service.initialize()
    except Exception as e:
        logger.warning(f"Failed to initialize InstanSeg: {e}")
    
    # Start scheduler
    await scheduler.start()
    
    # Start WebSocket broadcasting
    await ws_manager.start_broadcasting()
    
    logger.info("Application started successfully")
    
    yield
    
    # On shutdown
    logger.info("Shutting down application...")
    
    await scheduler.stop()
    await ws_manager.stop_broadcasting()
    
    logger.info("Application shutdown complete")


# Create FastAPI application
app = FastAPI(
    title="Branch-Aware Multi-Tenant Workflow Scheduler",
    description="Workflow scheduling system for large image processing",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Should restrict to specific domains in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files (must be before API routes)
try:
    app.mount("/static", StaticFiles(directory="static"), name="static")
    logger.info("Static files mounted at /static")
except RuntimeError:
    logger.warning("Static directory not found, skipping static files mounting")

# Mount results file directory (must be before API routes)
try:
    app.mount("/results", StaticFiles(directory="results"), name="results")
    logger.info("Results files mounted at /results")
except RuntimeError:
    logger.warning("Results directory not found, skipping results files mounting")

# Register API routes
app.include_router(api_router, prefix="/api/v1", tags=["API"])

# WebSocket route
@app.websocket("/ws/{user_id}")
async def websocket_route(websocket: WebSocket, user_id: str):
    """WebSocket endpoint"""
    await websocket_endpoint(websocket, user_id)

# Add Prometheus monitoring
instrumentator = Instrumentator()
instrumentator.instrument(app).expose(app, endpoint="/metrics")


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy"}


@app.get("/")
async def root():
    """Root path - redirect to frontend page"""
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

