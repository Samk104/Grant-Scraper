import os, time, sys, traceback
from redis import Redis
from rq import Worker, Queue, Connection

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
LISTEN = [os.getenv("RQ_QUEUE", "default")]

def main():
    while True:
        try:
            conn = Redis.from_url(REDIS_URL)
            with Connection(conn):
                w = Worker([Queue(n) for n in LISTEN])
                print(f"RQ worker listening on {LISTEN} (redis={REDIS_URL})")
                w.work(with_scheduler=False)
        except Exception:
            traceback.print_exc()
            print("Worker crashed; retrying in 5s...", file=sys.stderr)
            time.sleep(5)

if __name__ == "__main__":
    main()
