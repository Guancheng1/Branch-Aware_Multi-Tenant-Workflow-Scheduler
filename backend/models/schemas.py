"""
Data model definitions
"""
from enum import Enum
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
import uuid


class JobStatus(str, Enum):
    """Job status enumeration"""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class JobType(str, Enum):
    """Job type enumeration"""
    CELL_SEGMENTATION = "cell_segmentation"  # Cell segmentation
    TISSUE_MASK = "tissue_mask"  # Tissue mask generation


class WorkflowStatus(str, Enum):
    """Workflow status enumeration"""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class JobProgress(BaseModel):
    """Job progress"""
    job_id: str
    status: JobStatus
    progress_percent: float = 0.0
    tiles_processed: int = 0
    tiles_total: int = 0
    current_message: str = ""
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None


class JobCreate(BaseModel):
    """Create job request"""
    job_type: JobType
    branch: str = Field(..., description="Branch name, jobs in the same branch execute serially")
    image_path: str = Field(..., description="Image file path")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Job parameters")
    depends_on: List[str] = Field(default_factory=list, description="List of dependent job_ids, system will automatically create workflow")
    workflow_name: Optional[str] = Field(None, description="Workflow name (optional), used to organize multiple related jobs together")


class Job(BaseModel):
    """Job model"""
    job_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    workflow_id: Optional[str] = None
    job_type: JobType
    branch: str
    image_path: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    status: JobStatus = JobStatus.PENDING
    progress_percent: float = 0.0
    tiles_processed: int = 0
    tiles_total: int = 0
    current_message: str = ""
    result_path: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None


class WorkflowNode(BaseModel):
    """Workflow node (DAG node)"""
    node_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    job_type: JobType
    branch: str
    image_path: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    depends_on: List[str] = Field(default_factory=list, description="List of dependent node IDs")


class WorkflowCreate(BaseModel):
    """Create workflow request"""
    name: str
    description: Optional[str] = None
    nodes: List[WorkflowNode]


class Workflow(BaseModel):
    """Workflow model"""
    workflow_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    name: str
    description: Optional[str] = None
    nodes: List[WorkflowNode]
    job_ids: List[str] = Field(default_factory=list)
    status: WorkflowStatus = WorkflowStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    progress_percent: float = 0.0


class WorkflowProgress(BaseModel):
    """Workflow progress"""
    workflow_id: str
    status: WorkflowStatus
    progress_percent: float
    jobs: List[JobProgress]
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]


class UserStats(BaseModel):
    """User statistics"""
    user_id: str
    active_jobs: int
    completed_jobs: int
    failed_jobs: int
    total_jobs: int


class SystemStats(BaseModel):
    """System statistics"""
    active_users: int
    max_active_users: int
    active_workers: int
    max_workers: int
    queue_depth: int
    total_jobs_processed: int
    average_job_latency_seconds: float
    per_branch_queue_depth: Dict[str, int]


