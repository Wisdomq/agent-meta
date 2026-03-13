"""
skill_engine/selector.py

Selects the best matching skill for a task using:
  1. FAISS cosine similarity search (primary)
  2. Keyword fallback (secondary — only fires with strict guards)

Keyword fallback rules (ALL must pass):
  - 2+ meaningful words must match (after stop-word removal)
  - If the task contains a primary topic noun (hotel, recipe, workout, etc.)
    at least one must appear in the matched skill's name+description
  - Score is fixed at 0.62 — just above SKILL_MATCH_THRESHOLD (0.60)
"""

import re
from sentence_transformers import SentenceTransformer
from skill_engine.vector_memory import search
from config import SKILL_MATCH_THRESHOLD, EMBEDDING_MODEL

model = SentenceTransformer(EMBEDDING_MODEL)  # all-mpnet-base-v2 (768d)

# Words that should never count as "meaningful matches"
_STOP_WORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "be", "been", "being",
    "it", "its", "i", "me", "my", "we", "you", "he", "she", "they",
    "this", "that", "these", "those", "what", "which", "who",
    "how", "when", "where", "why",
    "get", "do", "make", "use", "can", "will", "would", "should", "could",
    "some", "any", "all", "more", "most", "just", "about",
    # Generic action verbs — too broad to be meaningful alone
    "generate", "create", "find", "list", "show", "give", "tell",
    "run", "execute", "write", "build", "add", "set", "put",
    # Numbers and units
    "1", "2", "3", "4", "5", "10", "100", "number", "numbers",
    "random", "between", "range",
}

# Primary topic nouns — if the task contains one of these,
# the matched skill's name+description MUST also contain at least one.
# This prevents cross-domain false positives (random numbers → workout exercises).
_PRIMARY_NOUNS = {
    # Fitness
    "workout", "exercise", "fitness", "gym", "training", "routine",
    # Food
    "recipe", "meal", "food", "diet", "nutrition", "cooking", "ingredient",
    # Travel
    "hotel", "attraction", "itinerary", "trip", "travel", "destination",
    # Learning
    "guide", "tutorial", "lesson", "course", "learn", "japanese", "language",
    # Time
    "time", "date", "clock", "calendar", "schedule",
    # Files
    "file", "lines", "count", "csv", "json", "txt",
    # Math/numbers — distinct topic
    "factorial", "fibonacci", "prime", "calculation", "arithmetic",
}

# Keyword fallback score — just above SKILL_MATCH_THRESHOLD
_KEYWORD_SCORE = 0.62


def _normalize_query(task: str) -> str:
    """Lowercase, strip punctuation. Double short queries for better embedding."""
    cleaned = re.sub(r"[^\w\s]", " ", task.lower()).strip()
    if len(cleaned.split()) <= 5:
        cleaned = cleaned + " " + cleaned
    return cleaned


def _meaningful_words(text: str) -> set:
    """Return words after removing stop words and short tokens."""
    words = re.sub(r"[^\w\s]", " ", text.lower()).split()
    return {w for w in words if w not in _STOP_WORDS and len(w) > 2}


def _primary_noun_check(task_words: set, skill: dict) -> bool:
    """
    If the task contains a primary topic noun, verify the skill shares at least one.
    Prevents 'random numbers' matching 'workout exercises' via generic words.
    """
    task_topics = task_words & _PRIMARY_NOUNS
    if not task_topics:
        return True  # no primary noun in task — no restriction

    skill_text = (
        skill.get("name", "") + " " +
        skill.get("description", "") + " " +
        " ".join(skill.get("tags", []))
    ).lower()

    return any(noun in skill_text for noun in task_topics)


def select_skill(task: str, skills=None):
    """
    Find the best matching skill for a task.

    Returns (skill, score) or (None, 0).
    """
    query = _normalize_query(task)

    try:
        vec = model.encode([query])[0]
    except Exception:
        return None, 0

    result = search(vec)
    if not result:
        return None, 0

    skill, score = result
    if not skill:
        return None, 0

    print(f"  [selector] Top FAISS match: '{skill.get('name')}' (score: {score:.4f}, threshold: {SKILL_MATCH_THRESHOLD})")

    if score >= SKILL_MATCH_THRESHOLD:
        return skill, score

    # ── Keyword fallback ──────────────────────────────────────────────────
    if not skills:
        return None, score

    task_words = _meaningful_words(task)

    for s in skills:
        skill_text = (
            s.get("name", "") + " " +
            s.get("description", "") + " " +
            " ".join(s.get("tags", []))
        )
        skill_words = _meaningful_words(skill_text)

        overlap = task_words & skill_words
        match_count = len(overlap)

        if match_count >= 2 and _primary_noun_check(task_words, s):
            print(f"  [selector] Keyword fallback: '{s.get('name')}' ({match_count} word matches: {overlap})")
            return s, _KEYWORD_SCORE

    return None, score