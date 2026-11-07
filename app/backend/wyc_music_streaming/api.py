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
from .search import MAX_PAGES, SEARCH_TIMEOUT, search
from .suggest import fetch_suggestions

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
    request: Request,
    user: UserDep,
    q: Annotated[str, Query(min_length=1, max_length=500)],
    page: Annotated[int, Query(ge=1, le=MAX_PAGES)] = 1,
) -> dict[str, Any]:
    st = request.app.state
    ids = st.library.video_ids(user.name)
    try:
        return await asyncio.wait_for(
            run_in_threadpool(search, q, ids, st.extract, page=page), timeout=SEARCH_TIMEOUT
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="empty query") from None
    except TimeoutError:
        raise HTTPException(status_code=504, detail="search took too long") from None
    except DownloadError as exc:
        raise HTTPException(status_code=502, detail=str(exc).removeprefix("ERROR: ")[:300]) from None


@router.get("/suggest")
async def suggest_route(
    request: Request, user: UserDep, q: Annotated[str, Query(min_length=1, max_length=100)]
) -> dict[str, list[str]]:
    return {"suggestions": await fetch_suggestions(request.app.state.suggest_http, q)}


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
