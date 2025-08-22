from __future__ import annotations
from datetime import datetime, timedelta, timezone
import hashlib, json, glob, os, logging
import signal
import sys
from typing import Dict, Any

from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.db.database import SessionLocal
from app.db.models import Opportunity
from app.main import run_all_scrapers 
from redis import Redis

logger = logging.getLogger(__name__)

HERE = os.path.dirname(__file__)                 
ROOT = os.path.abspath(os.path.join(HERE, ".."))  
VECTOR_STORE = os.path.join(ROOT, "vector_store")
FEEDBACK_IDS = os.path.join(VECTOR_STORE, "feedback_ids.json")
REBUILD_STATE = os.path.join(VECTOR_STORE, "rebuild_state.json")
ORGKB_DIR = os.path.join(HERE, "org_kb") 

# ---------- Scrape job ----------
def scrape_job() -> Dict[str, Any]:
    """
    Run all scrapers and return a summary of the scrape job.
    """
    summary = run_all_scrapers()
    logger.info("scrape_job done: %s", summary)
    return summary

# ---------- Prune job ----------
def prune_old_grants_job(days: int = 366) -> int:
    """
    Delete grants with scraped_at older than N days and NOT marked as user_feedback.
    (We retain feedback rows as training data.)
    Returns deleted row count.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    deleted = 0
    with SessionLocal() as db:
        q = (db.query(Opportunity)
               .filter(Opportunity.scraped_at < cutoff)
               .filter(Opportunity.user_feedback.is_(None)))
        deleted = q.delete(synchronize_session=False)
        db.commit()
    logger.info("prune_old_grants_job: deleted=%d (older than %d days)", deleted, days)
    return deleted

# ---------- LLM job ----------
def llm_job(max_workers: int = 4) -> None:
    """
    Process all new/unprocessed grants (llm_info IS NULL OR is_relevant IS NULL).
    """
    from app.utils.llm.llm_pipeline import process_new_grants_with_llm
    process_new_grants_with_llm(max_workers=max_workers)
    logger.info("llm_job: completed.")

# ---------- Feedback index: conditional rebuild ----------
def _feedback_db_count(db: Session) -> int:
    return (db.query(Opportunity)
              .filter(or_(Opportunity.description.isnot(None),
                          Opportunity.description != ""))
              .filter(Opportunity.user_feedback.isnot(None)) 
              .count())

def _feedback_indexed_count() -> int:
    if not os.path.exists(FEEDBACK_IDS):
        return 0
    try:
        data = json.load(open(FEEDBACK_IDS, "r", encoding="utf-8")) or []
        return len(data)
    except Exception:
        return 0

def try_feedback_index_job_rebuild() -> bool:
    from app.scripts.rebuild_indexes import rebuild_feedback
    with SessionLocal() as db:
        db_count = _feedback_db_count(db)
    idx_count = _feedback_indexed_count()

    if db_count != idx_count:
        logger.info("Rebuilding feedback index (db=%d, idx=%d)", db_count, idx_count)
        rebuild_feedback()
        return True

    logger.info("Feedback index up-to-date (db=%d, idx=%d)", db_count, idx_count)
    return False

# ---------- Organization Knowledge Base Rebuild based on Hash, index: conditional rebuild ----------
def _hash_orgkb_dir() -> str:
    h = hashlib.sha256()
    for path in sorted(glob.glob(os.path.join(ORGKB_DIR, "*.md"))):
        with open(path, "rb") as f:
            h.update(b"FILE:"); h.update(path.encode("utf-8")); h.update(b"\n"); h.update(f.read())
    return "sha256:" + h.hexdigest()

def _load_state() -> dict:
    if not os.path.exists(REBUILD_STATE):
        return {}
    try:
        return json.load(open(REBUILD_STATE, "r", encoding="utf-8")) or {}
    except Exception:
        return {}

def _save_state(state: dict) -> None:
    os.makedirs(VECTOR_STORE, exist_ok=True)
    tmp = REBUILD_STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, REBUILD_STATE)

def try_orgkb_index_job_rebuild(always: bool = False) -> bool:
    from app.scripts.rebuild_indexes import rebuild_orgkb
    current_hash = _hash_orgkb_dir()
    state = _load_state()
    prev_hash = state.get("orgkb_hash")

    if always or (current_hash != prev_hash):
        logger.info("Rebuilding org-KB index (changed=%s)", current_hash != prev_hash)
        rebuild_orgkb()
        state["orgkb_hash"] = current_hash
        state["last_rebuild_at"] = datetime.now(timezone.utc).isoformat()
        _save_state(state)
        return True

    logger.info("Org-KB index up-to-date")
    return False

# ---------- Orchestrator (weekly pipeline) ----------
WEEKLY_LOCK_KEY = "weekly_pipeline_lock"
WEEKLY_LOCK_TTL_SECONDS = int(os.getenv("WEEKLY_LOCK_TTL_SECONDS", "72000"))

WEEKLY_MIN_INTERVAL_SECONDS = int(os.getenv("WEEKLY_MIN_INTERVAL_SECONDS", str(6 * 24 * 60 * 60)))
WEEKLY_LAST_SUCCESS_TS_KEY = os.getenv("WEEKLY_LAST_SUCCESS_TS_KEY", "weekly:last_success_ts")
_current_lock = None  

def _graceful_lock_release(signum, frame):
    global _current_lock
    try:
        if _current_lock is not None:
            _current_lock.release()
            logger.warning("weekly_pipeline: released lock on signal %s", signum)
    except Exception:
        pass
    sys.exit(1)


def weekly_pipeline() -> dict:
    """
    Check if a weekly run is already in progress (via Redis lock). If not, acquire the lock and run:
    1) Scrape
    2) Prune >366d non-feedback rows
    3) LLM pass on new grants
    4) Conditionally try to rebuild feedback index
    5) Conditionally try to rebuild org-KB index (hash-based)
    """
    
    logger.info("weekly_pipeline: TRIGGERED at %s", datetime.now(timezone.utc).isoformat())
    logger.info(
    "weekly_pipeline config: cooldown=%ss lock_ttl=%ss key=%s",
    WEEKLY_MIN_INTERVAL_SECONDS, WEEKLY_LOCK_TTL_SECONDS, WEEKLY_LAST_SUCCESS_TS_KEY)
    r = Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"))
    
    
    # Throttle: ensure at least WEEKLY_MIN_INTERVAL_SECONDS since last success
    now = datetime.now(timezone.utc).timestamp()
    last_ts = r.get(WEEKLY_LAST_SUCCESS_TS_KEY)
    if last_ts:
        elapsed = now - float(last_ts)
        if elapsed < WEEKLY_MIN_INTERVAL_SECONDS:
            logger.info("weekly_pipeline: cooldown active (elapsed=%.1fs < %ss); skipping.",
                        elapsed, WEEKLY_MIN_INTERVAL_SECONDS)
            return {"skipped": True, "reason": "cooldown: less than %ds since last run" % WEEKLY_MIN_INTERVAL_SECONDS}
    
    
    lock = r.lock(WEEKLY_LOCK_KEY, timeout=WEEKLY_LOCK_TTL_SECONDS)
    if not lock.acquire(blocking=False):
        logger.info("weekly_pipeline: another run is in progress; skipping.")
        return {"skipped": True, "reason": "already_running"}

    global _current_lock
    _current_lock = lock
    signal.signal(signal.SIGTERM, _graceful_lock_release)
    signal.signal(signal.SIGINT, _graceful_lock_release)
    
    logger.info("weekly_pipeline: starting new run.")
    try:
        sc = scrape_job()
        pruned = prune_old_grants_job(days=366)
        llm_job()

        rebuilt_feedback = try_feedback_index_job_rebuild()
        rebuilt_orgkb = try_orgkb_index_job_rebuild(always=False)

        summary = {
            "scrape": sc,
            "pruned": pruned,
            "rebuilt_feedback": rebuilt_feedback,
            "rebuilt_orgkb": rebuilt_orgkb,
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }
        ts = str(datetime.now(timezone.utc).timestamp())
        r.set(WEEKLY_LAST_SUCCESS_TS_KEY, ts)
        logger.info("Weekly pipeline summary: %s", summary)
        return summary
    finally:
        try:
            lock.release()
        except Exception:
            pass
        finally:
            _current_lock = None
