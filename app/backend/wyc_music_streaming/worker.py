"""Download workers: yt-dlp → tag → move into the user's music_dir."""
from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Protocol

import httpx

from .config import Config, User
from .events import EventBroker
from .jobs import Job, JobStore
from .library import AUDIO_EXTS, Library
from .paths import sanitize_name, track_filename, unique_path
from .tags import TagData, write_tags

log = logging.getLogger(__name__)

ProgressFn = Callable[[float], None]
Downloader = Callable[[Job, Path, ProgressFn], tuple[Path, Path | None]]
CoverFetcher = Callable[[str], Awaitable[bytes | None]]

TMP_DIR_NAME = ".wyc-music-streaming-tmp"
UPDATE_HINT = " (yt-dlp may be out of date: sudo systemctl start wyc-music-streaming-update-ytdlp)"
OUTDATED_MARKERS = (
    "HTTP Error 403",
    "Sign in to confirm",
    "nsig",
    "Requested format is not available",
    "Unable to extract",
)
PROGRESS_INTERVAL = 1.0


class Refresher(Protocol):
    def schedule(self) -> None: ...


def ytdlp_download(job: Job, tmp_dir: Path, on_progress: ProgressFn) -> tuple[Path, Path | None]:
    from yt_dlp import YoutubeDL

    def hook(d: dict[str, Any]) -> None:
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            if total:
                on_progress(min(d.get("downloaded_bytes", 0) / total, 1.0))

    opts = {
        "format": "bestaudio[ext=m4a]/bestaudio",
        "outtmpl": str(tmp_dir / f"{job.id}.%(ext)s"),
        "writethumbnail": True,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "socket_timeout": 30,
        "progress_hooks": [hook],
        "postprocessors": [
            # "best" = stream copy into a taggable container (aac→.m4a, opus→.opus). Never re-encode.
            {"key": "FFmpegExtractAudio", "preferredcodec": "best"},
            {"key": "FFmpegThumbnailsConvertor", "format": "jpg", "when": "before_dl"},
        ],
    }
    with YoutubeDL(opts) as ydl:
        ydl.extract_info(f"https://www.youtube.com/watch?v={job.video_id}", download=True)
    audio = next(
        (p for p in sorted(tmp_dir.glob(f"{job.id}.*")) if p.suffix.lower() in AUDIO_EXTS),
        None,
    )
    if audio is None:
        raise RuntimeError("download finished but no audio file was found")
    thumb = tmp_dir / f"{job.id}.jpg"
    return audio, (thumb if thumb.exists() else None)


async def fetch_cover(url: str) -> bytes | None:
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.content
    except httpx.HTTPError as exc:
        log.warning("cover fetch failed for %s: %s", url, exc)
        return None


def _error_text(exc: BaseException) -> str:
    lines = str(exc).strip().splitlines()
    text = (lines[0] if lines else "")[:300].removeprefix("ERROR: ").strip() or type(exc).__name__
    if any(marker in text for marker in OUTDATED_MARKERS):
        text += UPDATE_HINT
    return text


def _can_rename(src_dir: Path, dst_dir: Path) -> bool:
    """Try a real rename of an empty probe file from src_dir into dst_dir."""
    name = f".wyc-rename-probe-{os.getpid()}"
    src, dst = src_dir / name, dst_dir / name
    try:
        src.touch()
        os.replace(src, dst)
    except OSError:
        return False
    finally:
        src.unlink(missing_ok=True)
        dst.unlink(missing_ok=True)
    return True


