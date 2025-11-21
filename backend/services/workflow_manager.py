"""
工作流管理器 - 管理DAG工作流
"""
import asyncio
from typing import Dict, List, Set, Optional
from collections import defaultdict
import logging
from datetime import datetime

from backend.models.schemas import (
    Workflow, WorkflowStatus, WorkflowNode, WorkflowProgress,
    Job, JobStatus, JobType, JobProgress
)
from backend.core.scheduler import scheduler
from backend.services.job_executor import job_executor

logger = logging.getLogger(__name__)


class WorkflowManager:
    """工作流管理器"""
    
    def __init__(self):
        self.workflows: Dict[str, Workflow] = {}
        self.workflow_jobs: Dict[str, List[str]] = defaultdict(list)  # workflow_id -> job_ids
        self.node_to_job: Dict[str, str] = {}  # node_id -> job_id
        logger.info("WorkflowManager initialized")
    
    async def create_workflow(self, workflow: Workflow) -> str:
        """
        创建并启动工作流
        
        Args:
            workflow: 工作流对象
            
        Returns:
            workflow_id
        """
        workflow_id = workflow.workflow_id
        self.workflows[workflow_id] = workflow
        
        logger.info(f"Creating workflow {workflow_id} with {len(workflow.nodes)} nodes")
        
        # 验证DAG
        if not self._validate_dag(workflow.nodes):
            raise ValueError("Invalid DAG: contains cycles or invalid dependencies")
        
        # 启动工作流执行
        asyncio.create_task(self._execute_workflow(workflow))
        
        return workflow_id
    
    def _validate_dag(self, nodes: List[WorkflowNode]) -> bool:
        """
        验证DAG的有效性（无环图）
        
        Args:
            nodes: 节点列表
            
        Returns:
            是否有效
        """
        # 构建邻接表
        node_ids = {node.node_id for node in nodes}
        graph = {node.node_id: node.depends_on for node in nodes}
        
        # 检查所有依赖是否存在
        for node in nodes:
            for dep in node.depends_on:
                if dep not in node_ids:
                    logger.error(f"Node {node.node_id} depends on non-existent node {dep}")
                    return False
        
        # 检查是否有环（拓扑排序）
        visited = set()
        rec_stack = set()
        
        def has_cycle(node_id):
            visited.add(node_id)
            rec_stack.add(node_id)
            
            for neighbor in graph.get(node_id, []):
                if neighbor not in visited:
                    if has_cycle(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True
            
            rec_stack.remove(node_id)
            return False
        
        for node_id in graph:
            if node_id not in visited:
                if has_cycle(node_id):
                    logger.error("DAG contains cycle")
                    return False
        
        return True
    
    async def _execute_workflow(self, workflow: Workflow):
        """
        执行工作流
        
        Args:
            workflow: 工作流对象
        """
        workflow.status = WorkflowStatus.RUNNING
        workflow.started_at = datetime.now()
        
        try:
            # 构建依赖图
            node_map = {node.node_id: node for node in workflow.nodes}
            completed_nodes: Set[str] = set()
            failed_nodes: Set[str] = set()
            running_nodes: Set[str] = set()
            
            # 持续执行直到所有节点完成或失败
            while len(completed_nodes) + len(failed_nodes) < len(workflow.nodes):
                # 找到可以执行的节点（依赖已完成）
                ready_nodes = []
                for node in workflow.nodes:
                    if (node.node_id not in completed_nodes 
                        and node.node_id not in failed_nodes
                        and node.node_id not in running_nodes):
                        # 检查依赖
                        deps_satisfied = all(
                            dep in completed_nodes for dep in node.depends_on
                        )
                        if deps_satisfied:
                            ready_nodes.append(node)
                
                # 提交准备好的节点
                for node in ready_nodes:
                    running_nodes.add(node.node_id)
                    asyncio.create_task(
                        self._execute_node(workflow, node, completed_nodes, failed_nodes, running_nodes)
                    )
                
                # 更新进度
                self._update_workflow_progress(workflow)
                
                # 等待一段时间再检查
                await asyncio.sleep(0.5)
            
            # 检查最终状态
            if failed_nodes:
                workflow.status = WorkflowStatus.FAILED
                logger.error(f"Workflow {workflow.workflow_id} failed with {len(failed_nodes)} failed nodes")
            else:
                workflow.status = WorkflowStatus.COMPLETED
                logger.info(f"Workflow {workflow.workflow_id} completed successfully")
            
        except Exception as e:
            logger.error(f"Error executing workflow {workflow.workflow_id}: {e}", exc_info=True)
            workflow.status = WorkflowStatus.FAILED
        
        finally:
            workflow.completed_at = datetime.now()
            self._update_workflow_progress(workflow)
    
    async def _execute_node(
        self,
        workflow: Workflow,
        node: WorkflowNode,
        completed_nodes: Set[str],
        failed_nodes: Set[str],
        running_nodes: Set[str]
    ):
        """
        执行单个节点
        
        Args:
            workflow: 工作流对象
            node: 节点对象
            completed_nodes: 已完成节点集合
            failed_nodes: 失败节点集合
            running_nodes: 运行中节点集合
        """
        try:
            print(f"🌳 [WORKFLOW] Executing node {node.node_id} in workflow {workflow.workflow_id}")
            logger.info(f"Executing node {node.node_id} in workflow {workflow.workflow_id}")
            
            # 创建任务
            job = Job(
                user_id=workflow.user_id,
                workflow_id=workflow.workflow_id,
                job_type=node.job_type,
                branch=node.branch,
                image_path=node.image_path,
                parameters=node.parameters
            )
            
            print(f"📝 [WORKFLOW] Created job {job.job_id} for node {node.node_id}")
            print(f"📝 [WORKFLOW] Job details - type: {node.job_type}, branch: {node.branch}, image: {node.image_path}")
            
            # 提交到调度器
            job_id = await scheduler.submit_job(job)
            self.workflow_jobs[workflow.workflow_id].append(job_id)
            workflow.job_ids.append(job_id)
            self.node_to_job[node.node_id] = job_id
            
            print(f"📤 [WORKFLOW] Job {job_id} submitted to scheduler")
            
            # 等待任务完成
            iteration = 0
            while True:
                job = scheduler.get_job(job_id)
                if not job:
                    print(f"⚠️ [WORKFLOW] Job {job_id} not found in scheduler")
                    break
                
                if iteration % 10 == 0:  # 每5秒打印一次
                    print(f"⏳ [WORKFLOW] Waiting for job {job_id}, status: {job.status}, progress: {job.progress_percent:.1f}%")
                
                if job.status in [JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED]:
                    print(f"🏁 [WORKFLOW] Job {job_id} finished with status: {job.status}")
                    break
                
                # 注意：调度器现在会自动执行任务，不需要在这里手动调用executor
                
                await asyncio.sleep(0.5)
                iteration += 1
            
            # 检查最终状态
            if job and job.status == JobStatus.SUCCEEDED:
                completed_nodes.add(node.node_id)
                print(f"✅ [WORKFLOW] Node {node.node_id} completed successfully")
                logger.info(f"Node {node.node_id} completed successfully")
            else:
                failed_nodes.add(node.node_id)
                print(f"❌ [WORKFLOW] Node {node.node_id} failed")
                logger.error(f"Node {node.node_id} failed")
        
        except Exception as e:
            print(f"💥 [WORKFLOW] Error executing node {node.node_id}: {e}")
            logger.error(f"Error executing node {node.node_id}: {e}", exc_info=True)
            failed_nodes.add(node.node_id)
        
        finally:
            running_nodes.discard(node.node_id)
            print(f"🧹 [WORKFLOW] Node {node.node_id} cleaned up")
    
    def _update_workflow_progress(self, workflow: Workflow):
        """更新工作流进度"""
        if not workflow.job_ids:
            workflow.progress_percent = 0.0
            return
        
        # 计算所有任务的平均进度
        total_progress = 0.0
        for job_id in workflow.job_ids:
            job = scheduler.get_job(job_id)
            if job:
                if job.status == JobStatus.SUCCEEDED:
                    total_progress += 100.0
                elif job.status == JobStatus.RUNNING:
                    total_progress += job.progress_percent
        
        workflow.progress_percent = total_progress / len(workflow.job_ids)
    
    def get_workflow(self, workflow_id: str) -> Optional[Workflow]:
        """获取工作流"""
        return self.workflows.get(workflow_id)
    
    def get_workflow_progress(self, workflow_id: str) -> Optional[WorkflowProgress]:
        """获取工作流进度"""
        workflow = self.workflows.get(workflow_id)
        if not workflow:
            return None
        
        # 获取所有任务的进度
        jobs = []
        for job_id in workflow.job_ids:
            job = scheduler.get_job(job_id)
            if job:
                jobs.append(JobProgress(
                    job_id=job.job_id,
                    status=job.status,
                    progress_percent=job.progress_percent,
                    tiles_processed=job.tiles_processed,
                    tiles_total=job.tiles_total,
                    current_message=job.current_message,
                    started_at=job.started_at,
                    completed_at=job.completed_at,
                    error=job.error
                ))
        
        return WorkflowProgress(
            workflow_id=workflow.workflow_id,
            status=workflow.status,
            progress_percent=workflow.progress_percent,
            jobs=jobs,
            created_at=workflow.created_at,
            started_at=workflow.started_at,
            completed_at=workflow.completed_at
        )
    
    def get_user_workflows(self, user_id: str) -> List[Workflow]:
        """获取用户的所有工作流"""
        return [
            wf for wf in self.workflows.values()
            if wf.user_id == user_id
        ]
    
    async def cancel_workflow(self, workflow_id: str, user_id: str) -> bool:
        """
        取消工作流
        
        Args:
            workflow_id: 工作流ID
            user_id: 用户ID
            
        Returns:
            是否成功取消
        """
        workflow = self.workflows.get(workflow_id)
        if not workflow:
            return False
        
        if workflow.user_id != user_id:
            logger.warning(f"User {user_id} attempted to cancel workflow {workflow_id} owned by {workflow.user_id}")
            return False
        
        if workflow.status not in [WorkflowStatus.PENDING, WorkflowStatus.RUNNING]:
            return False
        
        # 取消所有相关任务
        cancelled_count = 0
        for job_id in workflow.job_ids:
            if await scheduler.cancel_job(job_id, user_id):
                cancelled_count += 1
        
        workflow.status = WorkflowStatus.CANCELLED
        workflow.completed_at = datetime.now()
        
        logger.info(f"Workflow {workflow_id} cancelled by user {user_id}, {cancelled_count} jobs cancelled")
        
        return True


# 全局工作流管理器实例
workflow_manager = WorkflowManager()

