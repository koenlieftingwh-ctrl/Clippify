import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

_WEIGHT_DESCRIPTIONS = {
    "hook_strength": "How compelling is the opening line to stop scrolling?",
    "emotional_peak": "How emotionally resonant or intense is this moment?",
    "standalone_clarity": "Can this moment be understood without prior context?",
    "novelty": "How surprising, counterintuitive, or new is the information?",
    "quotability": "How memorable and shareable are the specific words?",
    "controversy_potential": "How likely is this to spark discussion or debate?",
}


def score_transcript_moments(transcript: str, score_weights: dict) -> list[dict]:
    """Call Claude to identify and score candidate clip moments from a transcript."""
    import anthropic  # type: ignore

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set in pipeline/.env")

    client = anthropic.Anthropic(api_key=api_key)

    weights_block = "\n".join(
        f"  - {k} (weight {v:.2f}): {_WEIGHT_DESCRIPTIONS.get(k, k)}"
        for k, v in score_weights.items()
    )

    prompt = f"""You are an expert podcast clip curator. Analyze the transcript below and identify the 10 best moments for viral short-form video clips (YouTube Shorts / TikTok).

SCORING DIMENSIONS (score each 0.0–1.0):
{weights_block}

WEIGHTED FINAL SCORE = Σ(dimension × weight). All weights sum to 1.0.

RULES:
- Prefer moments that are 20–90 seconds long based on the timestamps.
- Each moment must be self-contained and gripping without prior context.
- transcript_snippet must be an exact quote (no paraphrasing).
- suggested_title ≤ 60 characters; suggested_hook is the first spoken sentence.

TRANSCRIPT (format: [start_sec] text):
{transcript[:16000]}

Return EXACTLY a JSON array of 10 objects. No markdown, no explanation.
[
  {{
    "moment_id": "moment_001",
    "start_sec": 0.0,
    "end_sec": 0.0,
    "transcript_snippet": "",
    "suggested_title": "",
    "suggested_hook": "",
    "hook_strength": 0.0,
    "emotional_peak": 0.0,
    "standalone_clarity": 0.0,
    "novelty": 0.0,
    "quotability": 0.0,
    "controversy_potential": 0.0,
    "score": 0.0
  }}
]"""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = msg.content[0].text.strip()

    # Strip markdown fences if present
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    moments: list[dict] = json.loads(raw)

    # Re-derive scores authoritatively so Claude can't override the weights
    from ..engines.scoring_engine import compute_score

    for i, m in enumerate(moments, 1):
        m["moment_id"] = f"moment_{i:03d}"
        m["score"] = compute_score({k: m.get(k, 0.0) for k in score_weights})

    return sorted(moments, key=lambda x: x["score"], reverse=True)
