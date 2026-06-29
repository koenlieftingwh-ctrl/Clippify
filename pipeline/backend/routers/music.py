from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter()

MUSIC_LIBRARY = Path(__file__).parent.parent.parent / "assets" / "music_library"

# Map mood keywords to filename substrings to prefer
_MOOD_MAP: dict[str, list[str]] = {
    "energetic": ["energetic", "upbeat", "hype", "fast", "power", "pump"],
    "calm": ["calm", "chill", "relax", "ambient", "peaceful", "soft"],
    "dramatic": ["dramatic", "intense", "suspense", "epic", "tension"],
    "inspirational": ["inspire", "motivat", "uplift", "success", "triumph"],
    "curious": ["curious", "wonder", "discover", "learn", "mystery"],
    "neutral": ["neutral", "background", "subtle"],
}


@router.get("/select")
async def select_music(mood: str = "neutral"):
    MUSIC_LIBRARY.mkdir(parents=True, exist_ok=True)
    tracks = sorted(
        list(MUSIC_LIBRARY.glob("*.mp3")) + list(MUSIC_LIBRARY.glob("*.wav"))
    )

    if not tracks:
        raise HTTPException(
            status_code=404,
            detail=(
                "No tracks found in pipeline/assets/music_library/. "
                "Add licensed .mp3 or .wav files before running the Editor."
            ),
        )

    mood_lower = mood.lower()

    # Try to match mood against filename keywords
    keywords = _MOOD_MAP.get(mood_lower, [mood_lower])
    for track in tracks:
        name = track.stem.lower()
        if any(kw in name for kw in keywords):
            return {
                "track_path": str(track),
                "filename": track.name,
                "mood_matched": mood_lower,
            }

    # Fallback: first available track
    return {
        "track_path": str(tracks[0]),
        "filename": tracks[0].name,
        "mood_matched": "default",
    }
