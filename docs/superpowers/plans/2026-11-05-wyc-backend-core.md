# WYC-music-streaming Backend Core Implementation Plan (Plan 1 of 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A FastAPI backend on the NAS that searches YouTube, downloads audio into each user's music folder with correct tags, lists and deletes library tracks, and triggers a Jellyfin refresh. It is reachable only through `tailscale serve`.

**Architecture:** One Python package `wyc_music_streaming` in `app/backend/`. Small modules with one job each: config, auth, paths, metadata, tags, library, jobs (SQLite), jellyfin, events (SSE), search, worker, api, main. yt-dlp and the Jellyfin HTTP client are injected, so tests never touch the network. systemd runs it as user `wyc-music-streaming`.

**Tech Stack:** Python 3.12 (via uv), FastAPI, uvicorn, yt-dlp, mutagen, httpx, SQLite (stdlib `sqlite3`), pytest + pytest-asyncio. ffmpeg is used by yt-dlp and by the test fixtures.

**Spec:** `docs/superpowers/specs/2026-11-05-wyc-music-streaming-design.md`

**Later plans (not in this one):**
- Plan 2: SvelteKit frontend (search, library, queue, denied pages).
- Plan 3: albums (`ytmusicapi`) and boxes (Jellyfin playlists), backend and frontend.

## Global Constraints

- Python 3.12 from uv only (`uv sync --python 3.12`). Never use or change the system Python 3.8.
- The server binds `127.0.0.1` only. Startup fails for a non-loopback `server.host` unless `[server] dev = true`.
- Auth header: `Tailscale-User-Login`. Unknown or missing login → `403`. No sessions, no cookies.
- Never transcode. Format `bestaudio[ext=m4a]/bestaudio`. `FFmpegExtractAudio` only with `preferredcodec: "best"` (stream copy into a taggable container).
- Default download concurrency: `2` (allowed 1–4).
- File layout: `music_dir/<Artist>/<Album>/<Title>.<ext>`; with a track number: `<NN> <Title>.<ext>` (`NN` = 2 digits).
- Name sanitizing: remove `/\:*?"<>|` and control characters, trim, max 120 characters. Collision: add ` (2)`, ` (3)`, …
- Duplicate tag: comment `youtube:<video_id>`.
- Jellyfin: `POST {url}/Library/Refresh` with header `Authorization: MediaBrowser Token="<key>"`. Debounce 30 s. A failure only logs a warning; it never fails a job.
- Search: `ytsearch10:<q>`, flat extraction, timeout 20 s. Playlists: max 200 entries.
- Progress events: at most 1 per second per job.
- Timestamps: ISO 8601 UTC, for example `2026-11-05T10:00:00Z`.
- Names: repo/UI `WYC-music-streaming`; systemd unit, system user, `/etc`, `/var/lib`, `/opt` → `wyc-music-streaming`; Python package `wyc_music_streaming`; env var `WYC_MUSIC_STREAMING_CONFIG`; app folder `app/`.
- The repo is public. Never commit `config.toml` or any API key.

## File Structure

```
app/
  README.md                         dev setup + NAS setup + deploy
  backend/
    pyproject.toml
    uv.lock
    wyc_music_streaming/
      __init__.py
      __main__.py                   load config, run uvicorn on config host/port
      config.py                     load + validate TOML → Config/User dataclasses
      auth.py                       resolve_user(headers, config)
      paths.py                      sanitize_name, safe_resolve, unique_path, track_filename
      metadata.py                   clean() YouTube title/channel → Suggested
      tags.py                       write_tags / read_tags with mutagen
      library.py                    scan_dir, Track, Library index, delete
      jobs.py                       JobStore (SQLite), Job, NewJob
      jellyfin.py                   JellyfinClient.refresh_library, RefreshScheduler
      events.py                     EventBroker, format_sse
      search.py                     search() over an injectable yt-dlp extractor
      worker.py                     Worker: download → tag → move; ytdlp_download
      api.py                        APIRouter /api/*
      main.py                       create_app() factory, lifespan, SPA static files
    tests/
      conftest.py
      test_config.py test_auth.py test_paths.py test_metadata.py test_tags.py
      test_library.py test_jobs.py test_jellyfin.py test_events.py
      test_search.py test_worker.py test_api.py
  deploy/
    check-nas.sh                    read-only preflight checks on the NAS
    config.example.toml
    update.sh
    wyc-music-streaming.service
    wyc-music-streaming-update-ytdlp.service
    wyc-music-streaming-update-ytdlp.timer
.gitignore                          (modify: add app ignores)
```

All commands below run from `app/backend/` unless the step says otherwise.

---

### Task 1: NAS preflight check script

Checks the risks the spec still lists as open (ffmpeg, Node, `tailscale serve`, UFW). The user can run it on the NAS while the other tasks are built.

**Files:**
- Create: `app/deploy/check-nas.sh`

**Interfaces:**
- Consumes: nothing
- Produces: an executable script. Exit code 0 = all required checks pass.

- [ ] **Step 1: Write the script**

```bash
#!/usr/bin/env bash
# Read-only preflight checks for WYC-music-streaming on the NAS.
# Usage: bash app/deploy/check-nas.sh
# Changes nothing. Exit code 1 means at least one required check failed.

FAILED=0
ok()   { printf 'OK    %s\n' "$*"; }
warn() { printf 'WARN  %s\n' "$*"; }
bad()  { printf 'FAIL  %s\n' "$*"; FAILED=1; }

if command -v ffmpeg >/dev/null 2>&1; then
  ok "ffmpeg: $(ffmpeg -version | head -n1)"
else
  bad "ffmpeg missing. Fix: sudo apt install ffmpeg"
fi

if [[ -x /usr/local/bin/deno ]]; then
  ok "deno (system-wide): $(/usr/local/bin/deno --version | head -n1)"
else
  bad "deno not in /usr/local/bin. The service user cannot see ~/.deno. See app/README.md"
fi

if [[ -x /usr/local/bin/uv ]]; then
  ok "uv (system-wide): $(/usr/local/bin/uv --version)"
else
  bad "uv not in /usr/local/bin. See app/README.md"
fi

if [[ -s "$HOME/.nvm/nvm.sh" ]]; then
  # shellcheck disable=SC1091
  source "$HOME/.nvm/nvm.sh"
  if command -v node >/dev/null 2>&1 && node -e 'process.exit(0)' 2>/dev/null; then
    ok "node: $(node --version) (needed by Plan 2 frontend build)"
  else
    warn "nvm found but node does not run. Try: nvm install --lts"
  fi
else
  warn "nvm missing (needed by Plan 2 frontend build only)"
fi

if command -v tailscale >/dev/null 2>&1; then
  ok "tailscale: $(tailscale version | head -n1)"
  serve_status="$(tailscale serve status 2>&1)"
  if grep -q '127.0.0.1:8097' <<<"$serve_status"; then
    ok "tailscale serve proxies to 127.0.0.1:8097"
  else
    warn "tailscale serve is not set up yet. After deploy: sudo tailscale serve --bg --https=443 http://127.0.0.1:8097"
  fi
else
  bad "tailscale missing"
fi

if sudo -n true 2>/dev/null; then
  ufw_status="$(sudo -n ufw status 2>&1)"
  if grep -qE '^8097' <<<"$ufw_status"; then
    bad "UFW has a rule for port 8097. Remove it: the app must not be reachable directly"
  else
    ok "UFW has no rule for port 8097"
  fi
else
  warn "skipped UFW check (needs sudo). Run: sudo -v && bash $0"
fi

if ss -ltnH 2>/dev/null | awk '{print $4}' | grep -E ':8097$' | grep -vqE '^(127\.0\.0\.1|\[::1\]):8097$'; then
  bad "something listens on port 8097 on a non-loopback address"
else
  ok "nothing listens on port 8097 outside loopback"
fi

jf_version="$(curl -s --max-time 5 http://127.0.0.1:8096/System/Info/Public | grep -o '"Version":"[^"]*"')"
if [[ -n "$jf_version" ]]; then
  ok "jellyfin $jf_version"
else
  bad "jellyfin does not answer on http://127.0.0.1:8096"
fi

exit "$FAILED"
```

- [ ] **Step 2: Check syntax and make it executable**

Run (repo root): `bash -n app/deploy/check-nas.sh && chmod +x app/deploy/check-nas.sh && echo syntax-ok`
Expected: `syntax-ok`

- [ ] **Step 3: Commit**

```bash
git add app/deploy/check-nas.sh
git commit -m "feat(deploy): add read-only NAS preflight check script"
```

---

### Task 2: Project scaffold and config loading

**Files:**
- Create: `app/backend/pyproject.toml`
- Create: `app/backend/wyc_music_streaming/__init__.py`
- Create: `app/backend/wyc_music_streaming/config.py`
- Create: `app/backend/tests/conftest.py`
- Create: `app/backend/tests/test_config.py`
- Modify: `.gitignore` (create it if missing)

**Interfaces:**
- Consumes: nothing
- Produces:
  - `class ConfigError(Exception)`
  - `@dataclass(frozen=True) class User: name: str; tailscale_login: str; music_dir: Path; jellyfin_user: str | None = None`
  - `@dataclass(frozen=True) class ServerConfig: host: str; port: int; data_dir: Path; dev: bool; dev_user: str | None`
  - `@dataclass(frozen=True) class JellyfinConfig: url: str; api_key: str`
  - `@dataclass(frozen=True) class Config: server; jellyfin; concurrency: int; users: dict[str, User]` with `user_by_login(login: str) -> User | None` (case-insensitive)
  - `load_config(path: Path) -> Config`
  - test fixtures: `config` (a valid `Config`), `write_cfg(**kw) -> Path`, `make_audio(path: Path) -> Path`

- [ ] **Step 1: Install tools on the dev machine**

Run: `command -v uv || curl -LsSf https://astral.sh/uv/install.sh | sh; command -v ffmpeg || sudo apt install -y ffmpeg`
Expected: both commands exist afterwards (`uv --version`, `ffmpeg -version` print versions).

- [ ] **Step 2: Write `pyproject.toml` and the package marker**

`app/backend/pyproject.toml`:

```toml
[project]
name = "wyc-music-streaming"
version = "0.1.0"
description = "Download music from YouTube into per-user NAS libraries for Jellyfin"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn>=0.32",
    "yt-dlp[default]",   # no floor: update.sh and the weekly timer always upgrade it
    "mutagen>=1.47",
    "httpx>=0.27",
]

[dependency-groups]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["wyc_music_streaming"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
testpaths = ["tests"]
```

`app/backend/wyc_music_streaming/__init__.py`:

```python
"""WYC-music-streaming backend."""
```

Append to the repo root `.gitignore`:

```
# WYC-music-streaming app
app/backend/.venv/
__pycache__/
.pytest_cache/
app/frontend/node_modules/
app/frontend/build/
# never commit real config or keys (public repo)
config.toml
*.key
```

- [ ] **Step 3: Create the venv and lock file**

Run: `uv sync --python 3.12`
Expected: creates `.venv/` and `uv.lock`, ends with `Installed N packages`.

- [ ] **Step 4: Write test fixtures**

`app/backend/tests/conftest.py`:

```python
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
```

- [ ] **Step 5: Write the failing config tests**

`app/backend/tests/test_config.py`:

```python
import pytest

from wyc_music_streaming.config import ConfigError, load_config


def test_loads_users_and_defaults(config, tmp_path):
    assert config.server.host == "127.0.0.1"
    assert config.server.port == 8097
    assert config.server.data_dir == tmp_path / "data"
    assert config.server.dev is False
    assert config.jellyfin.url == "http://jellyfin.test"
    assert config.jellyfin.api_key == "test-key"
    assert config.concurrency == 2
    wick = config.users["wick"]
    assert wick.tailscale_login == "wick@example.com"
    assert wick.music_dir == tmp_path / "wick-music"
    assert wick.jellyfin_user == "wick"
    assert config.users["safeena"].jellyfin_user is None


def test_user_by_login_is_case_insensitive(config):
    assert config.user_by_login("WICK@example.com").name == "wick"
    assert config.user_by_login(" safeena@example.com ").name == "safeena"
    assert config.user_by_login("stranger@example.com") is None


def test_rejects_non_loopback_host(write_cfg):
    with pytest.raises(ConfigError, match="loopback"):
        load_config(write_cfg(server_extra='host = "0.0.0.0"'))


def test_non_loopback_host_allowed_in_dev_mode(write_cfg):
    cfg = load_config(write_cfg(server_extra='host = "0.0.0.0"\ndev = true\ndev_user = "wick"'))
    assert cfg.server.host == "0.0.0.0"
    assert cfg.server.dev_user == "wick"


def test_rejects_missing_music_dir(write_cfg):
    users = '[users.x]\ntailscale_login = "x@example.com"\nmusic_dir = "/nonexistent/wyc-test"'
    with pytest.raises(ConfigError, match="music_dir does not exist"):
        load_config(write_cfg(users=users))


def test_rejects_duplicate_login(write_cfg, tmp_path):
    users = f"""
[users.a]
tailscale_login = "same@example.com"
music_dir = "{tmp_path / 'wick-music'}"
[users.b]
tailscale_login = "SAME@example.com"
music_dir = "{tmp_path / 'safeena-music'}"
"""
    with pytest.raises(ConfigError, match="duplicate tailscale_login"):
        load_config(write_cfg(users=users))


def test_rejects_missing_key_file(write_cfg, tmp_path):
    path = write_cfg()
    (tmp_path / "jellyfin.key").unlink()
    with pytest.raises(ConfigError, match="api_key_file not readable"):
        load_config(path)


def test_rejects_unknown_dev_user(write_cfg):
    with pytest.raises(ConfigError, match="dev_user"):
        load_config(write_cfg(server_extra='dev = true\ndev_user = "nobody"'))


def test_rejects_bad_concurrency(write_cfg, tmp_path):
    path = write_cfg()
    path.write_text(path.read_text().replace("concurrency = 2", "concurrency = 9"))
    with pytest.raises(ConfigError, match="concurrency"):
        load_config(path)


def test_rejects_missing_file(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope.toml")
```

