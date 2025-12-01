"""
Workflow manager - Manages DAG workflows
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
    """Workflow manager"""
    
    def __init__(self):
        self.workflows: Dict[str, Workflow] = {}
        self.workflow_jobs: Dict[str, List[str]] = defaultdict(list)  # workflow_id -> job_ids
        self.node_to_job: Dict[str, str] = {}  # node_id -> job_id
        logger.info("WorkflowManager initialized")
    
    async def create_workflow(self, workflow: Workflow) -> str:
        """
        Create and start workflow
        
        Args:
            workflow: Workflow object
            
        Returns:
            workflow_id
        """
        workflow_id = workflow.workflow_id
        self.workflows[workflow_id] = workflow
        
        logger.info(f"Creating workflow {workflow_id} with {len(workflow.nodes)} nodes")
        
        # Validate DAG
        if not self._validate_dag(workflow.nodes):
            raise ValueError("Invalid DAG: contains cycles or invalid dependencies")
        
        # Start workflow execution
        asyncio.create_task(self._execute_workflow(workflow))
        
        return workflow_id
    
    def _validate_dag(self, nodes: List[WorkflowNode]) -> bool:
        """
        Validate DAG validity (acyclic graph)
        
        Args:
            nodes: Node list
            
        Returns:
            Whether it's valid
        """
        # Build adjacency list
        node_ids = {node.node_id for node in nodes}
        graph = {node.node_id: node.depends_on for node in nodes}
        
        # Check if all dependencies exist (only check workflow internal dependencies)
        for node in nodes:
            for dep in node.depends_on:
                # If dependency starts with "job_", it's an external job reference, skip check
                if dep.startswith("job_"):
                    continue
                # Otherwise it should be a workflow internal node_id
                if dep not in node_ids:
                    logger.error(f"Node {node.node_id} depends on non-existent node {dep}")
                    return False
        
        # Check for cycles (only check workflow internal dependencies)
        # Only build dependency relationships between internal nodes
        internal_graph = {}
        for node in nodes:
            internal_deps = [dep for dep in node.depends_on if dep in node_ids]
            internal_graph[node.node_id] = internal_deps
        
        visited = set()
        rec_stack = set()
        
        def has_cycle(node_id):
            visited.add(node_id)
            rec_stack.add(node_id)
            
            for neighbor in internal_graph.get(node_id, []):
                if neighbor not in visited:
                    if has_cycle(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True
            
            rec_stack.remove(node_id)
            return False
        
        for node_id in internal_graph:
            if node_id not in visited:
                if has_cycle(node_id):
                    logger.error("DAG contains cycle")
                    return False
        
        return True
    
    async def _execute_workflow(self, workflow: Workflow):
        """
        Execute workflow
        
        Args:
            workflow: Workflow object
        """
        workflow.status = WorkflowStatus.RUNNING
        workflow.started_at = datetime.now()
        
        try:
            # Build dependency graph
            node_map = {node.node_id: node for node in workflow.nodes}
            completed_nodes: Set[str] = set()
            failed_nodes: Set[str] = set()
            running_nodes: Set[str] = set()
            
            # Continue execution until all nodes are completed or failed
            while len(completed_nodes) + len(failed_nodes) < len(workflow.nodes):
                # Find nodes that can be executed (dependencies completed)
                ready_nodes = []
                for node in workflow.nodes:
                    if (node.node_id not in completed_nodes 
                        and node.node_id not in failed_nodes
                        and node.node_id not in running_nodes):
                        # Check dependencies
                        deps_satisfied = True
                        for dep in node.depends_on:
                            if dep in node_map:
                                # Dependency is a workflow internal node
                                if dep not in completed_nodes:
                                    deps_satisfied = False
                                    break
                            else:
                                # Dependency is an external existing job (format: job_xxx)
                                # Extract job_id from node_id
                                if dep.startswith("job_"):
                                    dep_job_id = dep[4:]  # Remove "job_" prefix
                                    dep_job = scheduler.get_job(dep_job_id)
                                    if not dep_job or dep_job.status != JobStatus.SUCCEEDED:
                                        deps_satisfied = False
                                        break
                                else:
                                    # Unknown dependency format, consider unsatisfied
                                    deps_satisfied = False
                                    break
                        
                        if deps_satisfied:
                            ready_nodes.append(node)
                
                # Submit ready nodes
                for node in ready_nodes:
                    running_nodes.add(node.node_id)
                    asyncio.create_task(
                        self._execute_node(workflow, node, completed_nodes, failed_nodes, running_nodes)
                    )
                
                # Update progress
                self._update_workflow_progress(workflow)
                
                # Wait for a while before checking again
                await asyncio.sleep(0.5)
            
            # Check final status
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
        Execute single node
        
        Args:
            workflow: Workflow object
            node: Node object
            completed_nodes: Set of completed nodes
            failed_nodes: Set of failed nodes
            running_nodes: Set of running nodes
        """
        try:
            print(f"🌳 [WORKFLOW] Executing node {node.node_id} in workflow {workflow.workflow_id}")
            logger.info(f"Executing node {node.node_id} in workflow {workflow.workflow_id}")
            
            # Create job
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
            
            # Submit to scheduler
            job_id = await scheduler.submit_job(job)
            self.workflow_jobs[workflow.workflow_id].append(job_id)
            workflow.job_ids.append(job_id)
            self.node_to_job[node.node_id] = job_id
            
            print(f"📤 [WORKFLOW] Job {job_id} submitted to scheduler")
            
            # Wait for job completion
            iteration = 0
            while True:
                job = scheduler.get_job(job_id)
                if not job:
                    print(f"⚠️ [WORKFLOW] Job {job_id} not found in scheduler")
                    break
                
                if iteration % 10 == 0:  # Print every 5 seconds
                    print(f"⏳ [WORKFLOW] Waiting for job {job_id}, status: {job.status}, progress: {job.progress_percent:.1f}%")
                
                if job.status in [JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED]:
                    print(f"🏁 [WORKFLOW] Job {job_id} finished with status: {job.status}")
                    break
                
                # Note: Scheduler now automatically executes jobs, no need to manually call executor here
                
                await asyncio.sleep(0.5)
                iteration += 1
            
            # Check final status
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
        """Update workflow progress"""
        if not workflow.job_ids:
            workflow.progress_percent = 0.0
            return
        
        # Calculate average progress of all jobs
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
        """Get workflow"""
        return self.workflows.get(workflow_id)
    
    def get_workflow_progress(self, workflow_id: str) -> Optional[WorkflowProgress]:
        """Get workflow progress"""
        workflow = self.workflows.get(workflow_id)
        if not workflow:
            return None
        
        # Get progress of all jobs
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
        """Get all user workflows"""
        return [
            wf for wf in self.workflows.values()
            if wf.user_id == user_id
        ]
    
    async def cancel_workflow(self, workflow_id: str, user_id: str) -> bool:
        """
        Cancel workflow
        
        Args:
            workflow_id: Workflow ID
            user_id: User ID
            
        Returns:
            Whether cancellation was successful
        """
        workflow = self.workflows.get(workflow_id)
        if not workflow:
            return False
        
        if workflow.user_id != user_id:
            logger.warning(f"User {user_id} attempted to cancel workflow {workflow_id} owned by {workflow.user_id}")
            return False
        
        if workflow.status not in [WorkflowStatus.PENDING, WorkflowStatus.RUNNING]:
            return False
        
        # Cancel all related jobs
        cancelled_count = 0
        for job_id in workflow.job_ids:
            if await scheduler.cancel_job(job_id, user_id):
                cancelled_count += 1
        
        workflow.status = WorkflowStatus.CANCELLED
        workflow.completed_at = datetime.now()
        
        logger.info(f"Workflow {workflow_id} cancelled by user {user_id}, {cancelled_count} jobs cancelled")
        
        return True


# Global workflow manager instance
workflow_manager = WorkflowManager()

