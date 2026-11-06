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
