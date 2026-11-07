"""Rename (or merge) an album or an artist: rewrite tags, move files, drop empty folders."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

from .config import User
from .library import Library
from .paths import remove_empty_parents, safe_resolve, sanitize_name, unique_path
from .tags import read_tags, retag

Kind = Literal["album", "artist"]


@dataclass(frozen=True)
class RenameResult:
    moved: int
    merged: bool


class PartialRename(RuntimeError):
    """A track failed after `moved` tracks were already renamed."""

    def __init__(self, moved: int, cause: BaseException):
        super().__init__(f"ย้ายแล้ว {moved} เพลง ก่อนเกิดปัญหา: {cause}")
        self.moved = moved


def rename(library: Library, user: User, *, kind: Kind, artist: str, new_name: str,
           album: str | None = None) -> RenameResult:
    """artist/album are the names /api/library shows. Raises ValueError, LookupError or PartialRename."""
    new = new_name.strip()
    if kind == "album" and not album:
        raise ValueError("ต้องระบุอัลบั้ม")
    old = artist if kind == "artist" else album
    if not new:
        raise ValueError("ชื่อใหม่ว่างอยู่")
    if new == old:
        raise ValueError("ชื่อใหม่เหมือนชื่อเดิม")

    every = library.tracks(user.name)
    picked = [t for t in every if t.artist == artist and (kind == "artist" or t.album == album)]
    if not picked:
        raise LookupError("ไม่พบเพลงที่จะเปลี่ยนชื่อ")
    picked_paths = {t.path for t in picked}
    merged = any(
        t.path not in picked_paths and t.artist == (new if kind == "artist" else artist)
        and (kind == "artist" or t.album == new)
        for t in every
    )

    root = user.music_dir
    root_resolved = root.resolve()
    moved = 0
    try:
        for track in picked:
            src = safe_resolve(root, track.path)
            tags = read_tags(src)
            if kind == "album":
                dest_artist, dest_album = artist, new
                changes = {"album": new}
                if not (tags.get("album_artist") or tags.get("artist")):
                    changes["album_artist"] = artist  # keep the artist the folder gave it
            else:
                dest_artist, dest_album = new, track.album
                changes = {"album_artist": new}
                if not tags.get("artist") or tags.get("artist") == artist:
                    changes["artist"] = new  # keep "X feat. Y" track artists
                if not tags.get("album"):
                    changes["album"] = track.album
            retag(src, **changes)
            dest_dir = root_resolved / sanitize_name(dest_artist) / sanitize_name(dest_album, fallback="Singles")
            if dest_dir != src.parent:
                dest_dir.mkdir(parents=True, exist_ok=True)
                os.replace(src, unique_path(dest_dir / src.name))
                remove_empty_parents(root_resolved, src.parent)
            moved += 1
    except (OSError, ValueError) as exc:
        raise PartialRename(moved, exc) from exc
    finally:
        library.rescan(user.name)
    return RenameResult(moved=moved, merged=merged)
