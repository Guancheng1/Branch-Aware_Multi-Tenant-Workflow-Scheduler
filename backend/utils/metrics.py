"""
Prometheus指标定义
"""
from prometheus_client import Counter, Gauge, Histogram
import logging

logger = logging.getLogger(__name__)

# 任务指标
jobs_total = Counter(
    'jobs_total',
    'Total number of jobs',
    ['user_id', 'job_type', 'status']
)

jobs_active = Gauge(
    'jobs_active',
    'Number of active jobs',
    ['user_id', 'branch']
)

job_duration_seconds = Histogram(
    'job_duration_seconds',
    'Job execution duration in seconds',
    ['job_type', 'status'],
    buckets=[1, 5, 10, 30, 60, 120, 300, 600, 1800, 3600]
)

# 调度器指标
queue_depth = Gauge(
    'queue_depth',
    'Number of jobs in queue',
    ['branch']
)

active_users = Gauge(
    'active_users',
    'Number of active users'
)

waiting_users = Gauge(
    'waiting_users',
    'Number of waiting users'
)

active_workers = Gauge(
    'active_workers',
    'Number of active workers'
)

# 系统指标
system_errors = Counter(
    'system_errors_total',
    'Total number of system errors',
    ['component', 'error_type']
)


def record_job_start(user_id: str, job_type: str, branch: str):
    """记录任务开始"""
    try:
        jobs_active.labels(user_id=user_id, branch=branch).inc()
    except Exception as e:
        logger.error(f"Error recording job start: {e}")


def record_job_complete(user_id: str, job_type: str, branch: str, status: str, duration: float):
    """记录任务完成"""
    try:
        jobs_active.labels(user_id=user_id, branch=branch).dec()
        jobs_total.labels(user_id=user_id, job_type=job_type, status=status).inc()
        job_duration_seconds.labels(job_type=job_type, status=status).observe(duration)
    except Exception as e:
        logger.error(f"Error recording job complete: {e}")


def update_queue_metrics(branch_queues: dict):
    """更新队列指标"""
    try:
        for branch, queue in branch_queues.items():
            queue_depth.labels(branch=branch).set(len(queue))
    except Exception as e:
        logger.error(f"Error updating queue metrics: {e}")


def update_system_metrics(stats: dict):
    """更新系统指标"""
    try:
        active_users.set(stats.get('active_users', 0))
        waiting_users.set(stats.get('waiting_users', 0))
        active_workers.set(stats.get('active_workers', 0))
    except Exception as e:
        logger.error(f"Error updating system metrics: {e}")


def record_error(component: str, error_type: str):
    """记录错误"""
    try:
        system_errors.labels(component=component, error_type=error_type).inc()
    except Exception as e:
        logger.error(f"Error recording error: {e}")


