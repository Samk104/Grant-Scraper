
from __future__ import annotations
import os
from redis import Redis
from rq_scheduler import Scheduler

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
QUEUE_NAME = os.getenv("RQ_QUEUE", "default")
JOB_ID = os.getenv("RQ_JOB_ID", "weekly_pipeline_job")


FUNC_PATH = os.getenv("RQ_FUNC", "app.tasks.weekly_pipeline")


CRON = os.getenv("RQ_CRON", "*/2 * * * *")  

def main():
    conn = Redis.from_url(REDIS_URL)
    sched = Scheduler(queue_name=QUEUE_NAME, connection=conn)

    
    existing = [j for j in sched.get_jobs() if j.id == JOB_ID]
    for j in existing:
        sched.cancel(j)

    
    sched.cron(
        CRON,
        func=FUNC_PATH,
        args=[],
        kwargs={},
        id=JOB_ID,
        repeat=None,            
        queue_name=QUEUE_NAME,
        use_local_timezone=False,  
        timeout=os.getenv("RQ_DEFAULT_TIMEOUT", "72000"),  
        result_ttl=86400,       
        description="Weekly pipeline job",
    )

    print(f"Seeded RQ scheduler job {JOB_ID} -> {FUNC_PATH} as cron '{CRON}' (UTC)")

if __name__ == "__main__":
    main()
