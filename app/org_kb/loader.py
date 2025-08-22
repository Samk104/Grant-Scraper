from __future__ import annotations
from pathlib import Path
from functools import lru_cache
import yaml
import re
from typing import Dict, Any, List

ORG_KB_DIR = Path(__file__).parent
FRONT_RE = re.compile(r"^---\s*$")

def _parse_front_matter(text: str) -> tuple[Dict[str, Any], str]:

    lines = text.splitlines()
    if len(lines) >= 3 and FRONT_RE.match(lines[0]):
        for i in range(1, len(lines)):
            if FRONT_RE.match(lines[i]):
                raw_yaml = "\n".join(lines[1:i])
                body = "\n".join(lines[i+1:])
                meta = yaml.safe_load(raw_yaml) or {}
                return meta, body
    return {}, text

def _iter_md_files():
    for p in ORG_KB_DIR.glob("*.md"):
        if p.name.startswith("_"):
            continue
        yield p

@lru_cache(maxsize=1)
def load_org_kb() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    for p in _iter_md_files():
        raw = p.read_text(encoding="utf-8")
        meta, body = _parse_front_matter(raw)

        doc_id = str(meta.get("id") or p.stem).strip()
        try:
            priority = int(meta.get("priority", 5))
        except Exception:
            priority = 5

        for i, raw_line in enumerate(body.splitlines(), start=1):
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("- "):
                rows.append({
                    "doc": p.name,
                    "doc_id": doc_id,
                    "priority": priority,
                    "line": i,
                    "text": line[2:].strip(),
                })

    return rows
