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
    MAX_WORKERS: int = 5  # 全局worker池大小，控制并发任务数
    MAX_ACTIVE_USERS: int = 3  # 最多3个用户同时有运行中的任务
    
    # Redis配置
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    
    # 存储配置
    UPLOAD_DIR: Path = Path("./uploads")
    RESULTS_DIR: Path = Path("./results")
    
    # InstanSeg配置
    INSTANSEG_MODEL: str = "fluorescence_nuclei_1"
    TILE_SIZE: int = 512  # 优化：512×512 平衡速度与精度
    TILE_OVERLAP: int = 64  # 优化：减少重叠区域
    BATCH_SIZE: int = 4
    
    # 两阶段分割配置
    TISSUE_MASK_LEVEL: int = 2  # Stage 1: 低分辨率生成 mask
    CELL_SEG_LEVEL: int = 1     # Stage 2: 高分辨率细胞分割
    TISSUE_RATIO_THRESH: float = 0.05  # tile 最小组织覆盖率（降低以过滤更多）
    FG_DENSITY_THRESH: float = 0.10   # tile 内部最小前景密度（提高以过滤稀疏区域）
    MIN_CELL_AREA: float = 20.0       # 最小细胞面积（过滤噪声）
    
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