class Worker:
    def __init__(
        self,
        *,
        config: Config,
        store: JobStore,
        library: Library,
        events: EventBroker,
        refresher: Refresher,
        downloader: Downloader = ytdlp_download,
        fetch_cover: CoverFetcher = fetch_cover,
    ):
        self.config = config
        self.store = store
        self.library = library
        self.events = events
        self.refresher = refresher
        self.downloader = downloader
        self.fetch_cover = fetch_cover
        self._wake = asyncio.Event()
        self._tmp_dirs = {name: self._pick_tmp_dir(user) for name, user in config.users.items()}

    def _pick_tmp_dir(self, user: User) -> Path:
        """Use data_dir/tmp when a rename from it into music_dir works, so os.replace is atomic.

        Comparing st_dev is not enough: systemd ReadWritePaths= bind-mounts each path
        separately, and rename() across bind mounts fails with EXDEV on one filesystem.
        """
        shared = self.config.server.data_dir / "tmp"
        shared.mkdir(parents=True, exist_ok=True)
        if _can_rename(shared, user.music_dir):
            return shared
        own = user.music_dir / TMP_DIR_NAME
        own.mkdir(exist_ok=True)
        return own

    def start(self) -> list[asyncio.Task[None]]:
        return [asyncio.create_task(self._loop(), name=f"worker-{i}") for i in range(self.config.concurrency)]

    def wake(self) -> None:
        self._wake.set()

    async def _loop(self) -> None:
        while True:
            self._wake.clear()
            job = self.store.claim_next()
            if job is None:
                try:
                    await asyncio.wait_for(self._wake.wait(), timeout=5.0)
                except TimeoutError:
                    pass
                continue
            try:
                await self.process(job)
            except Exception:  # never let one job kill the loop
                log.exception("unexpected error while processing job %s", job.id)

    async def process(self, job: Job) -> None:
        user = self.config.users.get(job.user)
        if user is None:
            self._fail(job, f"user {job.user!r} is no longer in config")
            return
        tmp_dir = self._tmp_dirs[user.name]
        self._clean_tmp(tmp_dir, job.id)
        self._publish_job(job.id)

        loop = asyncio.get_running_loop()
        last_sent = float("-inf")

        def on_progress(fraction: float) -> None:  # runs in the yt-dlp thread
            nonlocal last_sent
            now = time.monotonic()
            if now - last_sent < PROGRESS_INTERVAL:
                return
            last_sent = now
            loop.call_soon_threadsafe(self._progress, job.id, fraction)

        try:
            audio, thumb = await asyncio.to_thread(self.downloader, job, tmp_dir, on_progress)
            cover = await self.fetch_cover(job.cover_url) if job.cover_url else None
            if cover is None and thumb is not None and thumb.exists():
                cover = thumb.read_bytes()
            final = await asyncio.to_thread(self._finalize, job, user, audio, cover)
        except Exception as exc:
            log.warning("job %s failed: %s", job.id, exc)
            self._fail(job, _error_text(exc))
            return
        finally:
            self._clean_tmp(tmp_dir, job.id)

        rel = final.relative_to(user.music_dir).as_posix()
        # Index the file before marking the job done, so a client that sees
        # "done" always finds the track in /api/library.
        await asyncio.to_thread(self.library.add_file, user.name, final)
        self.store.finish(job.id, rel)
        self.refresher.schedule()
        self._publish_job(job.id)
        self.events.publish(user.name, "library", {"added": [rel]})

    def _finalize(self, job: Job, user: User, audio: Path, cover: bytes | None) -> Path:
        write_tags(audio, TagData(
            title=job.title, artist=job.artist, album=job.album, album_artist=job.artist,
            video_id=job.video_id, track_no=job.track_no, year=job.year, cover_jpeg=cover,
        ))
        dest_dir = user.music_dir / sanitize_name(job.artist) / sanitize_name(job.album, fallback="Singles")
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = unique_path(dest_dir / track_filename(job.title, audio.suffix.lstrip(".").lower(), job.track_no))
        os.replace(audio, dest)
        return dest

    @staticmethod
    def _clean_tmp(tmp_dir: Path, job_id: int) -> None:
        for leftover in tmp_dir.glob(f"{job_id}.*"):
            leftover.unlink(missing_ok=True)

    def _progress(self, job_id: int, fraction: float) -> None:
        self.store.set_progress(job_id, fraction)
        self._publish_job(job_id)

    def _publish_job(self, job_id: int) -> None:
        job = self.store.get(job_id)
        if job is not None:
            self.events.publish(job.user, "job", job.to_dict())

    def _fail(self, job: Job, error: str) -> None:
        self.store.fail(job.id, error)
        self._publish_job(job.id)
