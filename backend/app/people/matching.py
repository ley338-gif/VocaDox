"""Pure-stdlib voiceprint similarity (post-GA P1-2) — no numpy/scipy
dependency for a straightforward cosine-similarity comparison between two
equal-length embedding vectors.
"""

from __future__ import annotations

import math
import uuid

# Below this cosine similarity, a candidate match is not confident enough
# to surface as a suggestion at all — chosen conservatively (a missed
# suggestion just means one more manual assignment; a wrong one risks
# misattributing a real person's statements).
DEFAULT_SUGGESTION_THRESHOLD = 0.75


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        raise ValueError(f"embedding dimension mismatch: {len(a)} vs {len(b)}")
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def find_best_match(
    embedding: list[float],
    candidates: dict[uuid.UUID, list[float]],
    *,
    threshold: float = DEFAULT_SUGGESTION_THRESHOLD,
) -> tuple[uuid.UUID, float] | None:
    """Returns (candidate_id, similarity) for the best-scoring candidate at
    or above `threshold`, or None if no candidate qualifies. A dimension
    mismatch against one candidate (e.g. an older embedding computed by a
    since-changed model) is skipped rather than raised — one bad candidate
    must not break matching against the rest."""
    best: tuple[uuid.UUID, float] | None = None
    for candidate_id, candidate_embedding in candidates.items():
        try:
            score = cosine_similarity(embedding, candidate_embedding)
        except ValueError:
            continue
        if score >= threshold and (best is None or score > best[1]):
            best = (candidate_id, score)
    return best
