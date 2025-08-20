import os, time, sys, traceback
from redis import Redis
from rq import Worker, Queue, Connection
from logging import getLogger

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
LISTEN = [os.getenv("RQ_QUEUE", "default")]
DEFAULT_TIMEOUT = int(os.getenv("RQ_DEFAULT_TIMEOUT", "72000")) 
logger = getLogger(__name__)

def main():
    while True:
        try:
            conn = Redis.from_url(REDIS_URL)
            with Connection(conn):
                queues = [Queue(n, default_timeout=DEFAULT_TIMEOUT) for n in LISTEN]
                w = Worker(queues)
                logger.info(f"RQ worker listening on {LISTEN} (redis={REDIS_URL}, default_timeout={DEFAULT_TIMEOUT}s)")
                w.work(with_scheduler=False)
        except Exception:
            traceback.print_exc()
            logger.error("Worker crashed; retrying in 5s...", exc_info=True)
            time.sleep(5)

if __name__ == "__main__":
    main()
