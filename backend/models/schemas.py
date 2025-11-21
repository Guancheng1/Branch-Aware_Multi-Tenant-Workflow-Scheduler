"""
数据模型定义
"""
from enum import Enum
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
import uuid


class JobStatus(str, Enum):
    """任务状态枚举"""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class JobType(str, Enum):
    """任务类型枚举"""
    CELL_SEGMENTATION = "cell_segmentation"  # 细胞分割
    TISSUE_MASK = "tissue_mask"  # 组织掩码生成


class WorkflowStatus(str, Enum):
    """工作流状态枚举"""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class JobProgress(BaseModel):
    """任务进度"""
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
    """创建任务请求"""
    job_type: JobType
    branch: str = Field(..., description="分支名称，同一分支的任务串行执行")
    image_path: str = Field(..., description="图像文件路径")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="任务参数")


class Job(BaseModel):
    """任务模型"""
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
    """工作流节点（DAG节点）"""
    node_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    job_type: JobType
    branch: str
    image_path: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    depends_on: List[str] = Field(default_factory=list, description="依赖的节点ID列表")


class WorkflowCreate(BaseModel):
    """创建工作流请求"""
    name: str
    description: Optional[str] = None
    nodes: List[WorkflowNode]


class Workflow(BaseModel):
    """工作流模型"""
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
    """工作流进度"""
    workflow_id: str
    status: WorkflowStatus
    progress_percent: float
    jobs: List[JobProgress]
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]


class UserStats(BaseModel):
    """用户统计"""
    user_id: str
    active_jobs: int
    completed_jobs: int
    failed_jobs: int
    total_jobs: int


class SystemStats(BaseModel):
    """系统统计"""
    active_users: int
    max_active_users: int
    active_workers: int
    max_workers: int
    queue_depth: int
    total_jobs_processed: int
    average_job_latency_seconds: float
    per_branch_queue_depth: Dict[str, int]


