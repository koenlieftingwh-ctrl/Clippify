import asyncio
import json
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

router = APIRouter()

BASE = Path(__file__).parent.parent.parent
JOBS_DIR = BASE / "data" / "jobs"
ASSETS_DIR = BASE / "data" / "assets"


# ── helpers ──────────────────────────────────────────────────────────────────


def _job_path(job_id: str) -> Path:
    return JOBS_DIR / f"{job_id}.json"


def _load_job(job_id: str) -> dict:
    path = _job_path(job_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found.")
    return json.loads(path.read_text(encoding="utf-8"))


def _save_job(job: dict) -> None:
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    job["updated_at"] = datetime.now(timezone.utc).isoformat()
    _job_path(job["job_id"]).write_text(
        json.dumps(job, indent=2), encoding="utf-8"
    )


def _blank_job(job_id: str) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "job_id": job_id,
        "status": "created",
        "episode_url": None,
        "episode_title": None,
        "podcast_name": None,
        "transcript_ready": False,
        "transcript": None,
        "candidate_moments": [],
        "selected_moment_id": None,
        "selection_status": None,
        "captions_ready": False,
        "captions": [],
        "created_at": now,
        "updated_at": now,
    }


# ── request models ────────────────────────────────────────────────────────────


class FindEpisodeRequest(BaseModel):
    config: dict[str, Any]


class DownloadSourceRequest(BaseModel):
    url: str


class PatchJobRequest(BaseModel):
    selected_moment_id: Optional[str] = None
    selection_status: Optional[str] = None


# ── endpoints ─────────────────────────────────────────────────────────────────


@router.post("/find_episode")
async def find_episode(req: FindEpisodeRequest, bg: BackgroundTasks):
    cfg = req.config
    channels = cfg.get("source_channels", [])
    if not channels:
        raise HTTPException(status_code=400, detail="source_channels is required.")

    try:
        from ..services.youtube_service import find_recent_episode

        ep = find_recent_episode(
            channels,
            cfg.get("lookback_days", 7),
            cfg.get("min_episode_length_min", 30),
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    job_id = uuid.uuid4().hex[:8]
    job = _blank_job(job_id)
    job["episode_url"] = ep["episode_url"]
    job["episode_title"] = ep["episode_title"]
    job["podcast_name"] = ep["podcast_name"]
    _save_job(job)

    return {"job_id": job_id, "episode_url": ep["episode_url"]}


@router.get("/{job_id}")
async def get_job(job_id: str, bg: BackgroundTasks):
    job = _load_job(job_id)

    # Side-effect: kick off transcript fetch when first polled
    if job["status"] == "created" and not job["transcript_ready"]:
        job["status"] = "transcript_pending"
        _save_job(job)
        bg.add_task(_fetch_transcript_bg, job_id)

    return job


@router.post("/{job_id}/score_moments")
async def score_moments(job_id: str):
    job = _load_job(job_id)
    if not job.get("transcript_ready"):
        raise HTTPException(
            status_code=409,
            detail="Transcript not ready. Poll GET /jobs/{job_id} until transcript_ready == true.",
        )

    from ..engines.scoring_engine import SCORE_WEIGHTS
    from ..services.scoring_service import score_transcript_moments

    try:
        moments = score_transcript_moments(job["transcript"], SCORE_WEIGHTS)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    job["candidate_moments"] = moments
    job["status"] = "scored"
    _save_job(job)
    return job


@router.patch("/{job_id}")
async def patch_job(job_id: str, req: PatchJobRequest):
    job = _load_job(job_id)
    if req.selected_moment_id is not None:
        job["selected_moment_id"] = req.selected_moment_id
    if req.selection_status is not None:
        job["selection_status"] = req.selection_status
        if req.selection_status == "selected":
            job["status"] = "selected"
    _save_job(job)
    return job


@router.post("/{job_id}/download_source")
async def download_source(job_id: str, req: DownloadSourceRequest, bg: BackgroundTasks):
    job = _load_job(job_id)
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    out = ASSETS_DIR / f"{job_id}_source.mp4"

    if out.exists() and out.stat().st_size > 500_000:
        job["status"] = "downloaded"
        _save_job(job)
        return {"status": "already_downloaded", "path": str(out)}

    job["status"] = "downloading"
    _save_job(job)
    bg.add_task(_download_video_bg, job_id, req.url, str(out))
    return {"status": "downloading", "job_id": job_id, "path": str(out)}


@router.post("/{job_id}/transcribe_clip")
async def transcribe_clip(job_id: str, bg: BackgroundTasks):
    cut_path = ASSETS_DIR / f"{job_id}_cut.mp4"
    if not cut_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Cut clip not found. Trim with ffmpeg before calling this endpoint.",
        )

    job = _load_job(job_id)
    job["captions_ready"] = False
    job["status"] = "transcribing_clip"
    _save_job(job)

    bg.add_task(_transcribe_clip_bg, job_id, str(cut_path))
    return {"status": "transcribing", "job_id": job_id}


# ── background tasks ──────────────────────────────────────────────────────────


async def _fetch_transcript_bg(job_id: str) -> None:
    job = _load_job(job_id)
    try:
        from ..services.transcription_service import get_episode_transcript

        transcript = await asyncio.to_thread(
            get_episode_transcript, job["episode_url"]
        )
        job["transcript"] = transcript
        job["transcript_ready"] = True
        job["status"] = "transcript_ready"
    except Exception as exc:
        job["status"] = "transcript_error"
        job["error"] = str(exc)
    _save_job(job)


async def _download_video_bg(job_id: str, url: str, out_path: str) -> None:
    job = _load_job(job_id)
    try:
        cmd = [
            "yt-dlp",
            "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "--merge-output-format", "mp4",
            "-o", out_path,
            "--no-playlist",
            url,
        ]
        result = await asyncio.to_thread(
            subprocess.run, cmd, capture_output=True, text=True, timeout=600
        )
        if result.returncode != 0:
            job["status"] = "download_error"
            job["error"] = result.stderr[:2000]
        else:
            job["status"] = "downloaded"
    except Exception as exc:
        job["status"] = "download_error"
        job["error"] = str(exc)
    _save_job(job)


async def _transcribe_clip_bg(job_id: str, clip_path: str) -> None:
    job = _load_job(job_id)
    try:
        from ..services.transcription_service import get_clip_captions

        captions = await asyncio.to_thread(get_clip_captions, clip_path)
        job["captions"] = captions
        job["captions_ready"] = True
        job["status"] = "captions_ready"
    except Exception as exc:
        job["status"] = "transcription_error"
        job["error"] = str(exc)
    _save_job(job)
