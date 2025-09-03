from __future__ import annotations
from typing import List, Dict, Any
import os, json
import faiss
from sqlalchemy.orm import Session
from app.db.models import Opportunity
from app.utils.rag.embed import embed
from app.utils.rag.text_utils import clean_text  

STORE = "vector_store"
FEEDBACK_INDEX = os.path.join(STORE, "feedback.faiss")
FEEDBACK_IDS   = os.path.join(STORE, "feedback_ids.json")

def _compose_final_labels(opp: Opportunity, corrections: Dict[str, Any] | None) -> Dict[str, Any]:
    llm_info: Dict[str, Any] = (opp.llm_info or {})
    corr: Dict[str, Any] = (corrections or {})

    final_is_relevant = opp.is_relevant

    if "location_applicable" in corr:
        final_location_applicable = corr.get("location_applicable")
    else:
        final_location_applicable = llm_info.get("location_applicable")

   
    final_grant_amount = None
    grant_amount = getattr(opp, "grant_amount", None)
    if grant_amount and grant_amount != "Not Available":
        final_grant_amount = grant_amount
    elif "grant_amount" in corr:
        final_grant_amount = corr.get("grant_amount")
    else:
        final_grant_amount = llm_info.get("grant_amount", llm_info.get("award_amount"))

   
    if "deadline" in corr:
        final_deadline = corr.get("deadline")
    else:
        final_deadline = llm_info.get("deadline")

    final_explanation = llm_info.get("explanation")

    return {
        "is_relevant": final_is_relevant,
        "location_applicable": final_location_applicable,
        "grant_amout": final_grant_amount,
        "deadline": final_deadline,
        "explanation": final_explanation,
    }


def _load_index_and_meta():
    
    if not os.path.exists(FEEDBACK_INDEX):
        return None, {}
    index = faiss.read_index(FEEDBACK_INDEX)

    
    
    meta_list: list[dict] = []
    if os.path.exists(FEEDBACK_IDS):
        meta_list = json.load(open(FEEDBACK_IDS, "r", encoding="utf-8")) or []

    idmap: dict[int, dict] = {
        int(m["faiss_id"]): {
            "unique_key": m["unique_key"],
            "url": m.get("url")
        }
        for m in meta_list
        if "faiss_id" in m and "unique_key" in m
    }
    return index, idmap

def retrieve_feedback_examples(db: Session, grant_text: str, k: int = 3) -> List[Dict[str, Any]]:
    index, idmap = _load_index_and_meta()
    if index is None or not idmap:
        return []

    
    qv = embed([grant_text])  
    scores, ids = index.search(qv, k)

    out: List[Dict[str, Any]] = []
    for faiss_id, score in zip(ids[0], scores[0]):
        fid = int(faiss_id)
        if fid == -1:
            continue

        meta = idmap.get(fid)
        if not meta:
            continue

        
        opp = db.query(Opportunity).filter(Opportunity.unique_key == meta["unique_key"]).first()
        if not opp:
            continue
        
        if not getattr(opp, "user_feedback", False):
            continue

        
        ufi = opp.user_feedback_info or {}
        final_labels = _compose_final_labels(opp, ufi.get("corrections"))
        
        desc = clean_text(opp.description or "")
        snippet = desc[:900] + ("…" if len(desc) > 900 else "")

        out.append({
            "id": opp.id,
            "unique_key": opp.unique_key,
            "url": meta.get("url") or opp.url,
            "score": float(score),
            "snippet": snippet,
            "final_labels": final_labels,
            "rationale": ufi.get("rationale"),
            "timestamp": ufi.get("timestamp"),
        })

    
    return out[:k]
