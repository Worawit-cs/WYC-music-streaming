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
