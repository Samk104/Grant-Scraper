from __future__ import annotations
from typing import List, Dict, Any
import os, json
import faiss
from app.utils.rag.embed import embed
from app.utils.rag.config import get_retrieval_knobs

STORE = "vector_store"
ORGKB_INDEX = os.path.join(STORE, "orgkb.faiss")
ORGKB_IDS   = os.path.join(STORE, "orgkb_ids.json")

def retrieve_org_context(grant_text: str, k: int | None = None) -> List[Dict[str, Any]]:
    
    knobs = get_retrieval_knobs() or {}
    topk = int(knobs.get("org_kb_k", 2)) if k is None else int(k)

    
    if not os.path.exists(ORGKB_INDEX) or not os.path.exists(ORGKB_IDS):
        return []

    
    index = faiss.read_index(ORGKB_INDEX)
    meta_list: list[dict] = json.load(open(ORGKB_IDS, "r", encoding="utf-8")) or []
    if not meta_list:
        return []

    
    
    idmap: dict[int, dict] = {int(m["id"]): m for m in meta_list if "id" in m}

    
    qv = embed([grant_text])  
    scores, ids = index.search(qv, topk)

    results: List[Dict[str, Any]] = []
    
    for score, fid in zip(scores[0], ids[0]):
        fid = int(fid)
        if fid == -1:
            continue

        m = idmap.get(fid)
        if not m:
            continue

        results.append({
            "id": f"{m.get('doc_id', 'orgkb')}#{m.get('chunk', 0)}",
            "priority": int(m.get("priority", 0)),
            "snippet": m.get("text", ""),
            "doc": m.get("file"),
            "score": float(score),
        })

    return results
