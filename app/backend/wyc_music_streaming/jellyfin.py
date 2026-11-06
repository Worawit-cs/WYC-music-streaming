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
