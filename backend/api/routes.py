"""
API路由定义
"""
from fastapi import APIRouter, HTTPException, Header, UploadFile, File, Depends
from typing import Optional, List
import shutil
from pathlib import Path
import logging

from backend.models.schemas import (
    Job, JobCreate, JobProgress, JobStatus,
    Workflow, WorkflowCreate, WorkflowProgress,
    SystemStats, UserStats
)
from backend.core.scheduler import scheduler
from backend.core.config import settings
from backend.services.workflow_manager import workflow_manager

logger = logging.getLogger(__name__)

router = APIRouter()


# 依赖：获取用户ID
async def get_user_id(x_user_id: str = Header(...)) -> str:
    """从请求头获取用户ID"""
    if not x_user_id:
        raise HTTPException(status_code=400, detail="X-User-ID header is required")
    return x_user_id


@router.post("/jobs", response_model=Job)
async def create_job(
    job_create: JobCreate,
    user_id: str = Depends(get_user_id)
):
    """
    创建单个任务
    
    Headers:
        X-User-ID: 用户唯一标识
    """
    try:
        # 创建任务对象
        job = Job(
            user_id=user_id,
            job_type=job_create.job_type,
            branch=job_create.branch,
            image_path=job_create.image_path,
            parameters=job_create.parameters
        )
        
        # 提交到调度器
        job_id = await scheduler.submit_job(job)
        
        logger.info(f"Job {job_id} created by user {user_id}")
        
        return job
    
    except Exception as e:
        logger.error(f"Error creating job: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/jobs/{job_id}", response_model=Job)
async def get_job(
    job_id: str,
    user_id: str = Depends(get_user_id)
):
    """获取任务详情"""
    job = scheduler.get_job(job_id)
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # 验证用户权限
    if job.user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    return job


@router.get("/jobs", response_model=List[Job])
async def list_jobs(user_id: str = Depends(get_user_id)):
    """列出用户的所有任务"""
    jobs = scheduler.get_user_jobs(user_id)
    return jobs


@router.delete("/jobs/{job_id}")
async def cancel_job(
    job_id: str,
    user_id: str = Depends(get_user_id)
):
    """取消任务"""
    success = await scheduler.cancel_job(job_id, user_id)
    
    if not success:
        raise HTTPException(status_code=400, detail="Cannot cancel job")
    
    return {"message": "Job cancelled successfully", "job_id": job_id}


@router.post("/workflows", response_model=Workflow)
async def create_workflow(
    workflow_create: WorkflowCreate,
    user_id: str = Depends(get_user_id)
):
    """
    创建工作流（DAG）
    
    Headers:
        X-User-ID: 用户唯一标识
    """
    try:
        # 创建工作流对象
        workflow = Workflow(
            user_id=user_id,
            name=workflow_create.name,
            description=workflow_create.description,
            nodes=workflow_create.nodes
        )
        
        # 提交到工作流管理器
        workflow_id = await workflow_manager.create_workflow(workflow)
        
        logger.info(f"Workflow {workflow_id} created by user {user_id}")
        
        return workflow
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating workflow: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/workflows/{workflow_id}", response_model=Workflow)
async def get_workflow(
    workflow_id: str,
    user_id: str = Depends(get_user_id)
):
    """获取工作流详情"""
    workflow = workflow_manager.get_workflow(workflow_id)
    
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    if workflow.user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    return workflow


@router.get("/workflows/{workflow_id}/progress", response_model=WorkflowProgress)
async def get_workflow_progress(
    workflow_id: str,
    user_id: str = Depends(get_user_id)
):
    """获取工作流进度"""
    workflow = workflow_manager.get_workflow(workflow_id)
    
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    if workflow.user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    progress = workflow_manager.get_workflow_progress(workflow_id)
    return progress


@router.get("/workflows", response_model=List[Workflow])
async def list_workflows(user_id: str = Depends(get_user_id)):
    """列出用户的所有工作流"""
    workflows = workflow_manager.get_user_workflows(user_id)
    return workflows


@router.delete("/workflows/{workflow_id}")
async def cancel_workflow(
    workflow_id: str,
    user_id: str = Depends(get_user_id)
):
    """取消工作流"""
    success = await workflow_manager.cancel_workflow(workflow_id, user_id)
    
    if not success:
        raise HTTPException(status_code=400, detail="Cannot cancel workflow")
    
    return {"message": "Workflow cancelled successfully", "workflow_id": workflow_id}


@router.post("/upload")
async def upload_image(
    file: UploadFile = File(...),
    user_id: str = Depends(get_user_id)
):
    """
    上传图像文件
    
    Returns:
        文件路径信息
    """
    try:
        # 创建用户目录
        user_upload_dir = Path(settings.UPLOAD_DIR) / user_id
        user_upload_dir.mkdir(parents=True, exist_ok=True)
        
        # 保存文件
        file_path = user_upload_dir / file.filename
        
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        logger.info(f"File {file.filename} uploaded by user {user_id}")
        
        return {
            "filename": file.filename,
            "path": str(file_path),
            "size": file_path.stat().st_size
        }
    
    except Exception as e:
        logger.error(f"Error uploading file: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats/system", response_model=SystemStats)
async def get_system_stats():
    """获取系统统计信息"""
    stats = scheduler.get_system_stats()
    return SystemStats(**stats)


@router.get("/stats/user", response_model=UserStats)
async def get_user_stats(user_id: str = Depends(get_user_id)):
    """获取用户统计信息"""
    jobs = scheduler.get_user_jobs(user_id)
    
    active_jobs = sum(1 for j in jobs if j.status == JobStatus.RUNNING)
    completed_jobs = sum(1 for j in jobs if j.status == JobStatus.SUCCEEDED)
    failed_jobs = sum(1 for j in jobs if j.status == JobStatus.FAILED)
    
    return UserStats(
        user_id=user_id,
        active_jobs=active_jobs,
        completed_jobs=completed_jobs,
        failed_jobs=failed_jobs,
        total_jobs=len(jobs)
    )


@router.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "scheduler": "running",
        "max_workers": settings.MAX_WORKERS,
        "max_active_users": settings.MAX_ACTIVE_USERS
    }