- [ ] **Step 6: Run the tests to see them fail**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'wyc_music_streaming.config'`

- [ ] **Step 7: Implement `config.py`**

`app/backend/wyc_music_streaming/config.py`:

```python
"""Load and validate the TOML config (default /etc/wyc-music-streaming/config.toml)."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}
DEFAULT_DATA_DIR = Path("/var/lib/wyc-music-streaming")


class ConfigError(Exception):
    """The config file is missing, invalid, or points at unusable paths."""


@dataclass(frozen=True)
class User:
    name: str
    tailscale_login: str
    music_dir: Path
    jellyfin_user: str | None = None


@dataclass(frozen=True)
class ServerConfig:
    host: str
    port: int
    data_dir: Path
    dev: bool
    dev_user: str | None


@dataclass(frozen=True)
class JellyfinConfig:
    url: str
    api_key: str


@dataclass(frozen=True)
class Config:
    server: ServerConfig
    jellyfin: JellyfinConfig
    concurrency: int
    users: dict[str, User]

    def user_by_login(self, login: str) -> User | None:
        wanted = login.strip().lower()
        for user in self.users.values():
            if user.tailscale_login == wanted:
                return user
        return None


def _require(table: dict[str, Any], key: str, where: str) -> Any:
    if key not in table:
        raise ConfigError(f"missing {where}.{key}")
    return table[key]


def load_config(path: Path) -> Config:
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ConfigError(f"config file not found: {path}") from None
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML in {path}: {exc}") from None

    s = raw.get("server", {})
    server = ServerConfig(
        host=str(s.get("host", "127.0.0.1")),
        port=int(s.get("port", 8097)),
        data_dir=Path(s.get("data_dir", DEFAULT_DATA_DIR)),
        dev=bool(s.get("dev", False)),
        dev_user=s.get("dev_user"),
    )
    if server.host not in LOOPBACK_HOSTS and not server.dev:
        raise ConfigError(
            f"server.host must be a loopback address, got {server.host!r}. "
            "The Tailscale-User-Login header is only trustworthy behind tailscale serve."
        )

    j = raw.get("jellyfin")
    if not isinstance(j, dict):
        raise ConfigError("missing [jellyfin] section")
    key_file = Path(_require(j, "api_key_file", "jellyfin"))
    try:
        api_key = key_file.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ConfigError(f"jellyfin.api_key_file not readable: {key_file} ({exc.strerror})") from None
    if not api_key:
        raise ConfigError(f"jellyfin.api_key_file is empty: {key_file}")
    jellyfin = JellyfinConfig(url=str(_require(j, "url", "jellyfin")).rstrip("/"), api_key=api_key)

    concurrency = int(raw.get("download", {}).get("concurrency", 2))
    if not 1 <= concurrency <= 4:
        raise ConfigError(f"download.concurrency must be 1-4, got {concurrency}")

    users: dict[str, User] = {}
    seen_logins: dict[str, str] = {}
    for name, u in raw.get("users", {}).items():
        where = f"users.{name}"
        login = str(_require(u, "tailscale_login", where)).strip().lower()
        if login in seen_logins:
            raise ConfigError(f"duplicate tailscale_login {login!r} in users.{seen_logins[login]} and {where}")
        seen_logins[login] = name
        music_dir = Path(_require(u, "music_dir", where))
        if not music_dir.is_dir():
            raise ConfigError(f"{where}.music_dir does not exist: {music_dir}")
        if not os.access(music_dir, os.W_OK | os.X_OK):
            raise ConfigError(f"{where}.music_dir is not writable: {music_dir}")
        users[name] = User(
            name=name,
            tailscale_login=login,
            music_dir=music_dir,
            jellyfin_user=u.get("jellyfin_user"),
        )
    if not users:
        raise ConfigError("config has no [users.<name>] sections")
    if server.dev_user is not None and server.dev_user not in users:
        raise ConfigError(f"server.dev_user {server.dev_user!r} is not a configured user")

    return Config(server=server, jellyfin=jellyfin, concurrency=concurrency, users=users)
```

- [ ] **Step 8: Run the tests to see them pass**

Run: `uv run pytest tests/test_config.py -v`
Expected: 10 passed

- [ ] **Step 9: Commit**

```bash
git add .gitignore app/backend/pyproject.toml app/backend/uv.lock app/backend/wyc_music_streaming app/backend/tests
git commit -m "feat(backend): scaffold package and validated config loading"
```

---

### Task 3: Auth from the Tailscale header

**Files:**
- Create: `app/backend/wyc_music_streaming/auth.py`
- Test: `app/backend/tests/test_auth.py`

**Interfaces:**
- Consumes: `Config`, `User`, `load_config` (Task 2)
- Produces:
  - `HEADER = "Tailscale-User-Login"`
  - `resolve_user(headers: Mapping[str, str], config: Config) -> User | None`. Starlette `Headers` are case-insensitive, so the API passes `request.headers` directly.

- [ ] **Step 1: Write the failing tests**

`app/backend/tests/test_auth.py`:

```python
from wyc_music_streaming.auth import HEADER, resolve_user
from wyc_music_streaming.config import load_config


def test_known_login(config):
    assert resolve_user({HEADER: "wick@example.com"}, config).name == "wick"


def test_login_is_case_insensitive(config):
    assert resolve_user({HEADER: "Safeena@Example.COM"}, config).name == "safeena"


def test_unknown_login(config):
    assert resolve_user({HEADER: "stranger@example.com"}, config) is None


def test_missing_header(config):
    assert resolve_user({}, config) is None


def test_dev_mode_uses_dev_user_without_header(write_cfg):
    cfg = load_config(write_cfg(server_extra='dev = true\ndev_user = "wick"'))
    assert resolve_user({}, cfg).name == "wick"


def test_dev_mode_still_rejects_unknown_header(write_cfg):
    cfg = load_config(write_cfg(server_extra='dev = true\ndev_user = "wick"'))
    assert resolve_user({HEADER: "stranger@example.com"}, cfg) is None
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest tests/test_auth.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'wyc_music_streaming.auth'`

- [ ] **Step 3: Implement `auth.py`**

```python
"""Resolve the current user from the Tailscale identity header.

The header is trustworthy only because the server binds 127.0.0.1 and
tailscale serve is the only thing that can reach it (see config.py).
A future OIDC mode adds another implementation of resolve_user.
"""
from __future__ import annotations

from collections.abc import Mapping

from .config import Config, User

HEADER = "Tailscale-User-Login"


def resolve_user(headers: Mapping[str, str], config: Config) -> User | None:
    login = headers.get(HEADER)
    if login:
        return config.user_by_login(login)
    if config.server.dev and config.server.dev_user:
        return config.users[config.server.dev_user]
    return None
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `uv run pytest tests/test_auth.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add app/backend/wyc_music_streaming/auth.py app/backend/tests/test_auth.py
git commit -m "feat(backend): resolve user from Tailscale-User-Login header"
```

---

### Task 4: Safe paths and file names

**Files:**
- Create: `app/backend/wyc_music_streaming/paths.py`
- Test: `app/backend/tests/test_paths.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `class UnsafePath(ValueError)`
  - `sanitize_name(name: str, fallback: str = "Unknown") -> str`
  - `safe_resolve(root: Path, rel: str) -> Path` (resolved absolute path strictly inside `root`; raises `UnsafePath`)
  - `unique_path(path: Path) -> Path`
  - `track_filename(title: str, ext: str, track_no: int | None = None) -> str`

- [ ] **Step 1: Write the failing tests**

`app/backend/tests/test_paths.py`:

```python
import pytest

from wyc_music_streaming.paths import (
    UnsafePath,
    safe_resolve,
    sanitize_name,
    track_filename,
    unique_path,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Numb", "Numb"),
        ('AC/DC: "Back" <In> Black?', "ACDC Back In Black"),
        ("  spaced  ", "spaced"),
        ("..", "Unknown"),
        ("", "Unknown"),
        ("a\x00b\nc", "abc"),
        ("x" * 200, "x" * 120),
        ("เพลงไทย", "เพลงไทย"),
    ],
)
def test_sanitize_name(raw, expected):
    assert sanitize_name(raw) == expected


def test_sanitize_name_custom_fallback():
    assert sanitize_name("???", fallback="Singles") == "Singles"


def test_safe_resolve_inside(tmp_path):
    root = tmp_path / "music"
    (root / "A").mkdir(parents=True)
    assert safe_resolve(root, "A/x.m4a") == (root / "A" / "x.m4a").resolve()


@pytest.mark.parametrize("rel", ["../etc/passwd", "A/../../x.m4a", "/etc/passwd", "", "."])
def test_safe_resolve_rejects_escape(tmp_path, rel):
    root = tmp_path / "music"
    root.mkdir()
    with pytest.raises(UnsafePath):
        safe_resolve(root, rel)


def test_safe_resolve_rejects_symlink_escape(tmp_path):
    root = tmp_path / "music"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "link").symlink_to(outside)
    with pytest.raises(UnsafePath):
        safe_resolve(root, "link/x.m4a")


def test_unique_path(tmp_path):
    p = tmp_path / "a.m4a"
    assert unique_path(p) == p
    p.touch()
    assert unique_path(p) == tmp_path / "a (2).m4a"
    (tmp_path / "a (2).m4a").touch()
    assert unique_path(p) == tmp_path / "a (3).m4a"


def test_track_filename():
    assert track_filename("Numb", "m4a") == "Numb.m4a"
    assert track_filename("Faint", "m4a", 7) == "07 Faint.m4a"
    assert track_filename("a/b", "opus") == "ab.opus"
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest tests/test_paths.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'wyc_music_streaming.paths'`

- [ ] **Step 3: Implement `paths.py`**

```python
"""Safe file names and path checks under a user's music_dir."""
from __future__ import annotations

import re
from pathlib import Path

FORBIDDEN = re.compile(r'[/\\:*?"<>|\x00-\x1f]')
MAX_NAME = 120


class UnsafePath(ValueError):
    """A client-supplied path points outside the user's music_dir."""


def sanitize_name(name: str, fallback: str = "Unknown") -> str:
    cleaned = FORBIDDEN.sub("", name).strip().strip(".").strip()
    cleaned = cleaned[:MAX_NAME].strip()
    return cleaned or fallback


def safe_resolve(root: Path, rel: str) -> Path:
    """Resolve rel under root, following symlinks. Reject root itself and anything outside."""
    root_resolved = root.resolve()
    target = (root_resolved / rel).resolve()
    if target == root_resolved or not target.is_relative_to(root_resolved):
        raise UnsafePath(rel)
    return target


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    n = 2
    while True:
        candidate = path.with_name(f"{path.stem} ({n}){path.suffix}")
        if not candidate.exists():
            return candidate
        n += 1


def track_filename(title: str, ext: str, track_no: int | None = None) -> str:
    base = sanitize_name(title)
    if track_no:
        base = f"{track_no:02d} {base}"
    return f"{base}.{ext}"
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `uv run pytest tests/test_paths.py -v`
Expected: 18 passed

- [ ] **Step 5: Commit**

```bash
git add app/backend/wyc_music_streaming/paths.py app/backend/tests/test_paths.py
git commit -m "feat(backend): add safe path resolution and file name sanitizing"
```

---

### Task 5: Metadata cleanup

**Files:**
- Create: `app/backend/wyc_music_streaming/metadata.py`
- Test: `app/backend/tests/test_metadata.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `@dataclass(frozen=True) class Suggested: title: str; artist: str; album: str`
  - `clean(title: str, channel: str, *, artist: str | None = None, track: str | None = None, album: str | None = None, playlist_title: str | None = None) -> Suggested`

- [ ] **Step 1: Write the failing tests**

`app/backend/tests/test_metadata.py`:

```python
import pytest

from wyc_music_streaming.metadata import Suggested, clean


