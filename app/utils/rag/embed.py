from __future__ import annotations
import numpy as np
from sentence_transformers import SentenceTransformer

_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2") 

def embed(texts: list[str]) -> np.ndarray:
    vecs = _model.encode(texts, batch_size=32, show_progress_bar=False, convert_to_numpy=True)
    normalization = np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-12
    return (vecs / normalization).astype("float32")
