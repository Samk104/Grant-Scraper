from __future__ import annotations
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from app.db.models import Opportunity
import logging

logger = logging.getLogger(__name__)

ALLOWED_CORRECTION_KEYS = {
    "is_relevant", "location_applicable", "award_amount", "deadline", "explanation"
}

def _validate_corrections(corrections: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not corrections:
        return {}
    bad = set(corrections.keys()) - ALLOWED_CORRECTION_KEYS
    if bad:
        logger.error(f"Unsupported correction keys: {sorted(bad)}")
        raise ValueError(f"Unsupported correction keys: {sorted(bad)}")
    return corrections

def save_feedback(
    db: Session,
    opportunity_unique_key: str,
    rationale: str,
    corrections: Optional[Dict[str, Any]] = None,
) -> Opportunity:
    o: Opportunity | None = (
        db.query(Opportunity)
          .filter(Opportunity.unique_key == opportunity_unique_key)
          .first()
    )
    if not o:
        raise ValueError(f"Opportunity with unique key {opportunity_unique_key} not found")

    corr = _validate_corrections(corrections)
    info = dict(o.user_feedback_info or {})
    info["rationale"] = rationale
    if corr:
        prev = dict(info.get("corrections") or {})
        prev.update(corr)
        info["corrections"] = prev
    info["timestamp"] = datetime.now(timezone.utc).isoformat()

    o.user_feedback = True
    o.user_feedback_info = info

    db.commit()
    db.refresh(o)
    return o