@pytest.mark.parametrize(
    ("title", "channel", "expected"),
    [
        ("Linkin Park - Numb (Official Music Video) [4K UPGRADE]", "Linkin Park",
         Suggested("Numb", "Linkin Park", "Singles")),
        ("Numb", "Linkin Park - Topic", Suggested("Numb", "Linkin Park", "Singles")),
        ("Sade - Smooth Operator (Official Video) | HD", "SadeVEVO",
         Suggested("Smooth Operator", "Sade", "Singles")),
        ("Kanye West - Stronger (Lyrics)", "Lyrics Channel",
         Suggested("Stronger", "Kanye West", "Singles")),
        ("Midnight City (Visualizer)", "M83VEVO", Suggested("Midnight City", "M83", "Singles")),
        ("Sade – Smooth Operator", "Some Channel", Suggested("Smooth Operator", "Sade", "Singles")),
        ("Faint (Official Audio)", "Linkin Park", Suggested("Faint", "Linkin Park", "Singles")),
        ("Numb [HD]", "Linkin Park", Suggested("Numb", "Linkin Park", "Singles")),
        ("Numb (Lyric Video)", "Linkin Park", Suggested("Numb", "Linkin Park", "Singles")),
        ("Linkin Park - Numb [Official Music Video]", "x", Suggested("Numb", "Linkin Park", "Singles")),
    ],
)
def test_clean_titles(title, channel, expected):
    assert clean(title, channel) == expected


def test_uses_ytdlp_artist_track_album_when_present():
    got = clean("whatever (Official Video)", "Linkin Park - Topic",
                artist="Linkin Park", track="Numb", album="Meteora")
    assert got == Suggested("Numb", "Linkin Park", "Meteora")


def test_strips_artist_prefix_matching_known_artist():
    got = clean("Linkin Park - Numb (Official Video)", "Linkin Park", artist="Linkin Park")
    assert got == Suggested("Numb", "Linkin Park", "Singles")


def test_playlist_title_is_default_album():
    got = clean("Some Phonk Track", "PhonkChannel", playlist_title="Phonk Mix")
    assert got == Suggested("Some Phonk Track", "PhonkChannel", "Phonk Mix")


def test_title_first_when_right_side_is_the_channel():
    # Real YouTube title seen in a dev run: "Title – Artist", uploaded by the artist.
    got = clean("Numb (Official Music Video) [4K UPGRADE] – Linkin Park", "Linkin Park")
    assert got == Suggested("Numb", "Linkin Park", "Singles")


def test_empty_values_get_fallbacks():
    assert clean("", "") == Suggested("Unknown", "Unknown Artist", "Singles")
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest tests/test_metadata.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'wyc_music_streaming.metadata'`

- [ ] **Step 3: Implement `metadata.py`**

```python
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
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `uv run pytest tests/test_metadata.py -v`
Expected: 15 passed

- [ ] **Step 5: Commit**

```bash
git add app/backend/wyc_music_streaming/metadata.py app/backend/tests/test_metadata.py
git commit -m "feat(backend): clean YouTube titles into suggested tags"
```

---

### Task 6: Read and write audio tags

**Files:**
- Create: `app/backend/wyc_music_streaming/tags.py`
- Test: `app/backend/tests/test_tags.py`

**Interfaces:**
- Consumes: `make_audio` fixture (Task 2)
- Produces:
  - `@dataclass(frozen=True) class TagData: title: str; artist: str; album: str; album_artist: str; video_id: str; track_no: int | None = None; year: str | None = None; cover_jpeg: bytes | None = None`
  - `write_tags(path: Path, tags: TagData) -> None`: supports `.m4a`, `.opus`, `.ogg`; raises `ValueError("unsupported container: …")` otherwise
  - `read_tags(path: Path) -> dict[str, Any]` with keys `title, artist, album, album_artist, year, track_no, video_id, duration` (missing → `None`; unreadable file → `{}`)

- [ ] **Step 1: Write the failing tests**

`app/backend/tests/test_tags.py`:

```python
import pytest
from mutagen.mp4 import MP4
from mutagen.oggopus import OggOpus

from wyc_music_streaming.tags import TagData, read_tags, write_tags

FULL = TagData(
    title="Faint", artist="Linkin Park", album="Meteora", album_artist="Linkin Park",
    video_id="kXYiU_JCYtU", track_no=7, year="2003", cover_jpeg=b"COVER",
)


def test_m4a_round_trip(make_audio, tmp_path):
    path = make_audio(tmp_path / "a.m4a")
    write_tags(path, FULL)
    got = read_tags(path)
    assert {k: got[k] for k in ("title", "artist", "album", "album_artist", "year", "track_no", "video_id")} == {
        "title": "Faint", "artist": "Linkin Park", "album": "Meteora", "album_artist": "Linkin Park",
        "year": "2003", "track_no": 7, "video_id": "kXYiU_JCYtU",
    }
    assert got["duration"] == pytest.approx(1.0, abs=0.2)
    assert MP4(path)["covr"][0] == b"COVER"


def test_opus_round_trip(make_audio, tmp_path):
    path = make_audio(tmp_path / "a.opus")
    write_tags(path, FULL)
    got = read_tags(path)
    assert got["title"] == "Faint"
    assert got["album_artist"] == "Linkin Park"
    assert got["track_no"] == 7
    assert got["video_id"] == "kXYiU_JCYtU"
    assert OggOpus(path)["metadata_block_picture"]


def test_minimal_tags_without_optional_fields(make_audio, tmp_path):
    path = make_audio(tmp_path / "a.m4a")
    write_tags(path, TagData("Numb", "Linkin Park", "Singles", "Linkin Park", "kXYiU_JCYtU"))
    got = read_tags(path)
    assert got["track_no"] is None
    assert got["year"] is None
    assert "covr" not in MP4(path)


def test_read_untagged_mp3(make_audio, tmp_path):
    got = read_tags(make_audio(tmp_path / "a.mp3"))
    assert got["title"] is None
    assert got["video_id"] is None
    assert got["duration"] == pytest.approx(1.0, abs=0.2)


def test_read_non_audio_returns_empty(tmp_path):
    p = tmp_path / "x.m4a"
    p.write_bytes(b"not audio")
    assert read_tags(p) == {}


def test_write_unsupported_container(make_audio, tmp_path):
    with pytest.raises(ValueError, match="unsupported container"):
        write_tags(make_audio(tmp_path / "a.mp3"), FULL)
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest tests/test_tags.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'wyc_music_streaming.tags'`

- [ ] **Step 3: Implement `tags.py`**

```python
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
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `uv run pytest tests/test_tags.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add app/backend/wyc_music_streaming/tags.py app/backend/tests/test_tags.py
git commit -m "feat(backend): read and write audio tags with mutagen"
```

---

### Task 7: Library scan, index, and delete

**Files:**
- Create: `app/backend/wyc_music_streaming/library.py`
- Test: `app/backend/tests/test_library.py`

**Interfaces:**
- Consumes: `User` (Task 2), `safe_resolve`, `UnsafePath` (Task 4), `read_tags`, `write_tags`, `TagData` (Task 6)
- Produces:
  - `AUDIO_EXTS: frozenset[str]` = `{".m4a", ".mp3", ".opus", ".flac", ".ogg"}`
  - `@dataclass(frozen=True) class Track: path: str` (posix, relative to `music_dir`)`; title: str; artist: str; album: str; duration: float | None; video_id: str | None; track_no: int | None` with `to_dict() -> dict`
  - `read_track(root: Path, file: Path) -> Track`
  - `scan_dir(root: Path) -> list[Track]` (skips dot-dirs and dot-files)
  - `class Library(users: dict[str, User])` with:
    - `rescan(user: str) -> int`
    - `rescan_all() -> None`
    - `add_file(user: str, file: Path) -> Track`
    - `tracks(user: str) -> list[Track]`
    - `video_ids(user: str) -> set[str]`
    - `has_video(user: str, video_id: str) -> bool`
    - `tree(user: str) -> list[dict]`. Shape: `[{"artist": str, "albums": [{"album": str, "tracks": [Track.to_dict()]}]}]`, sorted case-insensitively. Tracks are sorted by `track_no`, then title.
    - `delete(user: str, rel_path: str) -> None`. Raises `UnsafePath` or `FileNotFoundError`.

- [ ] **Step 1: Write the failing tests**

`app/backend/tests/test_library.py`:

```python
import pytest

from wyc_music_streaming.library import Library, scan_dir
from wyc_music_streaming.paths import UnsafePath
from wyc_music_streaming.tags import TagData, write_tags


@pytest.fixture
def tagged(make_audio):
    def _tagged(path, title, artist="Linkin Park", album="Meteora", video_id="kXYiU_JCYtU", track_no=None):
        make_audio(path)
        write_tags(path, TagData(title, artist, album, artist, video_id, track_no=track_no))
        return path
    return _tagged


def test_scan_reads_tags_and_falls_back_to_folders(config, make_audio, tagged):
    root = config.users["wick"].music_dir
    tagged(root / "LP" / "Meteora" / "x.m4a", "Numb", track_no=13)
    make_audio(root / "Sade" / "Diamond Life" / "Smooth Operator.mp3")
    make_audio(root / ".wyc-music-streaming-tmp" / "9.m4a")
    (root / "notes.txt").write_text("not audio")

    tracks = {t.path: t for t in scan_dir(root)}

    assert set(tracks) == {"LP/Meteora/x.m4a", "Sade/Diamond Life/Smooth Operator.mp3"}
    t = tracks["LP/Meteora/x.m4a"]
    assert (t.title, t.artist, t.album, t.video_id, t.track_no) == ("Numb", "Linkin Park", "Meteora", "kXYiU_JCYtU", 13)
    u = tracks["Sade/Diamond Life/Smooth Operator.mp3"]
    assert (u.title, u.artist, u.album, u.video_id) == ("Smooth Operator", "Sade", "Diamond Life", None)


def test_file_at_root_uses_unknown_artist(config, make_audio):
    root = config.users["wick"].music_dir
    make_audio(root / "loose.m4a")
    [t] = scan_dir(root)
    assert (t.artist, t.album, t.title) == ("Unknown Artist", "Singles", "loose")


def test_index_tree_and_video_ids(config, tagged):
    root = config.users["wick"].music_dir
    tagged(root / "Linkin Park" / "Meteora" / "13 Numb.m4a", "Numb", track_no=13, video_id="aaaaaaaaaaa")
    tagged(root / "Linkin Park" / "Meteora" / "07 Faint.m4a", "Faint", track_no=7, video_id="bbbbbbbbbbb")
    lib = Library(config.users)
    lib.rescan_all()

    tree = lib.tree("wick")
    assert [a["artist"] for a in tree] == ["Linkin Park"]
    [album] = tree[0]["albums"]
    assert album["album"] == "Meteora"
    assert [t["title"] for t in album["tracks"]] == ["Faint", "Numb"]
    assert lib.video_ids("wick") == {"aaaaaaaaaaa", "bbbbbbbbbbb"}
    assert lib.has_video("wick", "aaaaaaaaaaa")
    assert lib.tree("safeena") == []


def test_add_file_updates_index(config, tagged):
    lib = Library(config.users)
    lib.rescan_all()
    root = config.users["wick"].music_dir
    path = tagged(root / "Linkin Park" / "Singles" / "Numb.m4a", "Numb", album="Singles")
    track = lib.add_file("wick", path)
    assert track.path == "Linkin Park/Singles/Numb.m4a"
    assert lib.has_video("wick", "kXYiU_JCYtU")


def test_delete_removes_file_and_empty_dirs(config, tagged):
    root = config.users["wick"].music_dir
    tagged(root / "Linkin Park" / "Meteora" / "Numb.m4a", "Numb")
    lib = Library(config.users)
    lib.rescan_all()

    lib.delete("wick", "Linkin Park/Meteora/Numb.m4a")

    assert not (root / "Linkin Park").exists()
    assert root.is_dir()
    assert lib.tracks("wick") == []


def test_delete_keeps_non_empty_album(config, tagged):
    root = config.users["wick"].music_dir
    tagged(root / "Linkin Park" / "Meteora" / "Numb.m4a", "Numb", video_id="aaaaaaaaaaa")
    tagged(root / "Linkin Park" / "Meteora" / "Faint.m4a", "Faint", video_id="bbbbbbbbbbb")
    lib = Library(config.users)
    lib.rescan_all()

    lib.delete("wick", "Linkin Park/Meteora/Numb.m4a")

    assert (root / "Linkin Park" / "Meteora" / "Faint.m4a").exists()
    assert lib.video_ids("wick") == {"bbbbbbbbbbb"}


def test_delete_rejects_traversal(config):
    lib = Library(config.users)
    with pytest.raises(UnsafePath):
        lib.delete("wick", "../safeena-music/x.m4a")


def test_delete_missing_or_non_audio(config):
    root = config.users["wick"].music_dir
    (root / "notes.txt").write_text("x")
    lib = Library(config.users)
    with pytest.raises(FileNotFoundError):
        lib.delete("wick", "nope.m4a")
    with pytest.raises(FileNotFoundError):
        lib.delete("wick", "notes.txt")
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest tests/test_library.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'wyc_music_streaming.library'`

- [ ] **Step 3: Implement `library.py`**

```python
"""Scan users' music folders into an in-memory index; delete tracks safely."""
from __future__ import annotations

