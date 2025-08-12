from __future__ import annotations
from typing import List, Dict, Any
import os, json
import faiss
from sqlalchemy.orm import Session
from app.db.models import Opportunity
from app.utils.rag.embed import embed
from app.utils.rag.text_utils import clean_text  # optional for cleaner snippets

STORE = "vector_store"
FEEDBACK_INDEX = os.path.join(STORE, "feedback.faiss")
FEEDBACK_IDS   = os.path.join(STORE, "feedback_ids.json")

def _merge_labels(llm_info: Dict[str, Any] | None, corrections: Dict[str, Any] | None) -> Dict[str, Any]:
    base = (llm_info or {}).copy()
    for k, v in (corrections or {}).items():
        base[k] = v
    keep = {"is_relevant","location_applicable","award_amount","deadline","explanation"}
    return {k: base.get(k) for k in keep}

def _load_index_and_meta():
    # Bail early if no index
    if not os.path.exists(FEEDBACK_INDEX):
        return None, {}
    index = faiss.read_index(FEEDBACK_INDEX)

    # Load meta and map faiss_id → unique_key + url
    # Builder writes: {"faiss_id", "unique_key", "url"}
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

    # Embed query and search top-k
    qv = embed([grant_text])  # (1, d)
    scores, ids = index.search(qv, k)

    out: List[Dict[str, Any]] = []
    for faiss_id, score in zip(ids[0], scores[0]):
        fid = int(faiss_id)
        if fid == -1:
            continue

        meta = idmap.get(fid)
        if not meta:
            continue

        # Lookup opportunity by unique_key from meta
        opp = db.query(Opportunity).filter(Opportunity.unique_key == meta["unique_key"]).first()
        if not opp:
            continue

        # Merge LLM output with any user corrections
        ufi = opp.user_feedback_info or {}
        final_labels = _merge_labels(opp.llm_info, ufi.get("corrections"))

        # Clean + trim snippet for prompt
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

    # Enforce cap in case caller forgets
    return out[:k]
