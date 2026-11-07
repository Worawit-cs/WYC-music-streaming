"""Scan users' music folders into an in-memory index; delete tracks safely."""
from __future__ import annotations

import os
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .config import User
from .paths import remove_empty_parents, safe_resolve
from .tags import read_tags

AUDIO_EXTS = frozenset({".m4a", ".mp3", ".opus", ".flac", ".ogg"})


@dataclass(frozen=True)
class Track:
    path: str
    title: str
    artist: str
    album: str
    duration: float | None
    video_id: str | None
    track_no: int | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def read_track(root: Path, file: Path) -> Track:
    rel = file.relative_to(root)
    tags = read_tags(file)
    parts = rel.parts
    folder_artist = parts[0] if len(parts) >= 2 else "Unknown Artist"
    folder_album = parts[1] if len(parts) >= 3 else "Singles"
    return Track(
        path=rel.as_posix(),
        title=tags.get("title") or file.stem,
        artist=tags.get("album_artist") or tags.get("artist") or folder_artist,
        album=tags.get("album") or folder_album,
        duration=tags.get("duration"),
        video_id=tags.get("video_id"),
        track_no=tags.get("track_no"),
    )


def scan_dir(root: Path) -> list[Track]:
    tracks: list[Track] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in filenames:
            path = Path(dirpath) / name
            if not name.startswith(".") and path.suffix.lower() in AUDIO_EXTS:
                tracks.append(read_track(root, path))
    return tracks


def _track_sort_key(t: Track) -> tuple[bool, int, str]:
    return (t.track_no is None, t.track_no or 0, t.title.lower())


class Library:
    def __init__(self, users: dict[str, User]):
        self._users = users
        self._tracks: dict[str, dict[str, Track]] = {name: {} for name in users}
        self._lock = threading.Lock()

    def rescan(self, user: str) -> int:
        tracks = scan_dir(self._users[user].music_dir)
        with self._lock:
            self._tracks[user] = {t.path: t for t in tracks}
        return len(tracks)

    def rescan_all(self) -> None:
        for name in self._users:
            self.rescan(name)

    def add_file(self, user: str, file: Path) -> Track:
        track = read_track(self._users[user].music_dir, file)
        with self._lock:
            self._tracks[user][track.path] = track
        return track

    def tracks(self, user: str) -> list[Track]:
        with self._lock:
            return list(self._tracks[user].values())

    def video_ids(self, user: str) -> set[str]:
        return {t.video_id for t in self.tracks(user) if t.video_id}

    def has_video(self, user: str, video_id: str) -> bool:
        return video_id in self.video_ids(user)

    def tree(self, user: str) -> list[dict[str, Any]]:
        artists: dict[str, dict[str, list[Track]]] = {}
        for t in self.tracks(user):
            artists.setdefault(t.artist, {}).setdefault(t.album, []).append(t)
        return [
            {
                "artist": artist,
                "albums": [
                    {"album": album, "tracks": [t.to_dict() for t in sorted(ts, key=_track_sort_key)]}
                    for album, ts in sorted(albums.items(), key=lambda kv: kv[0].lower())
                ],
            }
            for artist, albums in sorted(artists.items(), key=lambda kv: kv[0].lower())
        ]

    def delete(self, user: str, rel_path: str) -> None:
        root = self._users[user].music_dir
        target = safe_resolve(root, rel_path)
        if target.suffix.lower() not in AUDIO_EXTS or not target.is_file():
            raise FileNotFoundError(rel_path)
        target.unlink()
        root_resolved = root.resolve()
        remove_empty_parents(root_resolved, target.parent)
        key = target.relative_to(root_resolved).as_posix()
        with self._lock:
            self._tracks[user].pop(key, None)
