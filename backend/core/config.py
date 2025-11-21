"""
配置管理
"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """应用配置"""
    
    # 服务器配置
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    # Worker配置
    MAX_WORKERS: int = 8
    MAX_ACTIVE_USERS: int = 3
    
    # Redis配置
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    
    # 存储配置
    UPLOAD_DIR: Path = Path("./uploads")
    RESULTS_DIR: Path = Path("./results")
    
    # InstanSeg配置
    INSTANSEG_MODEL: str = "fluorescence_nuclei_1"
    TILE_SIZE: int = 1024
    TILE_OVERLAP: int = 128
    BATCH_SIZE: int = 4
    
    # 设备配置
    DEVICE: str = "cuda"  # cuda or cpu
    
    class Config:
        env_file = ".env"
        case_sensitive = True
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # 创建必要的目录
        self.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        self.RESULTS_DIR.mkdir(parents=True, exist_ok=True)


# 全局配置实例
settings = Settings()


