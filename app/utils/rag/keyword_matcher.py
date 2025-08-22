from __future__ import annotations
from typing import Iterable, List, Tuple
import re
import yaml
from pathlib import Path

from app.utils.rag.config import get_keywords

_WORD = re.compile(r"\w+", re.UNICODE)


def _load_synonyms() -> dict:
    path = Path(__file__).parent.parent.parent / "configs" / "keyword_synonyms.yml"
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("synonyms", {})

SYNONYMS = _load_synonyms()  


def _filtered_synonyms() -> dict:
    core = set(get_keywords().get("core", []))
    return {k: v for k, v in SYNONYMS.items() if v in core}

def validate_synonyms(strict: bool = False) -> list[str]:
    core = set(get_keywords().get("core", []))
    invalid = sorted({v for v in SYNONYMS.values() if v not in core})
    if invalid and strict:
        raise ValueError(f"Synonym canonical(s) not in keywords.core: {invalid}")
    return invalid

def _norm(text: str) -> str:
    return " ".join(_WORD.findall((text or "").lower()))

def _find_matches(text: str, terms: Iterable[str]) -> List[Tuple[str, int]]:
    hits: List[Tuple[str, int]] = []
    for t in terms:
        tt = (t or "").strip()
        if not tt:
            continue
        i = text.find(tt.lower())
        if i != -1:
            hits.append((t, i))
    hits.sort(key=lambda x: x[1])
    return hits

def _overlaps(existing: List[str], cand: str) -> bool:
    cl = (cand or "").lower()
    return any((cl in e.lower()) or (e.lower() in cl) for e in existing)

def match_keywords(grant_text: str, max_terms: int = 4) -> List[str]:
    kws = get_keywords()
    text = _norm(grant_text)
    syn = _filtered_synonyms()

    
    injected: List[str] = []
    for phrase, canonical in syn.items():
        if phrase in text and canonical not in injected:
            injected.append(canonical)

    
    core_hits = _find_matches(text, kws.get("core", []))
    selected: List[str] = [t for t, _ in core_hits]

    
    for term in injected:
        if len(selected) >= max_terms:
            break
        if term not in selected and not _overlaps(selected, term):
            selected.append(term)

    if len(selected) >= max_terms:
        return selected[:max_terms]

    
    expanded_hits = _find_matches(text, kws.get("expanded", []))
    for t, _ in expanded_hits:
        if len(selected) >= max_terms:
            break
        if t not in selected and not _overlaps(selected, t):
            selected.append(t)

    return selected[:max_terms]
