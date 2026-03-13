# Similarity threshold for selecting an existing skill
# Uses cosine similarity (IndexFlatIP + normalized vectors)
# Value range: 0.0 – 1.0  (higher = stricter matching)
# 0.60 is calibrated for all-mpnet-base-v2 which produces tighter
# semantic clusters than all-MiniLM-L6-v2
SKILL_MATCH_THRESHOLD = 0.60


# Embedding model used for vector search
# UPGRADED: all-mpnet-base-v2 (768 dim) vs all-MiniLM-L6-v2 (384 dim)
# - Significantly better semantic recall for short phrases
# - Correctly clusters "what is the time" with "get current time"
# - Slightly slower to encode but still runs on CPU comfortably
EMBEDDING_MODEL = "all-mpnet-base-v2"


# FAISS embedding dimension — must match the model above
# all-MiniLM-L6-v2  → 384
# all-mpnet-base-v2 → 768
EMBEDDING_DIMENSION = 768


# Memory storage paths
VECTOR_INDEX_PATH = "memory/skill_index.faiss"
VECTOR_META_PATH = "memory/skill_metadata.json"


# Maximum steps the planner can generate
MAX_PLAN_STEPS = 3


# Skill storage directory
SKILLS_DIR = "skills"