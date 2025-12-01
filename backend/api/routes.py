"""
API route definitions
"""
from fastapi import APIRouter, HTTPException, Header, UploadFile, File, Depends
from typing import Optional, List
import shutil
from pathlib import Path
import logging

from backend.models.schemas import (
    Job, JobCreate, JobProgress, JobStatus,
    Workflow, WorkflowCreate, WorkflowProgress, WorkflowNode,
    SystemStats, UserStats
)
from backend.core.scheduler import scheduler
from backend.core.config import settings
from backend.services.workflow_manager import workflow_manager

logger = logging.getLogger(__name__)

router = APIRouter()


# Dependency: Get user ID
async def get_user_id(x_user_id: str = Header(...)) -> str:
    """Get user ID from request header"""
    if not x_user_id:
        raise HTTPException(status_code=400, detail="X-User-ID header is required")
    return x_user_id


@router.post("/jobs", response_model=Job)
async def create_job(
    job_create: JobCreate,
    user_id: str = Depends(get_user_id)
):
    """
    Create a single job
    
    If depends_on is specified, the system will automatically create a workflow and organize job dependencies.
    
    Headers:
        X-User-ID: User unique identifier
    """
    try:
        # Validate dependent jobs
        dependent_jobs = []
        if job_create.depends_on:
            for dep_job_id in job_create.depends_on:
                dep_job = scheduler.get_job(dep_job_id)
                if not dep_job:
                    raise HTTPException(
                        status_code=404, 
                        detail=f"Dependent job {dep_job_id} not found"
                    )
                if dep_job.user_id != user_id:
                    raise HTTPException(
                        status_code=403, 
                        detail=f"Cannot depend on job {dep_job_id} from another user"
                    )
                dependent_jobs.append(dep_job)
        
        # If there are dependencies, automatically create or join a workflow
        workflow_id = None
        if job_create.depends_on or job_create.workflow_name:
            # Check if there's an existing workflow to join
            # If the dependent job is already in a workflow, join the same workflow
            existing_workflow = None
            if dependent_jobs:
                for dep_job in dependent_jobs:
                    if dep_job.workflow_id:
                        existing_workflow = workflow_manager.get_workflow(dep_job.workflow_id)
                        if existing_workflow:
                            break
            
            # If no existing workflow found, create a new one
            if not existing_workflow:
                workflow_name = job_create.workflow_name or f"Auto Workflow - {job_create.job_type}"
                
                # Create workflow nodes
                nodes = []
                
                # Don't create nodes for existing jobs!
                # Existing jobs are already running in the scheduler and shouldn't be duplicated
                # Only add the new job as a node, and reference existing job_ids through depends_on
                
                # Add new job as node
                new_node = WorkflowNode(
                    node_id=f"job_pending",  # Temporary ID, will be updated later
                    job_type=job_create.job_type,
                    branch=job_create.branch,
                    image_path=job_create.image_path,
                    parameters=job_create.parameters,
                    depends_on=[f"job_{dep_id}" for dep_id in job_create.depends_on]
                )
                nodes.append(new_node)
                
                # Create workflow
                workflow = Workflow(
                    user_id=user_id,
                    name=workflow_name,
                    description=f"Automatically created workflow with dependency on existing jobs",
                    nodes=nodes,
                    job_ids=[dep_job.job_id for dep_job in dependent_jobs]  # Record dependent job_ids but don't create new ones
                )
                
                workflow_id = await workflow_manager.create_workflow(workflow)
                logger.info(f"Auto-created workflow {workflow_id} for job with dependencies")
            else:
                # Join existing workflow
                workflow_id = existing_workflow.workflow_id
                
                # Add new node to existing workflow
                new_node = WorkflowNode(
                    node_id=f"job_pending",
                    job_type=job_create.job_type,
                    branch=job_create.branch,
                    image_path=job_create.image_path,
                    parameters=job_create.parameters,
                    depends_on=[f"job_{dep_id}" for dep_id in job_create.depends_on]
                )
                existing_workflow.nodes.append(new_node)
                logger.info(f"Added job to existing workflow {workflow_id}")
        
        # Create job object
        job = Job(
            user_id=user_id,
            workflow_id=workflow_id,
            job_type=job_create.job_type,
            branch=job_create.branch,
            image_path=job_create.image_path,
            parameters=job_create.parameters
        )
        
        # Submit to scheduler
        job_id = await scheduler.submit_job(job)
        
        # Update node_id in workflow (from pending to actual job_id)
        if workflow_id:
            workflow = workflow_manager.get_workflow(workflow_id)
            if workflow:
                for node in workflow.nodes:
                    if node.node_id == "job_pending":
                        node.node_id = f"job_{job_id}"
                        break
                workflow.job_ids.append(job_id)
        
        logger.info(f"Job {job_id} created by user {user_id}" + 
                   (f" in workflow {workflow_id}" if workflow_id else ""))
        
        return job
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating job: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/jobs/{job_id}", response_model=Job)
async def get_job(
    job_id: str,
    user_id: str = Depends(get_user_id)
):
    """Get job details"""
    job = scheduler.get_job(job_id)
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Verify user permissions
    if job.user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    return job


@router.get("/jobs", response_model=List[Job])
async def list_jobs(user_id: str = Depends(get_user_id)):
    """List all user jobs"""
    jobs = scheduler.get_user_jobs(user_id)
    return jobs


@router.delete("/jobs/{job_id}")
async def cancel_job(
    job_id: str,
    user_id: str = Depends(get_user_id)
):
    """Cancel job"""
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
    Create workflow (DAG)
    
    Headers:
        X-User-ID: User unique identifier
    """
    try:
        # Create workflow object
        workflow = Workflow(
            user_id=user_id,
            name=workflow_create.name,
            description=workflow_create.description,
            nodes=workflow_create.nodes
        )
        
        # Submit to workflow manager
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
    """Get workflow details"""
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
    """Get workflow progress"""
    workflow = workflow_manager.get_workflow(workflow_id)
    
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    if workflow.user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    progress = workflow_manager.get_workflow_progress(workflow_id)
    return progress


@router.get("/workflows", response_model=List[Workflow])
async def list_workflows(user_id: str = Depends(get_user_id)):
    """List all user workflows"""
    workflows = workflow_manager.get_user_workflows(user_id)
    return workflows


@router.delete("/workflows/{workflow_id}")
async def cancel_workflow(
    workflow_id: str,
    user_id: str = Depends(get_user_id)
):
    """Cancel workflow"""
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
    Upload image file
    
    Returns:
        File path information
    """
    try:
        # Create user directory
        user_upload_dir = Path(settings.UPLOAD_DIR) / user_id
        user_upload_dir.mkdir(parents=True, exist_ok=True)
        
        # Save file
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
    """Get system statistics"""
    stats = scheduler.get_system_stats()
    return SystemStats(**stats)


@router.get("/stats/user", response_model=UserStats)
async def get_user_stats(user_id: str = Depends(get_user_id)):
    """Get user statistics"""
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
    """Health check"""
    return {
        "status": "healthy",
        "scheduler": "running",
        "max_workers": settings.MAX_WORKERS,
        "max_active_users": settings.MAX_ACTIVE_USERS
    }


