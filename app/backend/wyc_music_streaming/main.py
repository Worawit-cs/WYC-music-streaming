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
from .suggest import SUGGEST_TIMEOUT
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
    suggest_transport: httpx.AsyncBaseTransport | None = None,
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
        suggest_http = httpx.AsyncClient(timeout=SUGGEST_TIMEOUT, transport=suggest_transport)
        worker = Worker(config=config, store=store, library=library, events=events,
                        refresher=refresher, downloader=downloader)

        app.state.store = store
        app.state.library = library
        app.state.events = events
        app.state.jellyfin = jellyfin
        app.state.refresher = refresher
        app.state.worker = worker
        app.state.extract = extract
        app.state.suggest_http = suggest_http

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
            await suggest_http.aclose()
            store.close()

    app = FastAPI(title="WYC-music-streaming", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.config = config
    app.include_router(router)
    if static_dir is not None and (static_dir / "index.html").is_file():
        app.mount("/", SPAStaticFiles(directory=static_dir, html=True), name="static")
    return app
