"""
任务执行器 - 负责执行具体的图像处理任务
"""
import asyncio
from pathlib import Path
from typing import Optional, Callable
import logging
from datetime import datetime

from backend.models.schemas import Job, JobStatus, JobType
from backend.services.instanseg_service import instanseg_service
from backend.core.config import settings

logger = logging.getLogger(__name__)


class JobExecutor:
    """任务执行器"""
    
    def __init__(self):
        self.running_jobs = {}
        logger.info("JobExecutor initialized")
    
    async def execute_job(
        self,
        job: Job,
        progress_callback: Optional[Callable] = None
    ) -> Job:
        """
        执行任务
        
        Args:
            job: 任务对象
            progress_callback: 进度回调函数
            
        Returns:
            更新后的任务对象
        """
        print(f"🎯 [EXECUTOR] Starting execution of job {job.job_id}, type: {job.job_type}")
        self.running_jobs[job.job_id] = job
        
        try:
            job.status = JobStatus.RUNNING
            job.started_at = datetime.now()
            job.current_message = "Starting job..."
            
            print(f"📝 [EXECUTOR] Job {job.job_id} - Image path: {job.image_path}")
            logger.info(f"Executing job {job.job_id} of type {job.job_type}")
            
            # 根据任务类型执行
            if job.job_type == JobType.CELL_SEGMENTATION:
                print(f"🔬 [EXECUTOR] Job {job.job_id} - Executing cell segmentation")
                result = await self._execute_cell_segmentation(job, progress_callback)
            elif job.job_type == JobType.TISSUE_MASK:
                print(f"🧪 [EXECUTOR] Job {job.job_id} - Executing tissue mask")
                result = await self._execute_tissue_mask(job, progress_callback)
            else:
                raise ValueError(f"Unknown job type: {job.job_type}")
            
            # 更新任务状态
            job.status = JobStatus.SUCCEEDED
            job.completed_at = datetime.now()
            job.progress_percent = 100.0
            job.tiles_processed = job.tiles_total
            job.current_message = "Completed successfully"
            job.result_path = result.get("result_path")
            
            print(f"✨ [EXECUTOR] Job {job.job_id} completed successfully, result: {result}")
            logger.info(f"Job {job.job_id} completed successfully")
            
        except Exception as e:
            print(f"💥 [EXECUTOR] Job {job.job_id} failed with error: {e}")
            logger.error(f"Job {job.job_id} failed: {e}", exc_info=True)
            job.status = JobStatus.FAILED
            job.completed_at = datetime.now()
            job.error = str(e)
            job.current_message = f"Failed: {str(e)}"
        
        finally:
            self.running_jobs.pop(job.job_id, None)
            print(f"🏁 [EXECUTOR] Job {job.job_id} finished, final status: {job.status}")
        
        return job
    
    async def _execute_cell_segmentation(
        self,
        job: Job,
        progress_callback: Optional[Callable]
    ) -> dict:
        """
        执行细胞分割任务
        
        Args:
            job: 任务对象
            progress_callback: 进度回调
            
        Returns:
            结果字典
        """
        print(f"🔬 [CELL_SEG] Job {job.job_id} - Starting cell segmentation")
        
        # 创建输出目录
        output_dir = Path(settings.RESULTS_DIR) / job.user_id / job.job_id
        output_dir.mkdir(parents=True, exist_ok=True)
        print(f"📁 [CELL_SEG] Job {job.job_id} - Output dir: {output_dir}")
        
        # 获取参数
        tile_size = job.parameters.get("tile_size", settings.TILE_SIZE)
        overlap = job.parameters.get("overlap", settings.TILE_OVERLAP)
        print(f"⚙️ [CELL_SEG] Job {job.job_id} - tile_size={tile_size}, overlap={overlap}")
        
        # 创建进度回调包装
        async def wrapped_progress(processed, total, message):
            job.tiles_processed = processed
            job.tiles_total = total
            job.progress_percent = (processed / total * 100) if total > 0 else 0
            job.current_message = message
            print(f"📊 [CELL_SEG] Job {job.job_id} - Progress: {processed}/{total} ({job.progress_percent:.1f}%) - {message}")
            
            if progress_callback:
                await progress_callback(job)
        
        print(f"🚀 [CELL_SEG] Job {job.job_id} - Calling instanseg_service.segment_large_image")
        # 执行分割
        result = await instanseg_service.segment_large_image(
            image_path=job.image_path,
            output_dir=str(output_dir),
            tile_size=tile_size,
            overlap=overlap,
            progress_callback=wrapped_progress
        )
        
        print(f"✅ [CELL_SEG] Job {job.job_id} - Segmentation complete, result: {result}")
        return result
    
    async def _execute_tissue_mask(
        self,
        job: Job,
        progress_callback: Optional[Callable]
    ) -> dict:
        """
        执行组织掩码生成任务
        
        Args:
            job: 任务对象
            progress_callback: 进度回调
            
        Returns:
            结果字典
        """
        # 创建输出目录
        output_dir = Path(settings.RESULTS_DIR) / job.user_id / job.job_id
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 创建进度回调包装
        async def wrapped_progress(processed, total, message):
            job.tiles_processed = processed
            job.tiles_total = total
            job.progress_percent = (processed / total * 100) if total > 0 else 0
            job.current_message = message
            
            if progress_callback:
                await progress_callback(job)
        
        # 生成组织掩码
        result = await instanseg_service.generate_tissue_mask(
            image_path=job.image_path,
            output_dir=str(output_dir),
            progress_callback=wrapped_progress
        )
        
        return result
    
    def get_running_job(self, job_id: str) -> Optional[Job]:
        """获取运行中的任务"""
        return self.running_jobs.get(job_id)
    
    def get_all_running_jobs(self):
        """获取所有运行中的任务"""
        return list(self.running_jobs.values())


# 全局执行器实例
job_executor = JobExecutor()

