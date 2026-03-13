"""
skill_engine/duplicate_filter.py

Uses the FAISS index already built in memory — no re-encoding of all skills.
This replaces the old approach of encoding every skill from scratch on every check.
"""

import numpy as np
from config import SKILL_MATCH_THRESHOLD, EMBEDDING_DIMENSION

# Threshold at which two skills are considered duplicates
# Slightly higher than SKILL_MATCH_THRESHOLD to allow similar-but-distinct skills
DUPLICATE_THRESHOLD = 0.85


def is_duplicate(new_skill: dict, skills: list) -> tuple[bool, str]:
    """
    Check if new_skill is a near-duplicate of any existing skill.

    Strategy:
    1. Fast name check first (exact + normalised string match) — zero cost
    2. FAISS vector search using the already-built index — reuses existing embeddings
       instead of re-encoding every skill from scratch

    Returns (is_duplicate: bool, existing_skill_name: str)
    """
    new_name = new_skill.get("name", "").strip().lower()

    # ── Fast path: exact or normalised name match ──────────────────────────
    for s in skills:
        existing_name = s.get("name", "").strip().lower()
        # Exact match
        if new_name == existing_name:
            return True, s["name"]
        # Normalised match (ignore spaces, underscores, case)
        if new_name.replace(" ", "").replace("_", "") == existing_name.replace(" ", "").replace("_", ""):
            return True, s["name"]

    # ── Vector search via existing FAISS index ─────────────────────────────
    # Import lazily to avoid circular dependency at module load time
    try:
        from skill_engine.vector_memory import index, search
        from sentence_transformers import SentenceTransformer
        from config import EMBEDDING_MODEL
        import re

        if index.ntotal == 0:
            return False, ""

        # Build embed text the same way agent.py does
        name_words = re.sub(r"([A-Z])", r" \1", new_skill.get("name", "")).lower().strip()
        parts = [
            new_skill.get("name", ""),
            new_skill.get("description", ""),
            " ".join(new_skill.get("tags", [])),
            name_words,
        ]
        embed_text = " ".join(p for p in parts if p).strip()

        # Encode only the NEW skill — one encode call, not N
        model = SentenceTransformer(EMBEDDING_MODEL)
        vec = model.encode([embed_text])[0]

        result = search(vec)
        if result:
            matched_skill, score = result
            if matched_skill and score >= DUPLICATE_THRESHOLD:
                return True, matched_skill.get("name", "")

    except Exception as e:
        # If vector check fails for any reason, fall back to no-duplicate
        import logging
        logging.getLogger(__name__).warning(f"Duplicate vector check failed: {e}")

    return False, ""