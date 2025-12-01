"""
Configuration management
"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application configuration"""
    
    # Server configuration
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    # Worker configuration
    MAX_WORKERS: int = 5  # Global worker pool size, controls concurrent tasks
    MAX_ACTIVE_USERS: int = 3  # Maximum 3 users with running tasks simultaneously
    
    # Redis configuration
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    
    # Storage configuration
    UPLOAD_DIR: Path = Path("./uploads")
    RESULTS_DIR: Path = Path("./results")
    
    # InstanSeg configuration
    INSTANSEG_MODEL: str = "fluorescence_nuclei_1"
    TILE_SIZE: int = 512  # Optimization: 512×512 balances speed and accuracy
    TILE_OVERLAP: int = 64  # Optimization: reduce overlap area
    BATCH_SIZE: int = 8  # Batch processing size: process multiple tiles at once, fully utilize GPU parallelism
    
    # Two-stage segmentation configuration
    TISSUE_MASK_LEVEL: int = 2  # Stage 1: Low resolution mask generation
    CELL_SEG_LEVEL: int = 1     # Stage 2: High resolution cell segmentation
    TISSUE_RATIO_THRESH: float = 0.05  # Minimum tissue coverage ratio for tiles (lower to filter more)
    FG_DENSITY_THRESH: float = 0.10   # Minimum foreground density within tiles (increase to filter sparse regions)
    MIN_CELL_AREA: float = 20.0       # Minimum cell area (filter noise)
    
    # Device configuration
    DEVICE: str = "cuda"  # cuda or cpu
    
    class Config:
        env_file = ".env"
        case_sensitive = True
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Create necessary directories
        self.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        self.RESULTS_DIR.mkdir(parents=True, exist_ok=True)


# Global configuration instance
settings = Settings()


