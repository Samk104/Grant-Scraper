
import os, time
from redis import Redis
from rq import Queue
from rq_scheduler import Scheduler
from app.tasks import weekly_pipeline
import logging

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
QUEUE_NAME = os.getenv("RQ_QUEUE", "default")
JOB_ID = "weekly_pipeline_job"

def _cancel_existing_job(sched: Scheduler, job_id: str) -> None:
    try:
        jobs = sched.get_jobs()             
    except TypeError:
        
        jobs = sched.get_jobs(with_times=False)

    for j in jobs:
        if getattr(j, "id", None) == job_id:
            
            try:
                sched.cancel(j)             
            except Exception:
                try:
                    sched.cancel_job(j.id)  
                except Exception:
                    pass

def ensure_job(sched: Scheduler, q: Queue):
    _cancel_existing_job(sched, JOB_ID)

    
    
    sched.cron(
        "0 3 * * 6", # Every Saturday at 03:00 UTC
        func=weekly_pipeline,
        args=[],
        kwargs={},
        repeat=None,
        queue_name=q.name,
        id=JOB_ID,
        use_local_timezone=False,
    )
    logger.info("Scheduled weekly_pipeline at 07:00 UTC Sundays.")

if __name__ == "__main__":
    conn = Redis.from_url(REDIS_URL)
    q = Queue(QUEUE_NAME, connection=conn)
    sched = Scheduler(queue=q, connection=conn)
    ensure_job(sched, q)

    
    try:
        while True:
            sched.run(burst=False)
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Scheduler stopped.")
