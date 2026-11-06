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
