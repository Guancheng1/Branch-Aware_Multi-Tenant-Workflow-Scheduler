"""
Core scheduler - Implements branch-aware multi-tenant scheduling
"""
import asyncio
from typing import Dict, Set, Optional, List
from collections import defaultdict, deque
from datetime import datetime
import logging

from backend.models.schemas import Job, JobStatus
from backend.core.config import settings

logger = logging.getLogger(__name__)


class BranchAwareScheduler:
    """
    Branch-aware scheduler
    
    Features:
    1. Tasks in the same branch execute serially (FIFO)
    2. Tasks in different branches can execute in parallel (subject to global worker limits)
    3. Maximum 3 users can have running tasks simultaneously
    4. The 4th and subsequent users need to wait
    """
    
    def __init__(self):
        # Global job storage
        self.jobs: Dict[str, Job] = {}
        
        # Branch-organized job queues - use (user_id, branch) as key to implement user-level branch isolation
        self.branch_queues: Dict[tuple, deque] = defaultdict(deque)
        
        # Currently running job for each branch - use (user_id, branch) as key
        self.branch_running: Dict[tuple, Optional[str]] = {}
        
        # User-organized jobs
        self.user_jobs: Dict[str, Set[str]] = defaultdict(set)
        
        # Users currently with running tasks
        self.active_users: Set[str] = set()
        
        # Queue of users waiting for slots
        self.waiting_users: deque = deque()
        
        # Global worker semaphore
        self.worker_semaphore = asyncio.Semaphore(settings.MAX_WORKERS)
        
        # Number of running jobs
        self.running_jobs: Set[str] = set()
        
        # Job executor mapping (job_id -> task)
        self.job_tasks: Dict[str, asyncio.Task] = {}
        
        # Statistics
        self.total_jobs_processed = 0
        self.total_latency = 0.0
        
        # Scheduler main loop task
        self.scheduler_task: Optional[asyncio.Task] = None
        
        # Stop flag
        self._stop_event = asyncio.Event()
        
        logger.info("BranchAwareScheduler initialized with MAX_WORKERS=%d, MAX_ACTIVE_USERS=%d",
                   settings.MAX_WORKERS, settings.MAX_ACTIVE_USERS)
    
    async def start(self):
        """Start scheduler"""
        if self.scheduler_task is None:
            self.scheduler_task = asyncio.create_task(self._scheduler_loop())
            print(f"🚀 [SCHEDULER] Scheduler started! Task: {self.scheduler_task}")
            logger.info("Scheduler started")
        else:
            print(f"⚠️ [SCHEDULER] Scheduler already running! Task: {self.scheduler_task}")
            logger.warning("Scheduler start called but already running")
    
    async def stop(self):
        """Stop scheduler"""
        self._stop_event.set()
        if self.scheduler_task:
            self.scheduler_task.cancel()
            try:
                await self.scheduler_task
            except asyncio.CancelledError:
                pass
        logger.info("Scheduler stopped")
    
    async def submit_job(self, job: Job) -> str:
        """
        Submit job to scheduler
        
        Args:
            job: Job object
            
        Returns:
            job_id
        """
        job_id = job.job_id
        self.jobs[job_id] = job
        self.user_jobs[job.user_id].add(job_id)
        
        # Add job to corresponding branch queue - use (user_id, branch) to ensure user-level isolation
        branch_key = (job.user_id, job.branch)
        self.branch_queues[branch_key].append(job_id)
        
        print(f"📥 [SCHEDULER] Job {job_id} submitted to branch '{job.branch}' by user {job.user_id}")
        print(f"📊 [SCHEDULER] User {job.user_id} branch '{job.branch}' queue depth: {len(self.branch_queues[branch_key])}")
        logger.info(f"Job {job_id} submitted to branch '{job.branch}' by user {job.user_id}")
        
        return job_id
    
    async def cancel_job(self, job_id: str, user_id: str) -> bool:
        """
        Cancel job (only when job is still in queue)
        
        Args:
            job_id: Job ID
            user_id: User ID (for permission verification)
            
        Returns:
            Whether cancellation was successful
        """
        job = self.jobs.get(job_id)
        if not job:
            return False
        
        # Verify user permissions
        if job.user_id != user_id:
            logger.warning(f"User {user_id} attempted to cancel job {job_id} owned by {job.user_id}")
            return False
        
        # Can only cancel PENDING jobs
        if job.status != JobStatus.PENDING:
            logger.warning(f"Cannot cancel job {job_id} with status {job.status}")
            return False
        
        # Remove from branch queue - use (user_id, branch) key
        try:
            branch_key = (job.user_id, job.branch)
            self.branch_queues[branch_key].remove(job_id)
            job.status = JobStatus.CANCELLED
            job.completed_at = datetime.now()
            logger.info(f"Job {job_id} cancelled by user {user_id}")
            return True
        except ValueError:
            return False
    
    async def _scheduler_loop(self):
        """Scheduler main loop"""
        print("🔄 [SCHEDULER] Scheduler loop started!")
        loop_count = 0
        while not self._stop_event.is_set():
            try:
                loop_count += 1
                if loop_count % 100 == 0:  # Print every 100 loops
                    print(f"🔄 [SCHEDULER] Loop #{loop_count}: "
                          f"Active Users: {len(self.active_users)}/{settings.MAX_ACTIVE_USERS}, "
                          f"Workers: {len(self.running_jobs)}/{settings.MAX_WORKERS}, "
                          f"Total Jobs: {len(self.jobs)}, "
                          f"Waiting Users: {len(self.waiting_users)}")
                await self._schedule_next_jobs()
                await asyncio.sleep(0.1)  # Avoid CPU overload
            except asyncio.CancelledError:
                print("🛑 [SCHEDULER] Scheduler loop cancelled")
                break
            except Exception as e:
                print(f"❌ [SCHEDULER] Error in scheduler loop: {e}")
                logger.error(f"Error in scheduler loop: {e}", exc_info=True)
                await asyncio.sleep(1)
        print("🏁 [SCHEDULER] Scheduler loop ended")
    
    async def _schedule_next_jobs(self):
        """Schedule next batch of jobs"""
        
        # 1. Clean up users with completed jobs
        self._cleanup_completed_users()
        
        # 2. If there are waiting users, try to activate them
        self._activate_waiting_users()
        
        # 3. Try to schedule jobs for each branch - branch_key is now (user_id, branch) tuple
        for branch_key, queue in list(self.branch_queues.items()):
            if not queue:
                continue
            
            user_id, branch_name = branch_key
            
            # If this branch already has a running job, skip
            if self.branch_running.get(branch_key):
                continue
            
            # Get the job at the head of the queue
            while queue:
                job_id = queue[0]
                job = self.jobs.get(job_id)
                
                if not job:
                    queue.popleft()
                    continue
                
                # If job was cancelled, skip
                if job.status == JobStatus.CANCELLED:
                    queue.popleft()
                    continue
                
                # Check if user can execute (active user limit)
                if not self._can_user_execute(job.user_id):
                    print(f"⏸️ [SCHEDULER] User {job.user_id} cannot execute yet (active users limit)")
                    break  # This user needs to wait
                
                # Check if there are available workers
                if len(self.running_jobs) >= settings.MAX_WORKERS:
                    print(f"⏸️ [SCHEDULER] No available workers ({len(self.running_jobs)}/{settings.MAX_WORKERS})")
                    break  # Wait for worker to be idle
                
                # Remove from queue head and execute job
                print(f"✨ [SCHEDULER] Scheduling job {job_id} from user {user_id} branch '{branch_name}'")
                queue.popleft()
                await self._execute_job(job)
                break
    
    def _cleanup_completed_users(self):
        """Clean up users whose all jobs are completed"""
        users_to_remove = set()
        for user_id in self.active_users:
            user_job_ids = self.user_jobs.get(user_id, set())
            # Check if there are incomplete jobs (PENDING or RUNNING)
            has_active_jobs = any(
                self.jobs.get(jid) and self.jobs[jid].status in [JobStatus.PENDING, JobStatus.RUNNING]
                for jid in user_job_ids
            )
            # Only remove when all user jobs are completed
            if not has_active_jobs:
                users_to_remove.add(user_id)
                print(f"🧹 [SCHEDULER] User {user_id} removed from active_users (all jobs completed)")
                logger.info(f"User {user_id} removed from active_users (all jobs completed)")
        
        self.active_users -= users_to_remove
    
    def _activate_waiting_users(self):
        """Activate waiting users"""
        while (len(self.active_users) < settings.MAX_ACTIVE_USERS 
               and self.waiting_users):
            user_id = self.waiting_users.popleft()
            self.active_users.add(user_id)
            print(f"✨ [SCHEDULER] User {user_id} activated from waiting queue ({len(self.active_users)}/{settings.MAX_ACTIVE_USERS} active)")
            logger.info(f"User {user_id} activated from waiting queue")
    
    def _can_user_execute(self, user_id: str) -> bool:
        """
        Check if user can execute jobs
        
        Args:
            user_id: User ID
            
        Returns:
            Whether execution is allowed
        """
        if user_id in self.active_users:
            return True
        
        if len(self.active_users) < settings.MAX_ACTIVE_USERS:
            self.active_users.add(user_id)
            print(f"👤 [SCHEDULER] User {user_id} added to active users ({len(self.active_users)}/{settings.MAX_ACTIVE_USERS} active)")
            logger.info(f"User {user_id} added to active users ({len(self.active_users)}/{settings.MAX_ACTIVE_USERS})")
            return True
        
        # User needs to wait
        if user_id not in self.waiting_users:
            self.waiting_users.append(user_id)
            print(f"⏳ [SCHEDULER] User {user_id} added to waiting queue (active users full: {list(self.active_users)})")
            logger.info(f"User {user_id} added to waiting queue (waiting: {len(self.waiting_users)})")
        
        return False
    
    async def _execute_job(self, job: Job):
        """
        Execute job
        
        Args:
            job: Job object
        """
        job.status = JobStatus.RUNNING
        job.started_at = datetime.now()
        self.running_jobs.add(job.job_id)
        
        # Mark this branch as having a running job using (user_id, branch) as key
        branch_key = (job.user_id, job.branch)
        self.branch_running[branch_key] = job.job_id
        
        print(f"🚀 [SCHEDULER] Starting job {job.job_id} (user: {job.user_id}, branch: {job.branch})")
        logger.info(f"Starting job {job.job_id} (user: {job.user_id}, branch: {job.branch})")
        
        # Create job execution coroutine
        task = asyncio.create_task(self._run_job_with_semaphore(job))
        self.job_tasks[job.job_id] = task
    
    async def _run_job_with_semaphore(self, job: Job):
        """
        Job execution with semaphore control
        
        Args:
            job: Job object
        """
        print(f"💼 [SCHEDULER] Job {job.job_id} acquired worker semaphore")
        async with self.worker_semaphore:
            try:
                # Import JobExecutor (avoid circular import)
                from backend.services.job_executor import job_executor
                
                print(f"🔧 [SCHEDULER] Calling job_executor for job {job.job_id}")
                
                # Actually execute job
                await job_executor.execute_job(job)
                
                print(f"✅ [SCHEDULER] Job {job.job_id} execution completed with status: {job.status}")
                
            except Exception as e:
                print(f"❌ [SCHEDULER] Error executing job {job.job_id}: {e}")
                logger.error(f"Error executing job {job.job_id}: {e}", exc_info=True)
                job.status = JobStatus.FAILED
                job.error = str(e)
                job.completed_at = datetime.now()
            finally:
                # Cleanup
                print(f"🧹 [SCHEDULER] Cleaning up job {job.job_id}")
                self.running_jobs.discard(job.job_id)
                
                # Clean up branch_running using (user_id, branch) key
                branch_key = (job.user_id, job.branch)
                if self.branch_running.get(branch_key) == job.job_id:
                    self.branch_running[branch_key] = None
                
                self.job_tasks.pop(job.job_id, None)
                
                # Update statistics
                if job.status in [JobStatus.SUCCEEDED, JobStatus.FAILED]:
                    self.total_jobs_processed += 1
                    if job.started_at and job.completed_at:
                        latency = (job.completed_at - job.started_at).total_seconds()
                        self.total_latency += latency
                
                logger.info(f"Job {job.job_id} completed with status {job.status}")
    
    def get_job(self, job_id: str) -> Optional[Job]:
        """Get job information"""
        return self.jobs.get(job_id)
    
    def get_user_jobs(self, user_id: str) -> List[Job]:
        """Get all user jobs"""
        job_ids = self.user_jobs.get(user_id, set())
        return [self.jobs[jid] for jid in job_ids if jid in self.jobs]
    
    def get_system_stats(self) -> dict:
        """Get system statistics"""
        avg_latency = (
            self.total_latency / self.total_jobs_processed
            if self.total_jobs_processed > 0
            else 0.0
        )
        
        # Calculate queue depth for each branch - now includes user info
        # key is (user_id, branch), convert to "user_id:branch" format for display
        per_branch_depth = {
            f"{user_id}:{branch}": len(queue)
            for (user_id, branch), queue in self.branch_queues.items()
            if queue
        }
        
        return {
            "active_users": len(self.active_users),
            "max_active_users": settings.MAX_ACTIVE_USERS,
            "active_workers": len(self.running_jobs),
            "max_workers": settings.MAX_WORKERS,
            "queue_depth": sum(len(q) for q in self.branch_queues.values()),
            "total_jobs_processed": self.total_jobs_processed,
            "average_job_latency_seconds": avg_latency,
            "per_branch_queue_depth": per_branch_depth,
            "waiting_users": len(self.waiting_users)
        }


# Global scheduler instance
scheduler = BranchAwareScheduler()

