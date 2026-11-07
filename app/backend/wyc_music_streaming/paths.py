"""Safe file names and path checks under a user's music_dir."""
from __future__ import annotations

import re
from pathlib import Path

FORBIDDEN = re.compile(r'[/\\:*?"<>|\x00-\x1f]')
WHITESPACE = re.compile(r"\s+")
MAX_NAME = 120


class UnsafePath(ValueError):
    """A client-supplied path points outside the user's music_dir."""


def sanitize_name(name: str, fallback: str = "Unknown") -> str:
    """Make one safe path component. Runs of whitespace become a single "_"."""
    cleaned = FORBIDDEN.sub("", name).strip().strip(".").strip()
    cleaned = cleaned[:MAX_NAME].strip()
    return WHITESPACE.sub("_", cleaned) or fallback


def safe_resolve(root: Path, rel: str) -> Path:
    """Resolve rel under root, following symlinks. Reject root itself and anything outside."""
    root_resolved = root.resolve()
    target = (root_resolved / rel).resolve()
    if target == root_resolved or not target.is_relative_to(root_resolved):
        raise UnsafePath(rel)
    return target


def remove_empty_parents(root: Path, start: Path) -> None:
    """Remove start and its parents while they are empty, stopping at root (root stays)."""
    root_resolved = root.resolve()
    folder = start
    while folder != root_resolved and folder.is_relative_to(root_resolved):
        try:
            folder.rmdir()  # only succeeds when empty
        except OSError:
            break
        folder = folder.parent


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    n = 2
    while True:
        candidate = path.with_name(f"{path.stem}_({n}){path.suffix}")
        if not candidate.exists():
            return candidate
        n += 1


def track_filename(title: str, ext: str, track_no: int | None = None) -> str:
    base = sanitize_name(title)
    if track_no:
        base = f"{track_no:02d}_{base}"
    return f"{base}.{ext}"
