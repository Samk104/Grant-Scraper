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
    # Get retrieval limit (defaults to 2 unless overridden)
    knobs = get_retrieval_knobs() or {}
    topk = int(knobs.get("org_kb_k", 2)) if k is None else int(k)

    # Bail if index or metadata file missing
    if not os.path.exists(ORGKB_INDEX) or not os.path.exists(ORGKB_IDS):
        return []

    # Load FAISS index + metadata
    index = faiss.read_index(ORGKB_INDEX)
    meta_list: list[dict] = json.load(open(ORGKB_IDS, "r", encoding="utf-8")) or []
    if not meta_list:
        return []

    # Map faiss_id → meta row
    # Your builder writes: {"id", "file", "doc_id", "priority", "chunk", "text"}
    idmap: dict[int, dict] = {int(m["id"]): m for m in meta_list if "id" in m}

    # Embed query text and search top-k
    qv = embed([grant_text])  # shape (1, d)
    scores, ids = index.search(qv, topk)

    results: List[Dict[str, Any]] = []
    # Zip scores and ids to preserve alignment and skip -1 results
    for score, fid in zip(scores[0], ids[0]):
        fid = int(fid)
        if fid == -1:
            continue

        m = idmap.get(fid)
        if not m:
            continue

        results.append({
            # Build a stable readable ID: doc_id#chunk
            "id": f"{m.get('doc_id', 'orgkb')}#{m.get('chunk', 0)}",
            # Priority now always present from your rebuild script
            "priority": int(m.get("priority", 0)),
            # Short preview snippet (first 200 chars from builder)
            "snippet": m.get("text", ""),
            # Original file name for debugging
            "doc": m.get("file"),
            # FAISS similarity score
            "score": float(score),
        })

    return results
