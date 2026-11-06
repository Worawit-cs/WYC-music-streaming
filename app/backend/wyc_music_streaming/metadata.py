"""Turn a YouTube title/channel into suggested title, artist, album tags. Pure functions."""
from __future__ import annotations

import re
from dataclasses import dataclass

NOISE = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\(\s*official\s+(?:music\s+)?video\s*\)",
        r"\(\s*official\s+audio\s*\)",
        r"\(\s*(?:official\s+)?lyrics?(?:\s+video)?\s*\)",
        r"\(\s*(?:official\s+)?visuali[sz]er\s*\)",
        r"\[\s*official[^\]]*\]",
        r"\[\s*4k[^\]]*\]",
        r"[\[(]\s*hd\s*[\])]",
    )
]
PIPE_SUFFIX = re.compile(r"\s+\|.*$")
SPACES = re.compile(r"\s+")
ARTIST_SPLIT = re.compile(r"\s+[-–—]\s+")
TOPIC = re.compile(r"\s*-\s*Topic$", re.IGNORECASE)
VEVO = re.compile(r"VEVO$", re.IGNORECASE)


@dataclass(frozen=True)
class Suggested:
    title: str
    artist: str
    album: str


def clean_title(title: str) -> str:
    for pattern in NOISE:
        title = pattern.sub("", title)
    title = PIPE_SUFFIX.sub("", title)
    return SPACES.sub(" ", title).strip(" -–—|")


def clean_channel(channel: str) -> str:
    return VEVO.sub("", TOPIC.sub("", channel)).strip()


def clean(
    title: str,
    channel: str,
    *,
    artist: str | None = None,
    track: str | None = None,
    album: str | None = None,
    playlist_title: str | None = None,
) -> Suggested:
    t = clean_title(track or title)
    a = (artist or "").strip()
    if not track:
        parts = ARTIST_SPLIT.split(t, maxsplit=1)
        if len(parts) == 2:
            left, right = parts[0].strip(), parts[1].strip()
            if not a:
                ch = clean_channel(channel).lower()
                if ch and right.lower() == ch and left.lower() != ch:
                    a, t = right, left  # "Title – Artist" uploaded by the artist
                else:
                    a, t = left, right
            elif left.lower() == a.lower():
                t = right
    if not a:
        a = clean_channel(channel) or "Unknown Artist"
    return Suggested(
        title=t or "Unknown",
        artist=a,
        album=(album or playlist_title or "Singles").strip(),
    )
