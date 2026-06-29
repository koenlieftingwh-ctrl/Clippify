import re


def get_episode_transcript(episode_url: str) -> str:
    """Fetch auto-generated captions from YouTube as a timestamped plain-text transcript."""
    from youtube_transcript_api import YouTubeTranscriptApi  # type: ignore

    video_id = _extract_video_id(episode_url)
    try:
        entries = YouTubeTranscriptApi.get_transcript(video_id)
    except Exception as exc:
        raise RuntimeError(
            f"Could not fetch transcript for video {video_id}: {exc}"
        ) from exc

    lines = [
        f"[{entry['start']:.1f}] {entry['text'].replace(chr(10), ' ')}"
        for entry in entries
    ]
    return "\n".join(lines)


def get_clip_captions(clip_path: str) -> list[dict]:
    """Get word-level captions for a trimmed clip using openai-whisper."""
    try:
        import whisper  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "openai-whisper is not installed. Run: pip install openai-whisper"
        ) from exc

    model = whisper.load_model("base")
    result = model.transcribe(clip_path, word_timestamps=True)

    captions: list[dict] = []
    for segment in result.get("segments", []):
        for w in segment.get("words", []):
            captions.append(
                {
                    "word": w["word"].strip(),
                    "start_sec": round(w["start"], 3),
                    "end_sec": round(w["end"], 3),
                }
            )
    return captions


def _extract_video_id(url: str) -> str:
    for pattern in (
        r"youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})",
        r"youtu\.be/([a-zA-Z0-9_-]{11})",
    ):
        if m := re.search(pattern, url):
            return m.group(1)
    raise ValueError(f"Cannot extract YouTube video ID from URL: {url}")
