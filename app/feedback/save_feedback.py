# app/feedback/save.py
from __future__ import annotations
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from app.db.models import Opportunity  # adjust if your model path differs

# The only keys we allow the human to correct (matches your llm_info schema)
ALLOWED_CORRECTION_KEYS = {
    "is_relevant", "location_applicable", "award_amount", "deadline", "explanation"
}

def _validate_corrections(corrections: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not corrections:
        return {}
    bad = set(corrections.keys()) - ALLOWED_CORRECTION_KEYS
    if bad:
        raise ValueError(f"Unsupported correction keys: {sorted(bad)}")
    return corrections

def save_feedback(
    db: Session,
    opportunity_id: int,
    rationale: str,
    corrections: Optional[Dict[str, Any]] = None,
) -> Opportunity:
    """
    Save human feedback for an opportunity without duplicating grant data.
    - Writes `rationale` and (optional) `corrections` into `user_feedback_info`.
    - Sets `user_feedback=True`.
    - Leaves description/url/etc. untouched (we'll use those elsewhere).

    `corrections` can include any subset of:
        is_relevant (bool)
        location_applicable (bool)
        award_amount (str | None)
        deadline (str | None)         # keep as string for now
        explanation (str | None)
    """
    o: Opportunity | None = db.query(Opportunity).get(opportunity_id)
    if not o:
        raise ValueError(f"Opportunity {opportunity_id} not found")

    corr = _validate_corrections(corrections)
    info = dict(o.user_feedback_info or {})
    info["rationale"] = rationale
    if corr:
        # merge/overwrite only provided keys
        prev = dict(info.get("corrections") or {})
        prev.update(corr)
        info["corrections"] = prev
    info["timestamp"] = datetime.now(timezone.utc).isoformat()

    o.user_feedback = True
    o.user_feedback_info = info

    db.add(o)
    db.commit()
    db.refresh(o)
    return o
