"""
skill_engine/vector_memory.py

FAISS vector index for skill similarity search.

Index type: IndexFlatIP (inner product) with L2-normalised vectors
            -> equivalent to cosine similarity
            -> score range: 0.0 - 1.0  (higher = more similar)

Dimension:  768  (all-mpnet-base-v2)
            Reads from config so a model swap only needs one config change.

IMPORTANT: The old version used IndexFlatL2 (dimension=384, all-MiniLM-L6-v2).
           If you have an existing skill_index.faiss from the old version, delete it:
               del memory\skill_index.faiss
               del memory\skill_metadata.json
           The server will rebuild from skills/ on next startup.
"""

import faiss
import json
import numpy as np
import os

from config import EMBEDDING_DIMENSION, VECTOR_INDEX_PATH, VECTOR_META_PATH

os.makedirs(os.path.dirname(VECTOR_INDEX_PATH), exist_ok=True)


def _normalize(vec: np.ndarray) -> np.ndarray:
    """L2-normalise a (1, D) float32 array so inner product == cosine similarity."""
    norm = np.linalg.norm(vec)
    if norm == 0:
        return vec
    return (vec / norm).astype("float32")


def _load_index():
    """Load FAISS index from disk, or create fresh. Validates dimension vs config."""
    if os.path.exists(VECTOR_INDEX_PATH):
        loaded = faiss.read_index(VECTOR_INDEX_PATH)
        if loaded.d != EMBEDDING_DIMENSION:
            print(
                f"  [vector_memory] WARNING: stored index dimension {loaded.d} "
                f"!= config {EMBEDDING_DIMENSION}. Discarding stale index."
            )
            return faiss.IndexFlatIP(EMBEDDING_DIMENSION)
        return loaded
    return faiss.IndexFlatIP(EMBEDDING_DIMENSION)


def _load_metadata():
    if os.path.exists(VECTOR_META_PATH):
        try:
            return json.load(open(VECTOR_META_PATH, encoding="utf-8"))
        except Exception:
            return []
    return []


index    = _load_index()
metadata = _load_metadata()


def add_skill_vector(vec: np.ndarray, skill: dict):
    """
    Add a skill embedding to the index.
    vec: 1-D float32 numpy array of shape (EMBEDDING_DIMENSION,)
    """
    global metadata
    vec_norm = _normalize(np.array([vec], dtype="float32"))
    index.add(vec_norm)
    metadata.append(skill)
    faiss.write_index(index, VECTOR_INDEX_PATH)
    json.dump(metadata, open(VECTOR_META_PATH, "w", encoding="utf-8"), indent=2)


def search(vec: np.ndarray):
    """
    Find the closest skill to the given embedding vector.
    Returns (skill: dict, score: float) — score is cosine similarity 0-1.
    Returns (None, 0) if index is empty or no result.
    """
    if index.ntotal == 0:
        return None, 0

    vec_norm = _normalize(np.array([vec], dtype="float32"))
    D, I = index.search(vec_norm, 1)

    idx = I[0][0]
    if idx < 0 or idx >= len(metadata):
        return None, 0

    return metadata[idx], float(D[0][0])