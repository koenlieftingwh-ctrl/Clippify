SCORE_WEIGHTS = {
    "hook_strength": 0.25,
    "emotional_peak": 0.20,
    "standalone_clarity": 0.20,
    "novelty": 0.15,
    "quotability": 0.10,
    "controversy_potential": 0.10,
}


def compute_score(moment_scores: dict) -> float:
    """Weighted sum of individual moment dimension scores (0.0–1.0 each)."""
    total = 0.0
    for key, weight in SCORE_WEIGHTS.items():
        total += moment_scores.get(key, 0.0) * weight
    return round(total, 4)
