from __future__ import annotations
import os, json, glob
import numpy as np
import faiss
from sqlalchemy.orm import Session
from app.db.database import SessionLocal
from app.db.models import Opportunity
from app.utils.rag.embed import embed
import re, yaml
import logging

logger = logging.getLogger(__name__)

STORE = "vector_store"
FEEDBACK_INDEX = os.path.join(STORE, "feedback.faiss")
FEEDBACK_IDS   = os.path.join(STORE, "feedback_ids.json")
ORGKB_INDEX    = os.path.join(STORE, "orgkb.faiss")
ORGKB_IDS      = os.path.join(STORE, "orgkb_ids.json")
ORGKB_DIR      = "app/org_kb"

os.makedirs(STORE, exist_ok=True)




FRONT = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
def _parse_front_matter(text: str):
    m = FRONT.match(text)
    if not m:
        return {}, text
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except Exception:
        fm = {}
    body = text[m.end():]
    return fm, body


def _fsync_dir(path: str) -> None:
    dir_path = os.path.dirname(path) or "."
    flags = getattr(os, "O_RDONLY", 0) | getattr(os, "O_DIRECTORY", 0)
    fd = os.open(dir_path, flags)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic_write_json(data, path: str) -> None:
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
        f.flush()                 
        os.fsync(f.fileno())      
    os.replace(tmp, path)     
    _fsync_dir(path)       

def _atomic_write_faiss(index: faiss.Index, path: str) -> None:
    tmp = f"{path}.tmp"
    faiss.write_index(index, tmp) 
    os.replace(tmp, path)   
    _fsync_dir(path)    

def _build_index(vectors: np.ndarray, ids: np.ndarray) -> faiss.Index:
    dim = vectors.shape[1]
    base = faiss.IndexFlatIP(dim)                  
    idx  = faiss.IndexIDMap2(base)                 
    idx.add_with_ids(vectors, ids.astype("int64"))
    return idx

def rebuild_feedback():
    db: Session = SessionLocal()
    try:
        rows = (db.query(Opportunity)
                  .filter(Opportunity.user_feedback == True)
                  .filter(Opportunity.description.isnot(None))
                  .all())
    finally:
        db.close()

    texts, ids, meta = [], [], []
    next_fid = 1
    for o in rows:
        t = (o.description or "").strip()
        if not t: continue
        texts.append(t)
        ids.append(next_fid)
        meta.append({
            "faiss_id": next_fid,
            "unique_key": o.unique_key,
            "url": o.url
        })
        next_fid += 1

    if not texts:
        _atomic_write_json([], FEEDBACK_IDS)
        _atomic_write_faiss(faiss.IndexFlatIP(384), FEEDBACK_INDEX)
        print("Feedback: no rows; wrote empty index.")
        return

    vecs = embed(texts)
    index = _build_index(vecs, np.array(ids))
    _atomic_write_faiss(index, FEEDBACK_INDEX)
    _atomic_write_json(meta, FEEDBACK_IDS)
    print(f"Feedback: indexed {len(texts)} examples.")

def _chunk(text: str, max_chars: int = 800):
    text = text.strip()
    out, start = [], 0
    while start < len(text):
        out.append(text[start:start+max_chars])
        start += max_chars
    return out

def rebuild_orgkb():
    files = sorted(glob.glob(os.path.join(ORGKB_DIR, "*.md")))
    texts, ids, meta = [], [], []
    next_id = 1
    for path in files:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
        fm, body = _parse_front_matter(raw)
        doc_id = (fm.get("id") or os.path.splitext(os.path.basename(path))[0]).strip()
        priority = int(fm.get("priority") or 0)

        chunks = _chunk(body, 800)
        for i, chunk in enumerate(chunks):
            texts.append(chunk)
            ids.append(next_id)
            meta.append({
                "id": next_id,                
                "file": os.path.basename(path),
                "doc_id": doc_id,          
                "priority": priority,        
                "chunk": i,
                "text": chunk[:200]
            })
            next_id += 1

    if not texts:
        _atomic_write_json([], ORGKB_IDS)
        _atomic_write_faiss(faiss.IndexFlatIP(384), ORGKB_INDEX)
        print("OrgKB: no files; wrote empty index.")
        return

    vecs = embed(texts)
    index = _build_index(vecs, np.array(ids))
    _atomic_write_faiss(index, ORGKB_INDEX)
    _atomic_write_json(meta, ORGKB_IDS)
    logger.info(f"OrgKB: indexed {len(texts)} chunks from {len(files)} files.")


if __name__ == "__main__":
    rebuild_feedback()
    rebuild_orgkb()
