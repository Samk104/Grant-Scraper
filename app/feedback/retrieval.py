from __future__ import annotations
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from app.db.models import Opportunity
from app.utils.rag.keyword_matcher import match_keywords
from app.utils.rag.text_utils import clean_text  # if you don’t have this yet, replace with a simple strip()

def _merge_labels(llm_info: Dict[str, Any] | None, corrections: Dict[str, Any] | None) -> Dict[str, Any]:
    base = (llm_info or {}).copy()
    for k, v in (corrections or {}).items():
        base[k] = v
    keep = {"is_relevant","location_applicable","award_amount","deadline","explanation"}
    return {k: base.get(k) for k in keep}

def _score_example(query_terms: set[str], example_text: str, scraped_at: str | None) -> float:
    ex_terms = set(match_keywords(example_text or "", max_terms=8))
    overlap = len(query_terms & ex_terms)
    recency_bonus = 0.0
    try:
        if scraped_at:
            days = max(0, (datetime.now(timezone.utc) - datetime.fromisoformat(scraped_at)).days)
            recency_bonus = max(0.0, 0.9 - min(days, 90) * (0.9 / 90.0))
    except Exception:
        pass
    return overlap + recency_bonus


def retrieve_feedback_examples(db: Session, grant_text: str, k: int = 3) -> List[Dict[str, Any]]:
    """
    Pull top-k user_feedback examples by simple keyword overlap + recency.
    No embeddings yet; fast and dependency-free.
    """
    q = (
        db.query(Opportunity)
          .filter(Opportunity.user_feedback == True)
          .filter(Opportunity.description.isnot(None))
          .order_by(Opportunity.id.desc())   # newest first fallback
          .limit(200)                        # cap scan size
    )
    query_terms = set(match_keywords(grant_text, max_terms=8))
    scored: list[tuple[float, Opportunity]] = []

    for opp in q:
        desc = (opp.description or "").strip()
        s = _score_example(query_terms, desc, getattr(opp, "scraped_at", None))
        scored.append((s, opp))

    scored.sort(key=lambda x: x[0], reverse=True)

    results: List[Dict[str, Any]] = []
    for s, opp in scored[:k]:
        ufi = opp.user_feedback_info or {}
        final_labels = _merge_labels(opp.llm_info, ufi.get("corrections"))
        snippet = (desc[:900] + "…") if len(desc) > 900 else desc
        results.append({
            "id": opp.id,
            "url": opp.url,
            "score": float(s),
            "snippet": snippet,
            "final_labels": final_labels,
            "rationale": ufi.get("rationale"),
            "timestamp": ufi.get("timestamp"),
        })
    return results
