from __future__ import annotations
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from app.db.models import Opportunity
import logging

logger = logging.getLogger(__name__)


ALLOWED_CORRECTION_KEYS = {
    "url", "grant_amount", "tags", "deadline", "email", "is_relevant"
}


COLUMN_FIELD_MAP = {
    "url": "url",
    "grant_amount": "grant_amount",
    "tags": "tags",
    "deadline": "deadline",
    "email": "email",
    "is_relevant": "is_relevant",
}

def _validate_corrections(corrections: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not corrections:
        return {}
    bad = set(corrections.keys()) - ALLOWED_CORRECTION_KEYS
    if bad:
        logger.error(f"Unsupported correction keys: {sorted(bad)}")
        raise ValueError(f"Unsupported correction keys: {sorted(bad)}")
    return corrections

def try_to_bool(v: Any) -> Optional[bool]:
    if isinstance(v, bool):
        return v
    if v is None:
        return None
    s = str(v).strip().lower()
    if s in {"True", "true","t","yes","y","1"}: return True
    if s in {"False","false","f","no","n","0"}: return False
    return None 

def _normalize_for_columns(key: str, val: Any) -> Any:
    if key == "tags":
        if isinstance(val, (list, tuple)):
            joined = ", ".join([str(x).strip() for x in val if str(x).strip()])
            return joined or None
        return (str(val).strip() or None) if val is not None else None

    if key in {"url", "grant_amount", "deadline", "email"}:
        return (str(val).strip() or None) if val is not None else None

    if key == "is_relevant":
        return try_to_bool(val)

    return val

def save_feedback(
    db: Session,
    opportunity_unique_key: str,
    user_feedback: bool, # Based on if user agrees with the LLM's assessment
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
    
    
    explicit_relevance: Optional[bool] = None

    if "is_relevant" in corr:
        explicit_relevance = _normalize_for_columns("is_relevant", corr["is_relevant"])
    else:
        if user_feedback is False:
            base = o.is_relevant  
            if base is None:
                try:
                    base = (o.llm_info or {}).get("is_relevant")
                except Exception:
                    base = None
            if base is not None:
                explicit_relevance = (not bool(base))

    with db.begin():
        o.user_feedback = user_feedback
        o.user_feedback_info = info

        for k, v in corr.items():
            col = COLUMN_FIELD_MAP.get(k)
            if col:
                norm_val = _normalize_for_columns(k, v)
                if norm_val is not None:
                    setattr(o, col, norm_val)

        if explicit_relevance is not None:
            o.is_relevant = explicit_relevance

        db.flush()
        db.refresh(o)

    return o
    
    