import os
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .config import User
from .paths import safe_resolve
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
        parent = target.parent
        while parent != root_resolved and parent.is_relative_to(root_resolved):
            try:
                parent.rmdir()  # only succeeds when empty
            except OSError:
                break
            parent = parent.parent
        key = target.relative_to(root_resolved).as_posix()
        with self._lock:
            self._tracks[user].pop(key, None)
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `uv run pytest tests/test_library.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add app/backend/wyc_music_streaming/library.py app/backend/tests/test_library.py
git commit -m "feat(backend): add library scan, index and safe delete"
```

---

### Task 8: SQLite job store

**Files:**
- Create: `app/backend/wyc_music_streaming/jobs.py`
- Test: `app/backend/tests/test_jobs.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `@dataclass(frozen=True) class NewJob: video_id: str; title: str; artist: str; album: str; track_no: int | None = None; year: str | None = None; cover_url: str | None = None`
  - `@dataclass(frozen=True) class Job` with fields `id, user, video_id, title, artist, album, track_no, year, cover_url, box_id, status, progress, error, final_path, created_at, updated_at` and `to_dict() -> dict`
  - `class JobStore(path: Path)` with:
    - `add(user, items: list[NewJob], box_id: str | None = None) -> list[Job]`
    - `get(job_id) -> Job | None`
    - `has_active(user, video_id) -> bool`
    - `claim_next() -> Job | None` (oldest queued job → `downloading`)
    - `set_progress(job_id, fraction)`
    - `finish(job_id, final_path)`
    - `fail(job_id, error)`
    - `cancel(user, job_id) -> bool` (queued only)
    - `retry(user, job_id) -> bool` (failed only)
    - `recover() -> int` (`downloading` → `queued`)
    - `list_for_user(user, history=50) -> list[Job]` (active jobs oldest first, then the newest finished jobs)
    - `close()`

- [ ] **Step 1: Write the failing tests**

`app/backend/tests/test_jobs.py`:

```python
import re

import pytest

from wyc_music_streaming.jobs import JobStore, NewJob

ISO = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")


@pytest.fixture
def store(tmp_path):
    s = JobStore(tmp_path / "data" / "app.db")
    yield s
    s.close()


def item(vid="aaaaaaaaaaa", **kw):
    return NewJob(video_id=vid, title="Numb", artist="Linkin Park", album="Meteora", **kw)


def test_add_creates_queued_jobs(store):
    [job] = store.add("wick", [item(track_no=13, year="2003", cover_url="https://img.test/c.jpg")], box_id="box1")
    assert job.status == "queued"
    assert job.progress == 0
    assert (job.user, job.video_id, job.track_no, job.year, job.box_id) == ("wick", "aaaaaaaaaaa", 13, "2003", "box1")
    assert ISO.match(job.created_at)
    assert store.get(job.id) == job


def test_claim_next_takes_oldest_queued(store):
    first, second = store.add("wick", [item("aaaaaaaaaaa"), item("bbbbbbbbbbb")])
    claimed = store.claim_next()
    assert claimed.id == first.id
    assert claimed.status == "downloading"
    assert store.claim_next().id == second.id
    assert store.claim_next() is None


def test_progress_finish_fail(store):
    a, b = store.add("wick", [item("aaaaaaaaaaa"), item("bbbbbbbbbbb")])
    store.set_progress(a.id, 1.7)
    assert store.get(a.id).progress == 1.0
    store.finish(a.id, "Linkin Park/Meteora/Numb.m4a")
    done = store.get(a.id)
    assert (done.status, done.progress, done.final_path) == ("done", 1.0, "Linkin Park/Meteora/Numb.m4a")
    store.fail(b.id, "Video unavailable")
    assert (store.get(b.id).status, store.get(b.id).error) == ("failed", "Video unavailable")


def test_cancel_only_queued_and_own(store):
    a, b = store.add("wick", [item("aaaaaaaaaaa"), item("bbbbbbbbbbb")])
    assert store.cancel("safeena", a.id) is False
    assert store.cancel("wick", a.id) is True
    assert store.get(a.id).status == "cancelled"
    store.claim_next()  # b is now downloading
    assert store.cancel("wick", b.id) is False


def test_retry_only_failed(store):
    [a] = store.add("wick", [item()])
    assert store.retry("wick", a.id) is False
    store.fail(a.id, "boom")
    assert store.retry("wick", a.id) is True
    again = store.get(a.id)
    assert (again.status, again.error) == ("queued", None)


def test_has_active(store):
    [a] = store.add("wick", [item()])
    assert store.has_active("wick", "aaaaaaaaaaa")
    assert not store.has_active("safeena", "aaaaaaaaaaa")
    store.claim_next()
    assert store.has_active("wick", "aaaaaaaaaaa")
    store.finish(a.id, "x.m4a")
    assert not store.has_active("wick", "aaaaaaaaaaa")


def test_recover_requeues_downloading(store):
    store.add("wick", [item("aaaaaaaaaaa"), item("bbbbbbbbbbb")])
    store.claim_next()
    assert store.recover() == 1
    assert [j.status for j in store.list_for_user("wick")] == ["queued", "queued"]


def test_list_for_user_active_then_history(store):
    jobs = store.add("wick", [item(f"{c}" * 11) for c in "abcd"])
    store.add("safeena", [item("zzzzzzzzzzz")])
    store.fail(jobs[0].id, "x")
    store.finish(jobs[1].id, "y.m4a")
    listed = store.list_for_user("wick", history=1)
    assert [j.id for j in listed] == [jobs[2].id, jobs[3].id, jobs[1].id]


def test_persists_across_reopen(tmp_path):
    path = tmp_path / "app.db"
    s1 = JobStore(path)
    [a] = s1.add("wick", [item()])
    s1.close()
    s2 = JobStore(path)
    assert s2.get(a.id).video_id == "aaaaaaaaaaa"
    s2.close()
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest tests/test_jobs.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'wyc_music_streaming.jobs'`

- [ ] **Step 3: Implement `jobs.py`**

```python
"""SQLite job store (WAL mode). The only database the app has."""
from __future__ import annotations

import sqlite3
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  id          INTEGER PRIMARY KEY,
  user        TEXT NOT NULL,
  video_id    TEXT NOT NULL,
  title       TEXT NOT NULL,
  artist      TEXT NOT NULL,
  album       TEXT NOT NULL,
  track_no    INTEGER,
  year        TEXT,
  cover_url   TEXT,
  box_id      TEXT,
  status      TEXT NOT NULL CHECK (status IN ('queued','downloading','done','failed','cancelled')),
  progress    REAL NOT NULL DEFAULT 0,
  error       TEXT,
  final_path  TEXT,
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS jobs_user_status ON jobs(user, status);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class NewJob:
    video_id: str
    title: str
    artist: str
    album: str
    track_no: int | None = None
    year: str | None = None
    cover_url: str | None = None


