import shutil
import subprocess
from pathlib import Path

import pytest

from wyc_music_streaming.config import Config, load_config


def write_config(tmp_path: Path, *, server_extra: str = "", users: str | None = None) -> Path:
    (tmp_path / "wick-music").mkdir(exist_ok=True)
    (tmp_path / "safeena-music").mkdir(exist_ok=True)
    key = tmp_path / "jellyfin.key"
    key.write_text("test-key\n")
    if users is None:
        users = f"""
[users.wick]
tailscale_login = "Wick@Example.com"
music_dir = "{tmp_path / 'wick-music'}"
jellyfin_user = "wick"

[users.safeena]
tailscale_login = "safeena@example.com"
music_dir = "{tmp_path / 'safeena-music'}"
"""
    text = f"""
[server]
data_dir = "{tmp_path / 'data'}"
{server_extra}

[jellyfin]
url = "http://jellyfin.test/"
api_key_file = "{key}"

[download]
concurrency = 2
{users}
"""
    path = tmp_path / "config.toml"
    path.write_text(text)
    return path


@pytest.fixture
def write_cfg(tmp_path):
    return lambda **kw: write_config(tmp_path, **kw)


@pytest.fixture
def config(tmp_path) -> Config:
    return load_config(write_config(tmp_path))


CODECS = {".m4a": "aac", ".opus": "libopus", ".mp3": "libmp3lame", ".flac": "flac", ".ogg": "libvorbis"}


@pytest.fixture
def make_audio():
    """Create a real 1-second silent audio file. Needs ffmpeg."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        pytest.fail("ffmpeg is required for audio tests: sudo apt install ffmpeg")

    def _make(path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [ffmpeg, "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono",
             "-t", "1", "-c:a", CODECS[path.suffix], "-y", str(path)],
            check=True,
        )
        return path

    return _make
