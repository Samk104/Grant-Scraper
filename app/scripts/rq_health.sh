#!/usr/bin/env bash
set -euo pipefail

REDIS_SVC=redis
SCHED_SVC=rqscheduler
WORKER_SVC=rq_worker
QUEUE=default
COOLDOWN_KEY="weekly:last_success_ts"
LOCK_KEY="weekly_pipeline_lock"

green() { printf "\033[32m%s\033[0m\n" "$*"; }
yellow(){ printf "\033[33m%s\033[0m\n" "$*"; }
red()   { printf "\033[31m%s\033[0m\n" "$*"; }

section(){ echo; echo "=== $* ==="; }

section "Containers"
docker compose ps "$REDIS_SVC" "$SCHED_SVC" "$WORKER_SVC" || true

section "Seeded schedule"
if ! out=$(docker compose exec -T $REDIS_SVC redis-cli ZRANGE rq:scheduler:scheduled_jobs 0 -1 WITHSCORES); then
  red "Redis not reachable"
  exit 1
fi
echo "$out"
JOB_ID=$(echo "$out" | sed -n '1p' | tr -d '\r')
SCORE=$(echo "$out" | sed -n '2p' | tr -d '\r')

if [[ -z "$JOB_ID" || -z "$SCORE" ]]; then
  red "No scheduled job found in rq:scheduler:scheduled_jobs"
else
  # Convert epoch -> ISO via the app container's Python
  WHEN=$(docker compose run --rm -T app python - <<PY
import datetime, sys
print(datetime.datetime.utcfromtimestamp(float("$SCORE")).isoformat()+"Z")
PY
  )
  green "Found scheduled job: $JOB_ID"
  echo "Next fire (UTC): $WHEN"
fi

section "Queue head (pending jobs)"
docker compose exec -T $REDIS_SVC redis-cli LLEN rq:queue:$QUEUE
docker compose exec -T $REDIS_SVC redis-cli LRANGE rq:queue:$QUEUE 0 4 || true

section "Cooldown key"
LAST_TS=$(docker compose exec -T $REDIS_SVC redis-cli GET "$COOLDOWN_KEY" | tr -d '\r')
echo "raw $COOLDOWN_KEY = ${LAST_TS:-<nil>}"
if [[ "$LAST_TS" != "(nil)" && -n "$LAST_TS" ]]; then
  docker compose run --rm -T app python - <<PY
import time, datetime
now = time.time()
last = float("$LAST_TS")
elapsed = now - last
print("Last success (UTC):", datetime.datetime.utcfromtimestamp(last).isoformat()+"Z")
print("Elapsed since last success (s):", int(elapsed))
PY
fi

section "Lock key"
docker compose exec -T $REDIS_SVC redis-cli GET "$LOCK_KEY" | sed 's/^/value: /'
docker compose exec -T $REDIS_SVC redis-cli TTL "$LOCK_KEY" | sed 's/^/ttl:   /'

section "Worker env (sanity)"
docker compose exec -T $WORKER_SVC printenv | grep -E 'REDIS_URL|WEEKLY_|RQ_DEFAULT_TIMEOUT' || true

section "Scheduler registry (Python view)"
docker compose run --rm -T app python - <<'PY'
from redis import Redis
from rq_scheduler import Scheduler
r = Redis.from_url("redis://redis:6379/0")
s = Scheduler(connection=r)
print([(j.id, j.func_name) for j in s.get_jobs()])
PY