@dataclass(frozen=True)
class Job:
    id: int
    user: str
    video_id: str
    title: str
    artist: str
    album: str
    track_no: int | None
    year: str | None
    cover_url: str | None
    box_id: str | None
    status: str
    progress: float
    error: str | None
    final_path: str | None
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class JobStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.executescript(SCHEMA)

    def close(self) -> None:
        self._db.close()

    def add(self, user: str, items: list[NewJob], box_id: str | None = None) -> list[Job]:
        now = _now()
        ids: list[int] = []
        with self._lock:
            self._db.execute("BEGIN")
            try:
                for it in items:
                    cur = self._db.execute(
                        "INSERT INTO jobs (user, video_id, title, artist, album, track_no, year, cover_url,"
                        " box_id, status, progress, created_at, updated_at)"
                        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', 0, ?, ?)",
                        (user, it.video_id, it.title, it.artist, it.album, it.track_no, it.year,
                         it.cover_url, box_id, now, now),
                    )
                    ids.append(cur.lastrowid)
                self._db.execute("COMMIT")
            except Exception:
                self._db.execute("ROLLBACK")
                raise
        return [job for i in ids if (job := self.get(i)) is not None]

    def get(self, job_id: int) -> Job | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return Job(**dict(row)) if row else None

    def has_active(self, user: str, video_id: str) -> bool:
        with self._lock:
            row = self._db.execute(
                "SELECT 1 FROM jobs WHERE user = ? AND video_id = ? AND status IN ('queued','downloading') LIMIT 1",
                (user, video_id),
            ).fetchone()
        return row is not None

    def claim_next(self) -> Job | None:
        with self._lock:
            row = self._db.execute(
                "SELECT id FROM jobs WHERE status = 'queued' ORDER BY id LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            job_id = row["id"]
            self._db.execute(
                "UPDATE jobs SET status = 'downloading', progress = 0, error = NULL, updated_at = ? WHERE id = ?",
                (_now(), job_id),
            )
        return self.get(job_id)

    def _update(self, job_id: int, assignments: str, params: tuple[Any, ...]) -> None:
        with self._lock:
            self._db.execute(
                f"UPDATE jobs SET {assignments}, updated_at = ? WHERE id = ?",
                (*params, _now(), job_id),
            )

    def set_progress(self, job_id: int, fraction: float) -> None:
        self._update(job_id, "progress = ?", (max(0.0, min(1.0, fraction)),))

    def finish(self, job_id: int, final_path: str) -> None:
        self._update(job_id, "status = 'done', progress = 1, final_path = ?, error = NULL", (final_path,))

    def fail(self, job_id: int, error: str) -> None:
        self._update(job_id, "status = 'failed', error = ?", (error,))

    def cancel(self, user: str, job_id: int) -> bool:
        with self._lock:
            cur = self._db.execute(
                "UPDATE jobs SET status = 'cancelled', updated_at = ?"
                " WHERE id = ? AND user = ? AND status = 'queued'",
                (_now(), job_id, user),
            )
        return cur.rowcount == 1

    def retry(self, user: str, job_id: int) -> bool:
        with self._lock:
            cur = self._db.execute(
                "UPDATE jobs SET status = 'queued', progress = 0, error = NULL, updated_at = ?"
                " WHERE id = ? AND user = ? AND status = 'failed'",
                (_now(), job_id, user),
            )
        return cur.rowcount == 1

    def recover(self) -> int:
        with self._lock:
            cur = self._db.execute(
                "UPDATE jobs SET status = 'queued', progress = 0, updated_at = ? WHERE status = 'downloading'",
                (_now(),),
            )
        return cur.rowcount

    def list_for_user(self, user: str, history: int = 50) -> list[Job]:
        with self._lock:
            active = self._db.execute(
                "SELECT * FROM jobs WHERE user = ? AND status IN ('queued','downloading') ORDER BY id",
                (user,),
            ).fetchall()
            finished = self._db.execute(
                "SELECT * FROM jobs WHERE user = ? AND status NOT IN ('queued','downloading')"
                " ORDER BY updated_at DESC, id DESC LIMIT ?",
                (user, history),
            ).fetchall()
        return [Job(**dict(r)) for r in (*active, *finished)]
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `uv run pytest tests/test_jobs.py -v`
Expected: 9 passed

Note on `test_list_for_user_active_then_history`: `fail` and `finish` run within the same second, so `updated_at` ties. Then `id DESC` decides, and job 1 (finished last, higher id) comes first. That is why `history=1` returns `jobs[1]`.

- [ ] **Step 5: Commit**

```bash
git add app/backend/wyc_music_streaming/jobs.py app/backend/tests/test_jobs.py
git commit -m "feat(backend): add SQLite job store"
```

---

### Task 9: Jellyfin refresh with debounce

**Files:**
- Create: `app/backend/wyc_music_streaming/jellyfin.py`
- Test: `app/backend/tests/test_jellyfin.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `class JellyfinClient(url: str, api_key: str, *, transport: httpx.AsyncBaseTransport | None = None)` with:
    - `async refresh_library() -> bool` (never raises on HTTP errors)
    - `async aclose()`
  - `class RefreshScheduler(client: JellyfinClient, delay: float = 30.0)` with:
    - `schedule() -> None` (call inside the event loop; coalesces calls during `delay`)
    - `async refresh_now() -> bool`
    - `async aclose()`

- [ ] **Step 1: Write the failing tests**

`app/backend/tests/test_jellyfin.py`:

```python
import asyncio

import httpx

from wyc_music_streaming.jellyfin import JellyfinClient, RefreshScheduler


def recorder(status=204):
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(status)

    return httpx.MockTransport(handler), calls


async def test_refresh_sends_token_header():
    transport, calls = recorder()
    client = JellyfinClient("http://jf.test", "KEY", transport=transport)
    assert await client.refresh_library() is True
    [req] = calls
    assert req.method == "POST"
    assert req.url == "http://jf.test/Library/Refresh"
    assert req.headers["Authorization"] == 'MediaBrowser Token="KEY"'
    await client.aclose()


async def test_refresh_http_error_returns_false():
    transport, _ = recorder(status=500)
    client = JellyfinClient("http://jf.test", "KEY", transport=transport)
    assert await client.refresh_library() is False
    await client.aclose()


async def test_refresh_offline_returns_false():
    def handler(request):
        raise httpx.ConnectError("down", request=request)

    client = JellyfinClient("http://jf.test", "KEY", transport=httpx.MockTransport(handler))
    assert await client.refresh_library() is False
    await client.aclose()


async def test_scheduler_coalesces_calls():
    transport, calls = recorder()
    client = JellyfinClient("http://jf.test", "KEY", transport=transport)
    scheduler = RefreshScheduler(client, delay=0.05)
    scheduler.schedule()
    scheduler.schedule()
    scheduler.schedule()
    await asyncio.sleep(0.15)
    assert len(calls) == 1
    scheduler.schedule()
    await asyncio.sleep(0.15)
    assert len(calls) == 2
    await scheduler.aclose()
    await client.aclose()


async def test_refresh_now_cancels_pending():
    transport, calls = recorder()
    client = JellyfinClient("http://jf.test", "KEY", transport=transport)
    scheduler = RefreshScheduler(client, delay=0.05)
    scheduler.schedule()
    assert await scheduler.refresh_now() is True
    await asyncio.sleep(0.15)
    assert len(calls) == 1
    await scheduler.aclose()
    await client.aclose()
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest tests/test_jellyfin.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'wyc_music_streaming.jellyfin'`

- [ ] **Step 3: Implement `jellyfin.py`**

```python
"""Jellyfin HTTP client. Plan 1: library refresh only (Plan 3 adds users, items, playlists)."""
from __future__ import annotations

import asyncio
import contextlib
import logging

import httpx

log = logging.getLogger(__name__)


class JellyfinClient:
    def __init__(self, url: str, api_key: str, *, transport: httpx.AsyncBaseTransport | None = None):
        self._http = httpx.AsyncClient(
            base_url=url,
            headers={"Authorization": f'MediaBrowser Token="{api_key}"'},
            timeout=10.0,
            transport=transport,
        )

    async def refresh_library(self) -> bool:
        try:
            response = await self._http.post("/Library/Refresh")
            response.raise_for_status()
        except httpx.HTTPError as exc:
            log.warning("Jellyfin library refresh failed: %s", exc)
            return False
        return True

    async def aclose(self) -> None:
        await self._http.aclose()


class RefreshScheduler:
    """Run one refresh `delay` seconds after the first schedule() call; later calls in that window join it."""

    def __init__(self, client: JellyfinClient, delay: float = 30.0):
        self._client = client
        self._delay = delay
        self._task: asyncio.Task[None] | None = None

    def schedule(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.get_running_loop().create_task(self._later())

    async def _later(self) -> None:
        await asyncio.sleep(self._delay)
        await self._client.refresh_library()

    async def refresh_now(self) -> bool:
        await self._cancel_pending()
        return await self._client.refresh_library()

    async def _cancel_pending(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        self._task = None

    async def aclose(self) -> None:
        await self._cancel_pending()
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `uv run pytest tests/test_jellyfin.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add app/backend/wyc_music_streaming/jellyfin.py app/backend/tests/test_jellyfin.py
git commit -m "feat(backend): add debounced Jellyfin library refresh"
```

---

### Task 10: Per-user event broker for SSE

**Files:**
- Create: `app/backend/wyc_music_streaming/events.py`
- Test: `app/backend/tests/test_events.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `class EventBroker(maxsize: int = 100)` with:
    - `subscribe(user) -> asyncio.Queue[dict]`
    - `unsubscribe(user, queue)`
    - `publish(user, type_: str, data: Any)`. Event shape: `{"type": type_, "data": data}`. Drops the event when a queue is full. Call it only from the event loop thread.
  - `format_sse(event: dict) -> str`

- [ ] **Step 1: Write the failing tests**

`app/backend/tests/test_events.py`:

```python
from wyc_music_streaming.events import EventBroker, format_sse


async def test_publish_reaches_only_that_user():
    broker = EventBroker()
    wick = broker.subscribe("wick")
    safeena = broker.subscribe("safeena")
    broker.publish("wick", "job", {"id": 1})
    assert wick.get_nowait() == {"type": "job", "data": {"id": 1}}
    assert safeena.empty()


async def test_unsubscribe_stops_delivery():
    broker = EventBroker()
    q = broker.subscribe("wick")
    broker.unsubscribe("wick", q)
    broker.publish("wick", "job", {})
    assert q.empty()
    broker.unsubscribe("wick", q)  # second call is harmless


async def test_full_queue_drops_events():
    broker = EventBroker(maxsize=1)
    q = broker.subscribe("wick")
    broker.publish("wick", "job", {"n": 1})
    broker.publish("wick", "job", {"n": 2})
    assert q.qsize() == 1
    assert q.get_nowait()["data"] == {"n": 1}


def test_format_sse_keeps_thai_text():
    text = format_sse({"type": "library", "data": {"title": "เพลง"}})
    assert text == 'event: library\ndata: {"title": "เพลง"}\n\n'
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest tests/test_events.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'wyc_music_streaming.events'`

- [ ] **Step 3: Implement `events.py`**

```python
"""In-process pub/sub for Server-Sent Events, one channel per user."""
from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from typing import Any

log = logging.getLogger(__name__)


class EventBroker:
    def __init__(self, maxsize: int = 100):
        self._maxsize = maxsize
        self._subs: dict[str, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)

    def subscribe(self, user: str) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=self._maxsize)
        self._subs[user].add(queue)
        return queue

    def unsubscribe(self, user: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        subs = self._subs.get(user)
        if subs is None:
            return
        subs.discard(queue)
        if not subs:
            del self._subs[user]

    def publish(self, user: str, type_: str, data: Any) -> None:
        event = {"type": type_, "data": data}
        for queue in list(self._subs.get(user, ())):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                log.debug("dropping %s event for slow client of %s", type_, user)


def format_sse(event: dict[str, Any]) -> str:
    return f"event: {event['type']}\ndata: {json.dumps(event['data'], ensure_ascii=False)}\n\n"
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `uv run pytest tests/test_events.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add app/backend/wyc_music_streaming/events.py app/backend/tests/test_events.py
git commit -m "feat(backend): add per-user SSE event broker"
```

---

### Task 11: Search (keyword, video URL, playlist URL)

**Files:**
- Create: `app/backend/wyc_music_streaming/search.py`
- Test: `app/backend/tests/test_search.py`

**Interfaces:**
- Consumes: `clean`, `Suggested` (Task 5)
- Produces:
  - `Extractor = Callable[[str, dict[str, Any]], dict[str, Any]]` with signature `(target, ydl_opts) -> info`
  - `ytdlp_extract(target, opts) -> dict` (the real extractor; runs yt-dlp)
  - `search(query: str, library_ids: set[str], extract: Extractor = ytdlp_extract) -> dict`. Raises `ValueError` when the query is blank.
    - Return shape: `{"kind": "search" | "url" | "playlist", "playlist_title": str | None, "results": [result]}`
    - `result`: `{"video_id", "title", "channel", "duration", "thumbnail_url", "suggested": {"title", "artist", "album"}, "in_library": bool}`
  - `SEARCH_TIMEOUT = 20.0`
  - `MAX_PLAYLIST = 200`

- [ ] **Step 1: Write the failing tests**

`app/backend/tests/test_search.py`:

```python
import pytest

from wyc_music_streaming.search import MAX_PLAYLIST, search


def fake(info):
    calls = []

    def extract(target, opts):
        calls.append((target, opts))
        return info

    return extract, calls


def test_keyword_search_uses_ytsearch10_flat():
    extract, calls = fake({
        "_type": "playlist", "title": "numb",
        "entries": [
            {"id": "kXYiU_JCYtU", "title": "Linkin Park - Numb (Official Music Video)",
             "channel": "Linkin Park", "duration": 187},
            {"id": "not-a-video-id"},
            None,
        ],
    })
    out = search("  numb  ", {"kXYiU_JCYtU"}, extract)
    [(target, opts)] = calls
    assert target == "ytsearch10:numb"
    assert opts["extract_flat"] == "in_playlist"
    assert out["kind"] == "search"
    assert out["playlist_title"] is None
    [r] = out["results"]
    assert r == {
        "video_id": "kXYiU_JCYtU",
        "title": "Linkin Park - Numb (Official Music Video)",
        "channel": "Linkin Park",
        "duration": 187,
        "thumbnail_url": "https://i.ytimg.com/vi/kXYiU_JCYtU/mqdefault.jpg",
        "suggested": {"title": "Numb", "artist": "Linkin Park", "album": "Singles"},
        "in_library": True,
    }


def test_single_video_url_uses_ytdlp_music_fields():
    extract, calls = fake({
        "id": "4TYv2PhG89A", "title": "Sade - Smooth Operator - Official - 1984",
        "uploader": "Sade", "duration": 258,
        "artist": "Sade", "track": "Smooth Operator", "album": "Diamond Life",
    })
    out = search("https://www.youtube.com/watch?v=4TYv2PhG89A", set(), extract)
    assert calls[0][0] == "https://www.youtube.com/watch?v=4TYv2PhG89A"
    assert out["kind"] == "url"
    [r] = out["results"]
    assert r["channel"] == "Sade"
    assert r["suggested"] == {"title": "Smooth Operator", "artist": "Sade", "album": "Diamond Life"}
    assert r["in_library"] is False


def test_playlist_url_uses_playlist_title_as_album():
    extract, calls = fake({
        "_type": "playlist", "title": "Phonk Mix",
        "entries": [{"id": "aaaaaaaaaaa", "title": "Drift Phonk", "channel": "PhonkGuy"}],
    })
    out = search("https://music.youtube.com/playlist?list=PL1234567890", set(), extract)
    assert calls[0][1]["playlistend"] == MAX_PLAYLIST
    assert out["kind"] == "playlist"
    assert out["playlist_title"] == "Phonk Mix"
    assert out["results"][0]["suggested"]["album"] == "Phonk Mix"


def test_radio_mix_url_is_treated_as_single_video():
    extract, calls = fake({"id": "aaaaaaaaaaa", "title": "x", "channel": "y"})
    search("https://www.youtube.com/watch?v=aaaaaaaaaaa&list=RDaaaaaaaaaaa", set(), extract)
    assert calls[0][1]["noplaylist"] is True


def test_blank_query_raises():
    extract, _ = fake({})
    with pytest.raises(ValueError):
        search("   ", set(), extract)
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest tests/test_search.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'wyc_music_streaming.search'`

- [ ] **Step 3: Implement `search.py`**

```python
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
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `uv run pytest tests/test_search.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add app/backend/wyc_music_streaming/search.py app/backend/tests/test_search.py
git commit -m "feat(backend): add YouTube search and URL lookup"
```

---

### Task 12: Download worker

**Files:**
- Create: `app/backend/wyc_music_streaming/worker.py`
- Test: `app/backend/tests/test_worker.py`

**Interfaces:**
- Consumes: `Config`, `User` (Task 2); `sanitize_name`, `track_filename`, `unique_path` (Task 4); `TagData`, `write_tags`, `read_tags` (Task 6); `AUDIO_EXTS`, `Library` (Task 7); `Job`, `JobStore`, `NewJob` (Task 8); `RefreshScheduler.schedule` (Task 9); `EventBroker` (Task 10)
- Produces:
  - `Downloader = Callable[[Job, Path, ProgressFn], tuple[Path, Path | None]]` with signature `(job, tmp_dir, on_progress) -> (audio_file, thumbnail_jpg_or_None)`. `ProgressFn = Callable[[float], None]`.
  - `ytdlp_download(job, tmp_dir, on_progress)` (the real downloader)
  - `async fetch_cover(url: str) -> bytes | None`
  - `class Worker(*, config, store, library, events, refresher, downloader=ytdlp_download, fetch_cover=fetch_cover)` with:
    - `start() -> list[asyncio.Task]` (starts `config.concurrency` loops)
    - `wake()` (call from the event loop thread)
    - `async process(job: Job)` (`job` must already be claimed)
  - `TMP_DIR_NAME = ".wyc-music-streaming-tmp"`

- [ ] **Step 1: Write the failing tests**

`app/backend/tests/test_worker.py`:

```python
import asyncio
from types import SimpleNamespace

import pytest
from mutagen.mp4 import MP4

from wyc_music_streaming.events import EventBroker
from wyc_music_streaming.jobs import JobStore, NewJob
from wyc_music_streaming.library import Library
from wyc_music_streaming.tags import read_tags
from wyc_music_streaming.worker import Worker


class FakeRefresher:
    def __init__(self):
        self.calls = 0

    def schedule(self):
        self.calls += 1


@pytest.fixture
def env(config, make_audio, tmp_path):
    store = JobStore(tmp_path / "jobs.db")
    library = Library(config.users)
    events = EventBroker()
    refresher = FakeRefresher()

    def good_downloader(job, tmp_dir, on_progress):
        on_progress(0.5)
        audio = make_audio(tmp_dir / f"{job.id}.m4a")
        thumb = tmp_dir / f"{job.id}.jpg"
        thumb.write_bytes(b"THUMB")
        return audio, thumb

    async def no_cover(url):
        raise AssertionError("fetch_cover must not be called without cover_url")

    def make_worker(downloader=good_downloader, fetch_cover=no_cover):
        return Worker(config=config, store=store, library=library, events=events,
                      refresher=refresher, downloader=downloader, fetch_cover=fetch_cover)

    yield SimpleNamespace(config=config, store=store, library=library, events=events,
                          refresher=refresher, make_worker=make_worker,
                          tmp_dir=config.server.data_dir / "tmp",
                          music=config.users["wick"].music_dir)
    store.close()


def drain(queue):
    return [queue.get_nowait() for _ in range(queue.qsize())]


def queue_job(env, user="wick", **kw):
    fields = {"video_id": "kXYiU_JCYtU", "title": "Numb", "artist": "Linkin Park", "album": "Meteora"} | kw
    env.store.add(user, [NewJob(**fields)])
    return env.store.claim_next()


async def test_job_done_moves_tags_and_notifies(env):
    worker = env.make_worker()
    q = env.events.subscribe("wick")
    job = queue_job(env)

    await worker.process(job)

    done = env.store.get(job.id)
    assert done.status == "done"
    assert done.final_path == "Linkin Park/Meteora/Numb.m4a"
    final = env.music / done.final_path
    tags = read_tags(final)
    assert (tags["title"], tags["album_artist"], tags["video_id"]) == ("Numb", "Linkin Park", "kXYiU_JCYtU")
    assert MP4(final)["covr"][0] == b"THUMB"
    assert env.library.has_video("wick", "kXYiU_JCYtU")
    assert env.refresher.calls == 1
    events = drain(q)
    assert [e["type"] for e in events].count("job") >= 2
    assert any(e["type"] == "job" and e["data"]["progress"] == 0.5 for e in events)
    assert events[-1]["type"] == "library"
    assert list(env.tmp_dir.iterdir()) == []


async def test_album_job_uses_track_number_and_cover_url(env):
    fetched = []

    async def fake_fetch(url):
        fetched.append(url)
        return b"COVER"

    worker = env.make_worker(fetch_cover=fake_fetch)
    job = queue_job(env, title="Faint", track_no=7, year="2003", cover_url="https://img.test/c.jpg")

    await worker.process(job)

    done = env.store.get(job.id)
    assert done.final_path == "Linkin Park/Meteora/07 Faint.m4a"
    final = env.music / done.final_path
    assert MP4(final)["covr"][0] == b"COVER"
    assert read_tags(final)["track_no"] == 7
    assert read_tags(final)["year"] == "2003"
    assert fetched == ["https://img.test/c.jpg"]


async def test_cover_fetch_failure_falls_back_to_thumbnail(env):
    async def failing_fetch(url):
        return None

    worker = env.make_worker(fetch_cover=failing_fetch)
    job = queue_job(env, cover_url="https://img.test/c.jpg")
    await worker.process(job)
    assert MP4(env.music / env.store.get(job.id).final_path)["covr"][0] == b"THUMB"


async def test_name_collision_adds_suffix(env, make_audio):
    make_audio(env.music / "Linkin Park" / "Meteora" / "Numb.m4a")
    worker = env.make_worker()
    job = queue_job(env)
    await worker.process(job)
    assert env.store.get(job.id).final_path == "Linkin Park/Meteora/Numb (2).m4a"


async def test_download_error_marks_failed_and_cleans_tmp(env):
    def broken(job, tmp_dir, on_progress):
        (tmp_dir / f"{job.id}.m4a.part").write_bytes(b"partial")
        raise RuntimeError("ERROR: [youtube] kXYiU_JCYtU: Sign in to confirm you're not a bot\nmore lines")

    worker = env.make_worker(downloader=broken)
    job = queue_job(env)

    await worker.process(job)

    failed = env.store.get(job.id)
    assert failed.status == "failed"
    assert failed.error.startswith("[youtube] kXYiU_JCYtU: Sign in to confirm")
    assert "wyc-music-streaming-update-ytdlp" in failed.error
    assert "more lines" not in failed.error
    assert list(env.tmp_dir.iterdir()) == []
    assert env.refresher.calls == 0


async def test_unknown_user_fails_job(env):
    worker = env.make_worker()
    job = queue_job(env, user="ghost")
    await worker.process(job)
    assert env.store.get(job.id).status == "failed"
    assert "no longer in config" in env.store.get(job.id).error


async def test_started_loop_processes_queued_job(env):
    worker = env.make_worker()
    tasks = worker.start()
    try:
        [job] = env.store.add("wick", [NewJob("kXYiU_JCYtU", "Numb", "Linkin Park", "Meteora")])
        worker.wake()
        for _ in range(100):
            if env.store.get(job.id).status == "done":
                break
            await asyncio.sleep(0.05)
        assert env.store.get(job.id).status == "done"
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest tests/test_worker.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'wyc_music_streaming.worker'`

- [ ] **Step 3: Implement `worker.py`**

```python
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
        """Use data_dir/tmp when it is on the same filesystem as music_dir, so os.replace is atomic."""
        shared = self.config.server.data_dir / "tmp"
        shared.mkdir(parents=True, exist_ok=True)
        if shared.stat().st_dev == user.music_dir.stat().st_dev:
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
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `uv run pytest tests/test_worker.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add app/backend/wyc_music_streaming/worker.py app/backend/tests/test_worker.py
git commit -m "feat(backend): add download worker (yt-dlp, tag, atomic move)"
```

---

### Task 13: HTTP API, app factory, and entry point

**Files:**
- Create: `app/backend/wyc_music_streaming/api.py`
- Create: `app/backend/wyc_music_streaming/main.py`
- Create: `app/backend/wyc_music_streaming/__main__.py`
- Test: `app/backend/tests/test_api.py`

**Interfaces:**
- Consumes: everything above
- Produces:
  - `create_app(config, *, downloader=ytdlp_download, extract=ytdlp_extract, jellyfin_transport=None, refresh_delay=30.0, rescan_interval=3600.0, static_dir=DEFAULT_STATIC_DIR, start_workers=True) -> FastAPI`
  - `DEFAULT_STATIC_DIR = app/frontend/build` (Plan 2 builds it; the app mounts it only if `index.html` exists)
  - `app.state`: `config, store, library, events, jellyfin, refresher, worker, extract`
  - Routes (all need a resolved user; else `403 {"detail": {"error": "denied", "login": <header or null>}}`):

| Method | Path | Body / query | Response |
|---|---|---|---|
| GET | `/api/me` | | `{"name", "login", "jellyfin_user"}` |
| GET | `/api/search` | `q` (1–500 chars) | search result (Task 11). `400` blank, `504` timeout, `502` yt-dlp error |
| POST | `/api/jobs` | `{"items": [{video_id, title, artist, album, track_no?, year?, cover_url?}]}` (1–200 items) | `201 {"created": [job], "skipped": [{"video_id", "reason": "in_library" \| "active" \| "duplicate"}]}` |
| GET | `/api/jobs` | | `{"jobs": [job]}` |
| DELETE | `/api/jobs/{id}` | | `204`; `409` if not a queued job of this user |
| POST | `/api/jobs/{id}/retry` | | `200 job`; `409` if not a failed job of this user |
| GET | `/api/library` | | `{"artists": tree}` |
| POST | `/api/library/rescan` | | `{"tracks": int}` |
| DELETE | `/api/library/track` | `{"path": str}` | `204`; `400` unsafe path; `404` missing |
| POST | `/api/jellyfin/refresh` | | `{"ok": bool}` |
| GET | `/api/events` | | `text/event-stream` (`job`, `library` events; `: ping` every 15 s) |

  - Entry point: `python -m wyc_music_streaming` reads `WYC_MUSIC_STREAMING_CONFIG` (default `/etc/wyc-music-streaming/config.toml`). Exit code 2 on a config error.

- [ ] **Step 1: Write the failing tests**

`app/backend/tests/test_api.py`:

```python
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from wyc_music_streaming.auth import HEADER
from wyc_music_streaming.main import create_app

WICK = {HEADER: "wick@example.com"}
SAFEENA = {HEADER: "safeena@example.com"}
NUMB = {"_type": "playlist", "title": "numb", "entries": [
    {"id": "kXYiU_JCYtU", "title": "Linkin Park - Numb (Official Music Video)", "channel": "Linkin Park", "duration": 187},
]}


def wait_for(predicate, timeout=10.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    raise AssertionError("timed out waiting for condition")


@pytest.fixture
def client(config, make_audio):
    def downloader(job, tmp_dir, on_progress):
        if job.video_id == "failfailfai":
            raise RuntimeError("ERROR: Video unavailable")
        return make_audio(tmp_dir / f"{job.id}.m4a"), None

    def extract(target, opts):
        return NUMB

    jf_calls = []

    def jellyfin(request):
        jf_calls.append(request)
        return httpx.Response(204)

    app = create_app(config, downloader=downloader, extract=extract,
                     jellyfin_transport=httpx.MockTransport(jellyfin), refresh_delay=0.01)
    with TestClient(app, headers=WICK) as c:
        c.jf_calls = jf_calls
        yield c


def job_status(client, job_id, status, headers=WICK):
    for job in client.get("/api/jobs", headers=headers).json()["jobs"]:
        if job["id"] == job_id and job["status"] == status:
            return job
    return None


def download_numb(client):
    result = client.get("/api/search", params={"q": "numb"}).json()["results"][0]
    r = client.post("/api/jobs", json={"items": [{"video_id": result["video_id"], **result["suggested"]}]})
    assert r.status_code == 201
    job_id = r.json()["created"][0]["id"]
    return wait_for(lambda: job_status(client, job_id, "done"))["final_path"]


def test_me(client):
    assert client.get("/api/me").json() == {"name": "wick", "login": "wick@example.com", "jellyfin_user": "wick"}


def test_unknown_login_is_denied(client):
    r = client.get("/api/me", headers={HEADER: "stranger@example.com"})
    assert r.status_code == 403
    assert r.json()["detail"] == {"error": "denied", "login": "stranger@example.com"}


def test_missing_header_is_denied(config):
    bare = TestClient(create_app(config, start_workers=False))
    r = bare.get("/api/me")
    assert r.status_code == 403
    assert r.json()["detail"]["login"] is None


def test_search_validation(client):
    assert client.get("/api/search", params={"q": ""}).status_code == 422
    assert client.get("/api/search", params={"q": "   "}).status_code == 400


def test_download_flow(client):
    first = client.get("/api/search", params={"q": "numb"}).json()["results"][0]
    assert first["in_library"] is False

    final_path = download_numb(client)

    assert final_path == "Linkin Park/Singles/Numb.m4a"
    artists = client.get("/api/library").json()["artists"]
    assert artists[0]["artist"] == "Linkin Park"
    assert artists[0]["albums"][0]["tracks"][0]["path"] == final_path
    assert client.get("/api/search", params={"q": "numb"}).json()["results"][0]["in_library"] is True
    wait_for(lambda: client.jf_calls)

    again = client.post("/api/jobs", json={"items": [
        {"video_id": "kXYiU_JCYtU", "title": "Numb", "artist": "Linkin Park", "album": "Singles"},
    ]}).json()
    assert again == {"created": [], "skipped": [{"video_id": "kXYiU_JCYtU", "reason": "in_library"}]}


def test_duplicate_in_same_request(client):
    item = {"video_id": "aaaaaaaaaaa", "title": "A", "artist": "B", "album": "C"}
    body = client.post("/api/jobs", json={"items": [item, item]}).json()
    assert len(body["created"]) == 1
    assert body["skipped"] == [{"video_id": "aaaaaaaaaaa", "reason": "duplicate"}]


def test_rejects_bad_job_item(client):
    r = client.post("/api/jobs", json={"items": [{"video_id": "short", "title": "A", "artist": "B", "album": "C"}]})
    assert r.status_code == 422


def test_failed_job_can_be_retried(client):
    item = {"video_id": "failfailfai", "title": "A", "artist": "B", "album": "C"}
    job_id = client.post("/api/jobs", json={"items": [item]}).json()["created"][0]["id"]
    failed = wait_for(lambda: job_status(client, job_id, "failed"))
    assert failed["error"] == "Video unavailable"
    r = client.post(f"/api/jobs/{job_id}/retry")
    assert r.status_code == 200
    assert r.json()["status"] == "queued"
    wait_for(lambda: job_status(client, job_id, "failed"))
    assert client.post(f"/api/jobs/{job_id + 999}/retry").status_code == 409


def test_cancel_finished_job_conflicts(client):
    download_numb(client)
    job_id = client.get("/api/jobs").json()["jobs"][0]["id"]
    assert client.delete(f"/api/jobs/{job_id}").status_code == 409


def test_delete_track(client):
    final_path = download_numb(client)
    assert client.request("DELETE", "/api/library/track", json={"path": "../x.m4a"}).status_code == 400
    assert client.request("DELETE", "/api/library/track", json={"path": "nope.m4a"}).status_code == 404
    assert client.request("DELETE", "/api/library/track", json={"path": final_path}).status_code == 204
    assert client.get("/api/library").json()["artists"] == []


def test_users_are_isolated(client):
    final_path = download_numb(client)
    assert client.get("/api/library", headers=SAFEENA).json()["artists"] == []
    assert client.get("/api/jobs", headers=SAFEENA).json()["jobs"] == []
    r = client.request("DELETE", "/api/library/track", json={"path": final_path}, headers=SAFEENA)
    assert r.status_code == 404


def test_rescan_and_manual_refresh(client):
    download_numb(client)
    assert client.post("/api/library/rescan").json() == {"tracks": 1}
    assert client.post("/api/jellyfin/refresh").json() == {"ok": True}


def test_spa_fallback(config, tmp_path):
    build = tmp_path / "build"
    build.mkdir()
    (build / "index.html").write_text("<html>app</html>")
    (build / "app.js").write_text("js")
    c = TestClient(create_app(config, static_dir=build, start_workers=False))
    assert c.get("/").text == "<html>app</html>"
    assert c.get("/library").text == "<html>app</html>"
    assert c.get("/app.js").text == "js"
    assert c.get("/api/nope").status_code == 404
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest tests/test_api.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'wyc_music_streaming.main'`

- [ ] **Step 3: Implement `api.py`**

```python
"""HTTP routes under /api. Every route resolves the user from the Tailscale header.

All routes are `async def` on purpose: EventBroker and Worker.wake() are not
thread-safe, so they must run on the event loop. Slow work goes to run_in_threadpool.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from yt_dlp.utils import DownloadError

from .auth import HEADER, resolve_user
from .config import User
from .events import format_sse
from .jobs import NewJob
from .paths import UnsafePath
from .search import SEARCH_TIMEOUT, search

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api")
PING_INTERVAL = 15.0


def current_user(request: Request) -> User:
    user = resolve_user(request.headers, request.app.state.config)
    if user is None:
        raise HTTPException(status_code=403, detail={"error": "denied", "login": request.headers.get(HEADER)})
    return user


UserDep = Annotated[User, Depends(current_user)]


class JobItem(BaseModel):
    video_id: str = Field(pattern=r"^[\w-]{11}$")
    title: str = Field(min_length=1, max_length=300)
    artist: str = Field(min_length=1, max_length=300)
    album: str = Field(min_length=1, max_length=300)
    track_no: int | None = Field(default=None, ge=1, le=999)
    year: str | None = Field(default=None, max_length=10)
    cover_url: str | None = Field(default=None, pattern=r"^https://", max_length=2000)


class JobsRequest(BaseModel):
    items: list[JobItem] = Field(min_length=1, max_length=200)


class TrackRef(BaseModel):
    path: str = Field(min_length=1, max_length=1000)


@router.get("/me")
async def me(user: UserDep) -> dict[str, Any]:
    return {"name": user.name, "login": user.tailscale_login, "jellyfin_user": user.jellyfin_user}


@router.get("/search")
async def search_route(
    request: Request, user: UserDep, q: Annotated[str, Query(min_length=1, max_length=500)]
) -> dict[str, Any]:
    st = request.app.state
    ids = st.library.video_ids(user.name)
    try:
        return await asyncio.wait_for(run_in_threadpool(search, q, ids, st.extract), timeout=SEARCH_TIMEOUT)
    except ValueError:
        raise HTTPException(status_code=400, detail="empty query") from None
    except TimeoutError:
        raise HTTPException(status_code=504, detail="search took too long") from None
    except DownloadError as exc:
        raise HTTPException(status_code=502, detail=str(exc).removeprefix("ERROR: ")[:300]) from None


@router.post("/jobs", status_code=201)
async def create_jobs(request: Request, user: UserDep, body: JobsRequest) -> dict[str, Any]:
    st = request.app.state
    in_library = st.library.video_ids(user.name)
    seen: set[str] = set()
    new: list[NewJob] = []
    skipped: list[dict[str, str]] = []
    for item in body.items:
        if item.video_id in seen:
            skipped.append({"video_id": item.video_id, "reason": "duplicate"})
            continue
        seen.add(item.video_id)
        if item.video_id in in_library:
            skipped.append({"video_id": item.video_id, "reason": "in_library"})
        elif st.store.has_active(user.name, item.video_id):
            skipped.append({"video_id": item.video_id, "reason": "active"})
        else:
            new.append(NewJob(**item.model_dump()))
    created = st.store.add(user.name, new) if new else []
    for job in created:
        st.events.publish(user.name, "job", job.to_dict())
    st.worker.wake()
    return {"created": [j.to_dict() for j in created], "skipped": skipped}


@router.get("/jobs")
async def list_jobs(request: Request, user: UserDep) -> dict[str, Any]:
    return {"jobs": [j.to_dict() for j in request.app.state.store.list_for_user(user.name)]}


@router.delete("/jobs/{job_id}", status_code=204)
async def cancel_job(request: Request, user: UserDep, job_id: int) -> Response:
    st = request.app.state
    if not st.store.cancel(user.name, job_id):
        raise HTTPException(status_code=409, detail="only a queued job can be cancelled")
    st.events.publish(user.name, "job", st.store.get(job_id).to_dict())
    return Response(status_code=204)


@router.post("/jobs/{job_id}/retry")
async def retry_job(request: Request, user: UserDep, job_id: int) -> dict[str, Any]:
    st = request.app.state
    if not st.store.retry(user.name, job_id):
        raise HTTPException(status_code=409, detail="only a failed job can be retried")
    job = st.store.get(job_id).to_dict()
    st.events.publish(user.name, "job", job)
    st.worker.wake()
    return job


@router.get("/library")
async def get_library(request: Request, user: UserDep) -> dict[str, Any]:
    return {"artists": request.app.state.library.tree(user.name)}


@router.post("/library/rescan")
async def rescan_library(request: Request, user: UserDep) -> dict[str, int]:
    st = request.app.state
    count = await run_in_threadpool(st.library.rescan, user.name)
    st.events.publish(user.name, "library", {"rescan": True})
    return {"tracks": count}


@router.delete("/library/track", status_code=204)
async def delete_track(request: Request, user: UserDep, body: TrackRef) -> Response:
    st = request.app.state
    try:
        await run_in_threadpool(st.library.delete, user.name, body.path)
    except UnsafePath:
        log.warning("path traversal attempt by %s: %r", user.name, body.path)
        raise HTTPException(status_code=400, detail="invalid path") from None
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="track not found") from None
    st.refresher.schedule()
    st.events.publish(user.name, "library", {"deleted": [body.path]})
    return Response(status_code=204)


@router.post("/jellyfin/refresh")
async def refresh_jellyfin(request: Request, user: UserDep) -> dict[str, bool]:
    return {"ok": await request.app.state.refresher.refresh_now()}


@router.get("/events")
async def events_stream(request: Request, user: UserDep) -> StreamingResponse:
    broker = request.app.state.events
    queue = broker.subscribe(user.name)

    async def stream():
        try:
            yield ": connected\n\n"
            while not await request.is_disconnected():
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=PING_INTERVAL)
                except TimeoutError:
                    yield ": ping\n\n"
                    continue
                yield format_sse(event)
        finally:
            broker.unsubscribe(user.name, queue)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

- [ ] **Step 4: Implement `main.py`**

```python
"""FastAPI app factory: wires config, stores, worker and routes together."""
from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from .api import router
from .config import Config, User
from .events import EventBroker
from .jellyfin import JellyfinClient, RefreshScheduler
from .jobs import JobStore
from .library import Library
from .search import Extractor, ytdlp_extract
from .worker import Downloader, Worker, ytdlp_download

log = logging.getLogger(__name__)
DEFAULT_STATIC_DIR = Path(__file__).resolve().parents[2] / "frontend" / "build"


class SPAStaticFiles(StaticFiles):
    """Serve the SvelteKit build; unknown non-API paths get index.html (client-side routing)."""

    async def get_response(self, path: str, scope: Scope):
        if path == "api" or path.startswith("api/"):
            raise StarletteHTTPException(status_code=404)
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404:
                raise
            return await super().get_response("index.html", scope)


async def _rescan_forever(library: Library, events: EventBroker, users: dict[str, User], interval: float) -> None:
    while True:
        await asyncio.sleep(interval)
        for name in users:
            try:
                await run_in_threadpool(library.rescan, name)
            except Exception:
                log.exception("hourly rescan failed for %s", name)
                continue
            events.publish(name, "library", {"rescan": True})


def create_app(
    config: Config,
    *,
    downloader: Downloader = ytdlp_download,
    extract: Extractor = ytdlp_extract,
    jellyfin_transport: httpx.AsyncBaseTransport | None = None,
    refresh_delay: float = 30.0,
    rescan_interval: float = 3600.0,
    static_dir: Path | None = DEFAULT_STATIC_DIR,
    start_workers: bool = True,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if config.server.dev:
            log.warning("DEV MODE: requests without Tailscale-User-Login act as user %r. "
                        "Never use dev mode on the NAS.", config.server.dev_user)
        config.server.data_dir.mkdir(parents=True, exist_ok=True)
        store = JobStore(config.server.data_dir / "app.db")
        recovered = store.recover()
        if recovered:
            log.info("re-queued %d interrupted job(s)", recovered)
        library = Library(config.users)
        await run_in_threadpool(library.rescan_all)
        events = EventBroker()
        jellyfin = JellyfinClient(config.jellyfin.url, config.jellyfin.api_key, transport=jellyfin_transport)
        refresher = RefreshScheduler(jellyfin, delay=refresh_delay)
        worker = Worker(config=config, store=store, library=library, events=events,
                        refresher=refresher, downloader=downloader)

        app.state.store = store
        app.state.library = library
        app.state.events = events
        app.state.jellyfin = jellyfin
        app.state.refresher = refresher
        app.state.worker = worker
        app.state.extract = extract

        tasks = worker.start() if start_workers else []
        tasks.append(asyncio.create_task(_rescan_forever(library, events, config.users, rescan_interval)))
        try:
            yield
        finally:
            for task in tasks:
                task.cancel()
            for task in tasks:
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            await refresher.aclose()
            await jellyfin.aclose()
            store.close()

    app = FastAPI(title="WYC-music-streaming", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.config = config
    app.include_router(router)
    if static_dir is not None and (static_dir / "index.html").is_file():
        app.mount("/", SPAStaticFiles(directory=static_dir, html=True), name="static")
    return app
```

- [ ] **Step 5: Implement `__main__.py`**

```python
"""Entry point: python -m wyc_music_streaming"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import uvicorn

from .config import ConfigError, load_config
from .main import create_app

CONFIG_ENV = "WYC_MUSIC_STREAMING_CONFIG"
DEFAULT_CONFIG = "/etc/wyc-music-streaming/config.toml"


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    path = Path(os.environ.get(CONFIG_ENV, DEFAULT_CONFIG))
    try:
        config = load_config(path)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        sys.exit(2)
    # host comes from the validated config, so the loopback check in config.py really applies.
    uvicorn.run(create_app(config), host=config.server.host, port=config.server.port,
                proxy_headers=False, log_level="info")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run the API tests to see them pass**

Run: `uv run pytest tests/test_api.py -v`
Expected: 13 passed

- [ ] **Step 7: Run the whole suite**

Run: `uv run pytest -q`
Expected: all tests pass, 0 failed

- [ ] **Step 8: Manual dev run with real yt-dlp (needs internet and Deno on the dev machine)**

Create a dev config at `/tmp/wyc-dev/config.toml` and start the server:

```bash
mkdir -p /tmp/wyc-dev/music && echo dev-key > /tmp/wyc-dev/jellyfin.key
cat > /tmp/wyc-dev/config.toml <<'EOF'
[server]
data_dir = "/tmp/wyc-dev/data"
dev = true
dev_user = "me"

[jellyfin]
url = "http://127.0.0.1:8096"
api_key_file = "/tmp/wyc-dev/jellyfin.key"

[users.me]
tailscale_login = "me@example.com"
music_dir = "/tmp/wyc-dev/music"
EOF
WYC_MUSIC_STREAMING_CONFIG=/tmp/wyc-dev/config.toml uv run python -m wyc_music_streaming
```

In a second terminal:

```bash
curl -s 'http://127.0.0.1:8097/api/search?q=linkin%20park%20numb' | head -c 600
curl -s -X POST http://127.0.0.1:8097/api/jobs -H 'content-type: application/json' \
  -d '{"items":[{"video_id":"kXYiU_JCYtU","title":"Numb","artist":"Linkin Park","album":"Singles"}]}'
sleep 20; curl -s http://127.0.0.1:8097/api/jobs; find /tmp/wyc-dev/music -type f
```

Expected:
- The log shows a `DEV MODE` warning.
- The search returns 10 results.
- The job reaches `done`.
- `/tmp/wyc-dev/music/Linkin Park/Singles/Numb.m4a` exists.
- A `Jellyfin library refresh failed` warning is fine when no local Jellyfin runs.

Stop the server with Ctrl+C.

- [ ] **Step 9: Commit**

```bash
git add app/backend/wyc_music_streaming/api.py app/backend/wyc_music_streaming/main.py \
        app/backend/wyc_music_streaming/__main__.py app/backend/tests/test_api.py
git commit -m "feat(backend): add HTTP API, app factory and entry point"
```

---

### Task 14: Deployment files, docs, and spec sync

**Files:**
- Create: `app/deploy/wyc-music-streaming.service`
- Create: `app/deploy/wyc-music-streaming-update-ytdlp.service`
- Create: `app/deploy/wyc-music-streaming-update-ytdlp.timer`
- Create: `app/deploy/config.example.toml`
- Create: `app/deploy/update.sh`
- Create: `app/README.md`
- Modify: `README.md` (add a short "Music downloader app" link section at the end)
- Modify: `docs/superpowers/specs/2026-11-05-wyc-music-streaming-design.md` §9 (deployment)

**Interfaces:**
- Consumes: `python -m wyc_music_streaming` (Task 13)
- Produces: a repeatable deploy. Run `sudo /opt/wyc-music-streaming/repo/app/deploy/update.sh`.

Deployment decisions in this task (they refine spec §9):
- `/opt/wyc-music-streaming` is owned by `wick`. The repo, venv, and frontend build are built as `wick`, so `git pull` and `npm` never need root.
- `UV_PYTHON_INSTALL_DIR=/opt/wyc-music-streaming/python`. The uv-managed Python must sit outside `/root` and `~wick`, or the service user cannot run the venv.
- `ExecStart` runs `python -m wyc_music_streaming`. Then the host and port come from the validated config, not from a second copy on the command line.

- [ ] **Step 1: Write the systemd units**

`app/deploy/wyc-music-streaming.service`:

```ini
[Unit]
Description=WYC-music-streaming (music download web app)
After=network-online.target jellyfin.service
Wants=network-online.target

[Service]
Type=simple
User=wyc-music-streaming
Group=wick
UMask=0002
WorkingDirectory=/opt/wyc-music-streaming/repo/app/backend
Environment=WYC_MUSIC_STREAMING_CONFIG=/etc/wyc-music-streaming/config.toml
Environment=HOME=/var/lib/wyc-music-streaming
Environment=PATH=/usr/local/bin:/usr/bin:/bin
ExecStart=/opt/wyc-music-streaming/repo/app/backend/.venv/bin/python -m wyc_music_streaming
Restart=on-failure
RestartSec=5
# exit code 2 = config error: do not restart in a loop
RestartPreventExitStatus=2
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=/var/lib/wyc-music-streaming /home/wick/share

[Install]
WantedBy=multi-user.target
```

`app/deploy/wyc-music-streaming-update-ytdlp.service`:

```ini
[Unit]
Description=Update yt-dlp for WYC-music-streaming
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=wick
Environment=PATH=/usr/local/bin:/usr/bin:/bin
ExecStart=/usr/local/bin/uv pip install --python /opt/wyc-music-streaming/repo/app/backend/.venv/bin/python -U "yt-dlp[default]"
# "+" runs this line as root, so it can restart the app service.
ExecStartPost=+/bin/systemctl restart wyc-music-streaming.service
```

`app/deploy/wyc-music-streaming-update-ytdlp.timer`:

```ini
[Unit]
Description=Weekly yt-dlp update for WYC-music-streaming

[Timer]
OnCalendar=weekly
RandomizedDelaySec=1h
Persistent=true

[Install]
WantedBy=timers.target
```

- [ ] **Step 2: Write the config example**

`app/deploy/config.example.toml`:

```toml
# Copy to /etc/wyc-music-streaming/config.toml (NOT into git; this repo is public).
#   sudo install -m 640 -o root -g wyc-music-streaming config.example.toml /etc/wyc-music-streaming/config.toml

[server]
host = "127.0.0.1"          # must stay loopback; tailscale serve is the only way in
port = 8097
data_dir = "/var/lib/wyc-music-streaming"
dev = false
# dev_user = "wick"         # dev machine only: user for requests without the Tailscale header

[jellyfin]
url = "http://127.0.0.1:8096"
api_key_file = "/etc/wyc-music-streaming/jellyfin.key"   # chmod 640 root:wyc-music-streaming

[download]
concurrency = 2

[users.wick]
tailscale_login = "wick@gmail.com"
music_dir = "/home/wick/share/wick/music"
jellyfin_user = "wick"

[users.safeena]
tailscale_login = "safeena@gmail.com"
music_dir = "/home/wick/share/safeena/music"
jellyfin_user = "safeena"
```

- [ ] **Step 3: Write `update.sh`**

`app/deploy/update.sh`:

```bash
#!/usr/bin/env bash
# Deploy or update WYC-music-streaming on the NAS. Safe to run again.
# Usage: sudo /opt/wyc-music-streaming/repo/app/deploy/update.sh
set -euo pipefail

BASE=/opt/wyc-music-streaming
REPO=$BASE/repo
APP=$REPO/app
SVC=wyc-music-streaming

if [[ $EUID -ne 0 ]]; then
  echo "Run with sudo." >&2
  exit 1
fi
OWNER=$(stat -c %U "$REPO")

as_owner() {
  sudo -u "$OWNER" -H env UV_PYTHON_INSTALL_DIR="$BASE/python" bash -lc "$1"
}

echo "== git pull"
as_owner "git -C '$REPO' pull --ff-only"

echo "== backend"
as_owner "cd '$APP/backend' && uv sync --frozen --no-dev --python 3.12 \
  && uv pip install --python .venv/bin/python -U 'yt-dlp[default]'"

if [[ -f $APP/frontend/package.json ]]; then
  echo "== frontend"
  as_owner "source ~/.nvm/nvm.sh && cd '$APP/frontend' && npm ci && npm run build"
fi

echo "== deno"
deno upgrade || echo "warning: deno upgrade failed; continuing" >&2

echo "== systemd"
install -m 644 "$APP/deploy/$SVC.service" \
               "$APP/deploy/$SVC-update-ytdlp.service" \
               "$APP/deploy/$SVC-update-ytdlp.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now "$SVC-update-ytdlp.timer"
systemctl enable "$SVC"
systemctl restart "$SVC"
sleep 2
systemctl --no-pager --lines=10 status "$SVC"
```

Run (repo root): `bash -n app/deploy/update.sh && chmod +x app/deploy/update.sh && echo syntax-ok`
Expected: `syntax-ok`

- [ ] **Step 4: Write `app/README.md` and link it from the root README**

`app/README.md`:

````markdown
# WYC-music-streaming app

Web app on the NAS. It downloads music from YouTube into each user's music
folder and refreshes Jellyfin. Design: `docs/superpowers/specs/2026-11-05-wyc-music-streaming-design.md`.

## Dev machine

```
cd app/backend
uv sync --python 3.12
uv run pytest -q
```

Run locally with a dev config (`[server] dev = true`, `dev_user = "<name>"`):

```
WYC_MUSIC_STREAMING_CONFIG=/path/to/dev-config.toml uv run python -m wyc_music_streaming
```

Never use dev mode on the NAS.

## NAS: one-time setup

1. Preflight: `bash app/deploy/check-nas.sh` (from a clone, or after step 4).
2. Packages and tools (system-wide, so the service user can run them):

   ```
   sudo apt install ffmpeg unzip
   curl -LsSf https://astral.sh/uv/install.sh | sudo env UV_INSTALL_DIR=/usr/local/bin sh
   curl -fsSL https://deno.land/install.sh | sudo env DENO_INSTALL=/usr/local sh -s -- -y --no-modify-path
   deno --version
   ```

3. Service user and folders:

   ```
   sudo useradd --system --gid wick --home-dir /var/lib/wyc-music-streaming --create-home wyc-music-streaming
   sudo mkdir -p /opt/wyc-music-streaming /etc/wyc-music-streaming
   sudo chown wick: /opt/wyc-music-streaming
   ```

4. Code:

   ```
   git clone https://github.com/Worawit-cs/WYC-music-streaming.git /opt/wyc-music-streaming/repo
   ```

5. Config and Jellyfin key (Jellyfin Dashboard → API Keys → +):

   ```
   sudo install -m 640 -o root -g wyc-music-streaming \
     /opt/wyc-music-streaming/repo/app/deploy/config.example.toml /etc/wyc-music-streaming/config.toml
   sudo nano /etc/wyc-music-streaming/config.toml      # set real tailscale_login values
   echo 'PASTE-KEY-HERE' | sudo tee /etc/wyc-music-streaming/jellyfin.key >/dev/null
   sudo chown root:wyc-music-streaming /etc/wyc-music-streaming/jellyfin.key
   sudo chmod 640 /etc/wyc-music-streaming/jellyfin.key
   ```

6. Deploy: `sudo /opt/wyc-music-streaming/repo/app/deploy/update.sh`
7. Tailscale (admin console: enable MagicDNS and HTTPS certificates first):

   ```
   sudo tailscale serve --bg --https=443 http://127.0.0.1:8097
   ```

Do not open port 8097 in UFW.

## Update

```
sudo /opt/wyc-music-streaming/repo/app/deploy/update.sh
```

yt-dlp also updates itself weekly (`wyc-music-streaming-update-ytdlp.timer`).
To update it now: `sudo systemctl start wyc-music-streaming-update-ytdlp`.

## Logs

```
journalctl -u wyc-music-streaming -f
```
````

Append to the root `README.md`:

```markdown

---

## 🎵 Music downloader app

A web app on the NAS downloads music from YouTube straight into each user's
Jellyfin library. Setup and deploy: [app/README.md](app/README.md).
```

- [ ] **Step 5: Sync spec §9 with the deploy decisions**

In `docs/superpowers/specs/2026-11-05-wyc-music-streaming-design.md` §9, make these exact changes:

1. Replace the `git clone …` code block with:

   ```
   sudo mkdir -p /opt/wyc-music-streaming && sudo chown wick: /opt/wyc-music-streaming
   git clone https://github.com/Worawit-cs/WYC-music-streaming.git /opt/wyc-music-streaming/repo
   sudo /opt/wyc-music-streaming/repo/app/deploy/update.sh
   ```

2. In the `update.sh` list, change step 2 to: "As the repo owner (`wick`), with `UV_PYTHON_INSTALL_DIR=/opt/wyc-music-streaming/python`: `uv sync --frozen --no-dev --python 3.12`, then `uv pip install -U "yt-dlp[default]"`. The uv Python must live outside home dirs so the service user can run it."
3. In the `.service` block, replace the `ExecStart=` line with:
   `ExecStart=/opt/wyc-music-streaming/repo/app/backend/.venv/bin/python -m wyc_music_streaming`
   Then add a note under the block: "The app reads host and port from the validated config. The loopback check in config.py therefore covers the real listen address."
4. Under the update timer, add: "Runs as `wick`. The restart line runs as root through systemd's `+` prefix."

- [ ] **Step 6: Commit**

```bash
git add app/deploy app/README.md README.md docs/superpowers/specs/2026-11-05-wyc-music-streaming-design.md
git commit -m "feat(deploy): add systemd units, update script, config example and setup docs"
```

---

### Task 15: First deploy and smoke test on the NAS (manual)

Run this with the user, on the NAS. Only the results get committed.

- [ ] **Step 1: Merge to `main`** (after review, per superpowers:finishing-a-development-branch), then push.

- [ ] **Step 2: Follow `app/README.md` → "NAS: one-time setup" steps 1–7.**

Expected: `check-nas.sh` shows no `FAIL`, and `systemctl status wyc-music-streaming` shows `active (running)`.

- [ ] **Step 3: Smoke-test from another device in the tailnet**

```bash
curl -s https://<nas>.<tailnet>.ts.net/api/me
curl -s 'https://<nas>.<tailnet>.ts.net/api/search?q=linkin%20park%20numb' | head -c 400
curl -s -X POST https://<nas>.<tailnet>.ts.net/api/jobs -H 'content-type: application/json' \
  -d '{"items":[{"video_id":"kXYiU_JCYtU","title":"Numb","artist":"Linkin Park","album":"Singles"}]}'
```

Expected:
1. `/api/me` returns your user. A tailnet login that is not in config gets `403`.
2. The search returns results.
3. Within about 1 minute, `/home/wick/share/wick/music/Linkin Park/Singles/Numb.m4a` exists. The file is mode `664`, group `wick`.
4. Within about 30 seconds after that, the track appears in the Jellyfin app.
5. On the NAS LAN, `curl http://<lan-ip>:8097` fails with connection refused.

- [ ] **Step 4: Record results**

Add the results to spec §11 (mark `tailscale serve` + UFW verified or not), then commit:

```bash
git add docs/superpowers/specs/2026-11-05-wyc-music-streaming-design.md
git commit -m "docs(spec): record NAS smoke test results"
```
