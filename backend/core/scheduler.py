"""
核心调度器 - 实现分支感知的多租户调度
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
    分支感知调度器
    
    特性：
    1. 同一分支的任务串行执行（FIFO）
    2. 不同分支的任务可以并行执行（受全局worker限制）
    3. 最多3个用户同时有运行中的任务
    4. 第4个及以后的用户需要等待
    """
    
    def __init__(self):
        # 全局任务存储
        self.jobs: Dict[str, Job] = {}
        
        # 按分支组织的任务队列 - 使用 (user_id, branch) 作为key实现用户级别的branch隔离
        self.branch_queues: Dict[tuple, deque] = defaultdict(deque)
        
        # 当前每个分支正在运行的任务 - 使用 (user_id, branch) 作为key
        self.branch_running: Dict[tuple, Optional[str]] = {}
        
        # 按用户组织的任务
        self.user_jobs: Dict[str, Set[str]] = defaultdict(set)
        
        # 当前有运行中任务的用户
        self.active_users: Set[str] = set()
        
        # 等待槽位的用户队列
        self.waiting_users: deque = deque()
        
        # 全局worker信号量
        self.worker_semaphore = asyncio.Semaphore(settings.MAX_WORKERS)
        
        # 运行中的任务数
        self.running_jobs: Set[str] = set()
        
        # 任务执行器映射（job_id -> task）
        self.job_tasks: Dict[str, asyncio.Task] = {}
        
        # 统计信息
        self.total_jobs_processed = 0
        self.total_latency = 0.0
        
        # 调度器主循环任务
        self.scheduler_task: Optional[asyncio.Task] = None
        
        # 停止标志
        self._stop_event = asyncio.Event()
        
        logger.info("BranchAwareScheduler initialized with MAX_WORKERS=%d, MAX_ACTIVE_USERS=%d",
                   settings.MAX_WORKERS, settings.MAX_ACTIVE_USERS)
    
    async def start(self):
        """启动调度器"""
        if self.scheduler_task is None:
            self.scheduler_task = asyncio.create_task(self._scheduler_loop())
            print(f"🚀 [SCHEDULER] Scheduler started! Task: {self.scheduler_task}")
            logger.info("Scheduler started")
        else:
            print(f"⚠️ [SCHEDULER] Scheduler already running! Task: {self.scheduler_task}")
            logger.warning("Scheduler start called but already running")
    
    async def stop(self):
        """停止调度器"""
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
        提交任务到调度器
        
        Args:
            job: 任务对象
            
        Returns:
            job_id
        """
        job_id = job.job_id
        self.jobs[job_id] = job
        self.user_jobs[job.user_id].add(job_id)
        
        # 将任务加入对应分支的队列 - 使用 (user_id, branch) 确保用户级别隔离
        branch_key = (job.user_id, job.branch)
        self.branch_queues[branch_key].append(job_id)
        
        print(f"📥 [SCHEDULER] Job {job_id} submitted to branch '{job.branch}' by user {job.user_id}")
        print(f"📊 [SCHEDULER] User {job.user_id} branch '{job.branch}' queue depth: {len(self.branch_queues[branch_key])}")
        logger.info(f"Job {job_id} submitted to branch '{job.branch}' by user {job.user_id}")
        
        return job_id
    
    async def cancel_job(self, job_id: str, user_id: str) -> bool:
        """
        取消任务（仅当任务还在队列中时）
        
        Args:
            job_id: 任务ID
            user_id: 用户ID（用于权限验证）
            
        Returns:
            是否成功取消
        """
        job = self.jobs.get(job_id)
        if not job:
            return False
        
        # 验证用户权限
        if job.user_id != user_id:
            logger.warning(f"User {user_id} attempted to cancel job {job_id} owned by {job.user_id}")
            return False
        
        # 只能取消PENDING状态的任务
        if job.status != JobStatus.PENDING:
            logger.warning(f"Cannot cancel job {job_id} with status {job.status}")
            return False
        
        # 从分支队列中移除 - 使用 (user_id, branch) key
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
        """调度器主循环"""
        print("🔄 [SCHEDULER] Scheduler loop started!")
        loop_count = 0
        while not self._stop_event.is_set():
            try:
                loop_count += 1
                if loop_count % 100 == 0:  # 每100次循环打印一次
                    print(f"🔄 [SCHEDULER] Loop #{loop_count}: "
                          f"Active Users: {len(self.active_users)}/{settings.MAX_ACTIVE_USERS}, "
                          f"Workers: {len(self.running_jobs)}/{settings.MAX_WORKERS}, "
                          f"Total Jobs: {len(self.jobs)}, "
                          f"Waiting Users: {len(self.waiting_users)}")
                await self._schedule_next_jobs()
                await asyncio.sleep(0.1)  # 避免CPU过载
            except asyncio.CancelledError:
                print("🛑 [SCHEDULER] Scheduler loop cancelled")
                break
            except Exception as e:
                print(f"❌ [SCHEDULER] Error in scheduler loop: {e}")
                logger.error(f"Error in scheduler loop: {e}", exc_info=True)
                await asyncio.sleep(1)
        print("🏁 [SCHEDULER] Scheduler loop ended")
    
    async def _schedule_next_jobs(self):
        """调度下一批任务"""
        
        # 1. 清理已完成任务的用户
        self._cleanup_completed_users()
        
        # 2. 如果有等待的用户，尝试激活
        self._activate_waiting_users()
        
        # 3. 为每个分支尝试调度任务 - branch_key现在是 (user_id, branch) 元组
        for branch_key, queue in list(self.branch_queues.items()):
            if not queue:
                continue
            
            user_id, branch_name = branch_key
            
            # 如果该分支已有任务在运行，跳过
            if self.branch_running.get(branch_key):
                continue
            
            # 获取队列头部的任务
            while queue:
                job_id = queue[0]
                job = self.jobs.get(job_id)
                
                if not job:
                    queue.popleft()
                    continue
                
                # 如果任务已被取消，跳过
                if job.status == JobStatus.CANCELLED:
                    queue.popleft()
                    continue
                
                # 检查用户是否可以执行（活跃用户限制）
                if not self._can_user_execute(job.user_id):
                    print(f"⏸️ [SCHEDULER] User {job.user_id} cannot execute yet (active users limit)")
                    break  # 该用户需要等待
                
                # 检查是否有可用的worker
                if len(self.running_jobs) >= settings.MAX_WORKERS:
                    print(f"⏸️ [SCHEDULER] No available workers ({len(self.running_jobs)}/{settings.MAX_WORKERS})")
                    break  # 等待worker空闲
                
                # 移除队列头部并执行任务
                print(f"✨ [SCHEDULER] Scheduling job {job_id} from user {user_id} branch '{branch_name}'")
                queue.popleft()
                await self._execute_job(job)
                break
    
    def _cleanup_completed_users(self):
        """清理所有任务都已完成的用户"""
        users_to_remove = set()
        for user_id in self.active_users:
            user_job_ids = self.user_jobs.get(user_id, set())
            # 检查是否有未完成的任务（PENDING 或 RUNNING）
            has_active_jobs = any(
                self.jobs.get(jid) and self.jobs[jid].status in [JobStatus.PENDING, JobStatus.RUNNING]
                for jid in user_job_ids
            )
            # 只有当用户所有任务都完成时才移除
            if not has_active_jobs:
                users_to_remove.add(user_id)
                print(f"🧹 [SCHEDULER] User {user_id} removed from active_users (all jobs completed)")
                logger.info(f"User {user_id} removed from active_users (all jobs completed)")
        
        self.active_users -= users_to_remove
    
    def _activate_waiting_users(self):
        """激活等待中的用户"""
        while (len(self.active_users) < settings.MAX_ACTIVE_USERS 
               and self.waiting_users):
            user_id = self.waiting_users.popleft()
            self.active_users.add(user_id)
            print(f"✨ [SCHEDULER] User {user_id} activated from waiting queue ({len(self.active_users)}/{settings.MAX_ACTIVE_USERS} active)")
            logger.info(f"User {user_id} activated from waiting queue")
    
    def _can_user_execute(self, user_id: str) -> bool:
        """
        检查用户是否可以执行任务
        
        Args:
            user_id: 用户ID
            
        Returns:
            是否可以执行
        """
        if user_id in self.active_users:
            return True
        
        if len(self.active_users) < settings.MAX_ACTIVE_USERS:
            self.active_users.add(user_id)
            print(f"👤 [SCHEDULER] User {user_id} added to active users ({len(self.active_users)}/{settings.MAX_ACTIVE_USERS} active)")
            logger.info(f"User {user_id} added to active users ({len(self.active_users)}/{settings.MAX_ACTIVE_USERS})")
            return True
        
        # 用户需要等待
        if user_id not in self.waiting_users:
            self.waiting_users.append(user_id)
            print(f"⏳ [SCHEDULER] User {user_id} added to waiting queue (active users full: {list(self.active_users)})")
            logger.info(f"User {user_id} added to waiting queue (waiting: {len(self.waiting_users)})")
        
        return False
    
    async def _execute_job(self, job: Job):
        """
        执行任务
        
        Args:
            job: 任务对象
        """
        job.status = JobStatus.RUNNING
        job.started_at = datetime.now()
        self.running_jobs.add(job.job_id)
        
        # 使用 (user_id, branch) 作为key标记该分支正在运行任务
        branch_key = (job.user_id, job.branch)
        self.branch_running[branch_key] = job.job_id
        
        print(f"🚀 [SCHEDULER] Starting job {job.job_id} (user: {job.user_id}, branch: {job.branch})")
        logger.info(f"Starting job {job.job_id} (user: {job.user_id}, branch: {job.branch})")
        
        # 创建任务执行协程
        task = asyncio.create_task(self._run_job_with_semaphore(job))
        self.job_tasks[job.job_id] = task
    
    async def _run_job_with_semaphore(self, job: Job):
        """
        使用信号量控制的任务执行
        
        Args:
            job: 任务对象
        """
        print(f"💼 [SCHEDULER] Job {job.job_id} acquired worker semaphore")
        async with self.worker_semaphore:
            try:
                # 导入JobExecutor（避免循环导入）
                from backend.services.job_executor import job_executor
                
                print(f"🔧 [SCHEDULER] Calling job_executor for job {job.job_id}")
                
                # 实际执行任务
                await job_executor.execute_job(job)
                
                print(f"✅ [SCHEDULER] Job {job.job_id} execution completed with status: {job.status}")
                
            except Exception as e:
                print(f"❌ [SCHEDULER] Error executing job {job.job_id}: {e}")
                logger.error(f"Error executing job {job.job_id}: {e}", exc_info=True)
                job.status = JobStatus.FAILED
                job.error = str(e)
                job.completed_at = datetime.now()
            finally:
                # 清理
                print(f"🧹 [SCHEDULER] Cleaning up job {job.job_id}")
                self.running_jobs.discard(job.job_id)
                
                # 使用 (user_id, branch) key 清理 branch_running
                branch_key = (job.user_id, job.branch)
                if self.branch_running.get(branch_key) == job.job_id:
                    self.branch_running[branch_key] = None
                
                self.job_tasks.pop(job.job_id, None)
                
                # 更新统计
                if job.status in [JobStatus.SUCCEEDED, JobStatus.FAILED]:
                    self.total_jobs_processed += 1
                    if job.started_at and job.completed_at:
                        latency = (job.completed_at - job.started_at).total_seconds()
                        self.total_latency += latency
                
                logger.info(f"Job {job.job_id} completed with status {job.status}")
    
    def get_job(self, job_id: str) -> Optional[Job]:
        """获取任务信息"""
        return self.jobs.get(job_id)
    
    def get_user_jobs(self, user_id: str) -> List[Job]:
        """获取用户的所有任务"""
        job_ids = self.user_jobs.get(user_id, set())
        return [self.jobs[jid] for jid in job_ids if jid in self.jobs]
    
    def get_system_stats(self) -> dict:
        """获取系统统计信息"""
        avg_latency = (
            self.total_latency / self.total_jobs_processed
            if self.total_jobs_processed > 0
            else 0.0
        )
        
        # 计算每个分支的队列深度 - 现在包含用户信息
        # key 是 (user_id, branch)，转换为 "user_id:branch" 格式便于显示
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


# 全局调度器实例
scheduler = BranchAwareScheduler()

