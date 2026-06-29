import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")


def find_recent_episode(
    source_channels: list[str],
    lookback_days: int,
    min_episode_length_min: int,
) -> dict:
    """Search YouTube channels for the newest qualifying episode."""
    from googleapiclient.discovery import build  # type: ignore

    if not YOUTUBE_API_KEY:
        raise RuntimeError("YOUTUBE_API_KEY is not set in pipeline/.env")

    youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
    published_after = (
        datetime.now(timezone.utc) - timedelta(days=lookback_days)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    candidates: list[dict] = []

    for channel_id in source_channels:
        try:
            search_resp = (
                youtube.search()
                .list(
                    part="snippet",
                    channelId=channel_id,
                    order="date",
                    type="video",
                    publishedAfter=published_after,
                    maxResults=10,
                )
                .execute()
            )

            video_ids = [
                item["id"]["videoId"]
                for item in search_resp.get("items", [])
            ]
            if not video_ids:
                continue

            videos_resp = (
                youtube.videos()
                .list(part="snippet,contentDetails", id=",".join(video_ids))
                .execute()
            )

            for video in videos_resp.get("items", []):
                duration_min = _iso_duration_to_minutes(
                    video["contentDetails"]["duration"]
                )
                if duration_min >= min_episode_length_min:
                    candidates.append(
                        {
                            "video_id": video["id"],
                            "episode_url": f"https://www.youtube.com/watch?v={video['id']}",
                            "episode_title": video["snippet"]["title"],
                            "podcast_name": video["snippet"]["channelTitle"],
                            "duration_min": duration_min,
                            "published_at": video["snippet"]["publishedAt"],
                        }
                    )
        except Exception as exc:
            print(f"[youtube_service] Error searching channel {channel_id}: {exc}")

    if not candidates:
        raise ValueError(
            "No qualifying episodes found in the specified channels and time window."
        )

    candidates.sort(key=lambda x: x["published_at"], reverse=True)
    return candidates[0]


def _iso_duration_to_minutes(iso: str) -> float:
    hours = int(m.group(1)) if (m := re.search(r"(\d+)H", iso)) else 0
    minutes = int(m.group(1)) if (m := re.search(r"(\d+)M", iso)) else 0
    seconds = int(m.group(1)) if (m := re.search(r"(\d+)S", iso)) else 0
    return hours * 60 + minutes + seconds / 60
