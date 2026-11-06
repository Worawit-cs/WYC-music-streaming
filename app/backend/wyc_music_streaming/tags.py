"""Read and write audio tags with mutagen.

The worker only produces .m4a (AAC) or .opus/.ogg (stream copy), so
write_tags supports those. read_tags also reads .mp3 and .flac added through SMB.
"""
from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mutagen import File as MutagenFile
from mutagen import MutagenError
from mutagen.flac import Picture
from mutagen.id3 import ID3
from mutagen.mp4 import MP4, MP4Cover

log = logging.getLogger(__name__)
COMMENT_PREFIX = "youtube:"


@dataclass(frozen=True)
class TagData:
    title: str
    artist: str
    album: str
    album_artist: str
    video_id: str
    track_no: int | None = None
    year: str | None = None
    cover_jpeg: bytes | None = None


def write_tags(path: Path, tags: TagData) -> None:
    ext = path.suffix.lower()
    comment = f"{COMMENT_PREFIX}{tags.video_id}"
    if ext == ".m4a":
        f = MP4(path)
        f["\xa9nam"] = [tags.title]
        f["\xa9ART"] = [tags.artist]
        f["aART"] = [tags.album_artist]
        f["\xa9alb"] = [tags.album]
        f["\xa9cmt"] = [comment]
        if tags.track_no:
            f["trkn"] = [(tags.track_no, 0)]
        if tags.year:
            f["\xa9day"] = [tags.year]
        if tags.cover_jpeg:
            f["covr"] = [MP4Cover(tags.cover_jpeg, imageformat=MP4Cover.FORMAT_JPEG)]
        f.save()
        return
    if ext in (".opus", ".ogg"):
        f = MutagenFile(path)
        if f is None or f.tags is None:
            raise ValueError(f"cannot open {path.name} for tagging")
        f["title"] = [tags.title]
        f["artist"] = [tags.artist]
        f["albumartist"] = [tags.album_artist]
        f["album"] = [tags.album]
        f["comment"] = [comment]
        if tags.track_no:
            f["tracknumber"] = [str(tags.track_no)]
        if tags.year:
            f["date"] = [tags.year]
        if tags.cover_jpeg:
            pic = Picture()
            pic.type = 3  # front cover
            pic.mime = "image/jpeg"
            pic.data = tags.cover_jpeg
            f["metadata_block_picture"] = [base64.b64encode(pic.write()).decode("ascii")]
        f.save()
        return
    raise ValueError(f"unsupported container: {ext}")


def _parse_track(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(str(value).split("/")[0]) or None
    except ValueError:
        return None


def read_tags(path: Path) -> dict[str, Any]:
    try:
        f = MutagenFile(path)
    except (MutagenError, OSError) as exc:
        log.warning("cannot read tags from %s: %s", path, exc)
        return {}
    if f is None:
        return {}
    out: dict[str, Any] = {"duration": getattr(f.info, "length", None)}

    if isinstance(f, MP4):
        t = f.tags or {}

        def g(key: str) -> Any:
            v = t.get(key)
            return v[0] if v else None

        out |= {"title": g("\xa9nam"), "artist": g("\xa9ART"), "album": g("\xa9alb"),
                "album_artist": g("aART"), "year": g("\xa9day"), "comment": g("\xa9cmt")}
        trkn = g("trkn")
        out["track_no"] = trkn[0] if trkn and trkn[0] else None
    elif isinstance(f.tags, ID3):
        t = f.tags

        def g(key: str) -> Any:
            frame = t.get(key)
            return str(frame.text[0]) if frame is not None and frame.text else None

        comms = t.getall("COMM")
        out |= {"title": g("TIT2"), "artist": g("TPE1"), "album": g("TALB"),
                "album_artist": g("TPE2"), "year": g("TDRC"),
                "comment": str(comms[0].text[0]) if comms and comms[0].text else None,
                "track_no": _parse_track(g("TRCK"))}
    else:
        t = f.tags

        def g(key: str) -> Any:
            v = t.get(key) if t else None
            return v[0] if v else None

        out |= {"title": g("title"), "artist": g("artist"), "album": g("album"),
                "album_artist": g("albumartist"), "year": g("date"), "comment": g("comment"),
                "track_no": _parse_track(g("tracknumber"))}

    comment = out.pop("comment", None)
    out["video_id"] = (
        comment[len(COMMENT_PREFIX):]
        if isinstance(comment, str) and comment.startswith(COMMENT_PREFIX)
        else None
    )
    return out
