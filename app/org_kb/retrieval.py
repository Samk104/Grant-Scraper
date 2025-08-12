from __future__ import annotations
from typing import List, Dict, Any
from app.org_kb.loader import load_org_kb
from app.utils.rag.keyword_matcher import match_keywords, _norm
from app.utils.rag.config import get_retrieval_knobs

def _score(snippet: str, q_terms: set[str], priority: int) -> float:
    s = _norm(snippet)
    score = 0.0
    for t in q_terms:
        if t.lower() in s:
            score += 1.0
    score += max(0.0, 0.3 - (len(s) / 4000.0))
    score += (max(0, min(priority, 10)) * 0.15)
    return score

def retrieve_org_context(grant_text: str, k: int | None = None) -> List[Dict[str, Any]]:
    kb = load_org_kb()
    knobs = get_retrieval_knobs() or {}
    topk = int(knobs.get("org_kb_k", 2)) if k is None else int(k)

    q_terms = set(match_keywords(grant_text, max_terms=10))

    scored: List[tuple[float, Dict[str, Any]]] = []
    for row in kb:
        sc = _score(row["text"], q_terms, row["priority"])
        if sc > 0:
            scored.append((sc, row))

    scored.sort(key=lambda x: x[0], reverse=True)

    results: List[Dict[str, Any]] = []
    for sc, row in scored[:topk]:
        pid = f"{row['doc_id']}#{row['line']}"
        results.append({
            "id": pid,
            "priority": row["priority"],
            "snippet": row["text"],
            "doc": row["doc"],
            "score": float(sc),
        })
    return results
