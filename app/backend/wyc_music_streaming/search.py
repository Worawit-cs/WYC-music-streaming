"""YouTube search and URL lookup through yt-dlp (no download)."""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import asdict
from typing import Any

from .metadata import clean

Extractor = Callable[[str, dict[str, Any]], dict[str, Any]]

SEARCH_TIMEOUT = 20.0
MAX_PLAYLIST = 200
SEARCH_COUNT = 10
YOUTUBE_URL = re.compile(r"^https?://([\w-]+\.)?(youtube\.com|youtu\.be)/", re.IGNORECASE)
RADIO_MIX = re.compile(r"[?&]list=RD")
VIDEO_ID = re.compile(r"^[\w-]{11}$")


def ytdlp_extract(target: str, opts: dict[str, Any]) -> dict[str, Any]:
    from yt_dlp import YoutubeDL

    with YoutubeDL(opts) as ydl:
        return ydl.sanitize_info(ydl.extract_info(target, download=False))


def _options(target: str, is_url: bool) -> dict[str, Any]:
    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": "in_playlist",
        "playlistend": MAX_PLAYLIST,
        "socket_timeout": 15,
    }
    if is_url and "v=" in target and RADIO_MIX.search(target):
        opts["noplaylist"] = True  # a "Mix" list is endless radio, not a real playlist
    return opts


def _result(entry: dict[str, Any], playlist_title: str | None, library_ids: set[str]) -> dict[str, Any]:
    video_id = entry["id"]
    title = entry.get("title") or ""
    channel = entry.get("channel") or entry.get("uploader") or ""
    suggested = clean(
        title, channel,
        artist=entry.get("artist"), track=entry.get("track"), album=entry.get("album"),
        playlist_title=playlist_title,
    )
    return {
        "video_id": video_id,
        "title": title,
        "channel": channel,
        "duration": entry.get("duration"),
        "thumbnail_url": f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg",
        "suggested": asdict(suggested),
        "in_library": video_id in library_ids,
    }


def search(query: str, library_ids: set[str], extract: Extractor = ytdlp_extract) -> dict[str, Any]:
    target = query.strip()
    if not target:
        raise ValueError("empty query")
    is_url = bool(YOUTUBE_URL.match(target))
    info = extract(target if is_url else f"ytsearch{SEARCH_COUNT}:{target}", _options(target, is_url))

    is_list = info.get("_type") == "playlist"
    playlist_title = info.get("title") if (is_url and is_list) else None
    entries = (info.get("entries") or []) if is_list else [info]
    results = [
        _result(e, playlist_title, library_ids)
        for e in entries
        if e and VIDEO_ID.match(str(e.get("id", "")))
    ]
    kind = "playlist" if playlist_title else ("url" if is_url else "search")
    return {"kind": kind, "playlist_title": playlist_title, "results": results}
