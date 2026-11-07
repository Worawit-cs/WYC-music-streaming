import asyncio
from types import SimpleNamespace

import pytest
from mutagen.mp4 import MP4

from wyc_music_streaming.events import EventBroker
from wyc_music_streaming.jobs import JobStore, NewJob
from wyc_music_streaming.library import Library
from wyc_music_streaming.tags import read_tags
from wyc_music_streaming.worker import Worker, progress_hook


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

    def good_downloader(job, tmp_dir, on_progress, on_stage):
        on_stage("downloading")
        on_progress(0.5)
        on_progress(0.7)  # inside the throttle window: dropped
        on_progress(1.0)  # the last update always goes out
        on_stage("processing")
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


def test_tmp_dir_is_shared_when_rename_works(env):
    worker = env.make_worker()
    assert worker._tmp_dirs["wick"] == env.tmp_dir
    assert not any(p.name.startswith(".wyc-rename-probe") for p in env.music.iterdir())
    assert list(env.tmp_dir.iterdir()) == []


async def test_tmp_dir_falls_back_when_rename_crosses_mounts(env, monkeypatch):
    # systemd ReadWritePaths= bind-mounts data_dir and music_dir separately: both report
    # the same st_dev, but rename() between them fails with EXDEV (seen on the NAS).
    import errno
    import os
    from pathlib import Path

    real_replace = os.replace

    def replace(src, dst):
        if Path(src).parent == env.tmp_dir:
            raise OSError(errno.EXDEV, "Invalid cross-device link")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", replace)
    worker = env.make_worker()
    own = env.music / ".wyc-music-streaming-tmp"
    assert worker._tmp_dirs["wick"] == own
    assert list(env.tmp_dir.iterdir()) == []

    job = queue_job(env)
    await worker.process(job)
    assert env.store.get(job.id).status == "done"
    assert (env.music / "Linkin_Park/Meteora/Numb.m4a").exists()
    assert list(own.iterdir()) == []


async def test_job_done_moves_tags_and_notifies(env):
    worker = env.make_worker()
    q = env.events.subscribe("wick")
    job = queue_job(env)

    await worker.process(job)

    done = env.store.get(job.id)
    assert done.status == "done"
    assert done.final_path == "Linkin_Park/Meteora/Numb.m4a"
    final = env.music / done.final_path
    tags = read_tags(final)
    assert (tags["title"], tags["album_artist"], tags["video_id"]) == ("Numb", "Linkin Park", "kXYiU_JCYtU")
    assert MP4(final)["covr"][0] == b"THUMB"
    assert env.library.has_video("wick", "kXYiU_JCYtU")
    assert env.refresher.calls == 1
    events = drain(q)
    assert [e["type"] for e in events].count("job") >= 2
    progress = [e["data"]["progress"] for e in events if e["type"] == "job" and e["data"]["status"] == "downloading"]
    assert 0.5 in progress and 1.0 in progress and 0.7 not in progress
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
    assert done.final_path == "Linkin_Park/Meteora/07_Faint.m4a"
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
    make_audio(env.music / "Linkin_Park" / "Meteora" / "Numb.m4a")
    worker = env.make_worker()
    job = queue_job(env)
    await worker.process(job)
    assert env.store.get(job.id).final_path == "Linkin_Park/Meteora/Numb_(2).m4a"


async def test_download_error_marks_failed_and_cleans_tmp(env):
    def broken(job, tmp_dir, on_progress, on_stage):
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


async def test_stages_go_finding_downloading_processing(env):
    worker = env.make_worker()
    q = env.events.subscribe("wick")
    job = queue_job(env)
    assert job.stage == "finding"

    await worker.process(job)

    stages = [e["data"]["stage"] for e in drain(q) if e["type"] == "job" and e["data"]["status"] == "downloading"]
    order = [s for i, s in enumerate(stages) if i == 0 or stages[i - 1] != s]
    assert order == ["finding", "downloading", "processing"]


async def test_processing_stage_is_set_even_if_the_downloader_never_says_so(env, make_audio):
    def quiet(job, tmp_dir, on_progress, on_stage):
        return make_audio(tmp_dir / f"{job.id}.m4a"), None

    worker = env.make_worker(downloader=quiet)
    q = env.events.subscribe("wick")
    job = queue_job(env)
    await worker.process(job)
    stages = [e["data"]["stage"] for e in drain(q) if e["type"] == "job" and e["data"]["status"] == "downloading"]
    assert stages[-1] == "processing"


def test_progress_hook_maps_ytdlp_events():
    calls = []
    hook = progress_hook(lambda f: calls.append(("progress", f)), lambda s: calls.append(("stage", s)))
    hook({"status": "downloading", "downloaded_bytes": 0, "total_bytes": None})
    hook({"status": "downloading", "downloaded_bytes": 50, "total_bytes": 200})
    hook({"status": "downloading", "downloaded_bytes": 100, "total_bytes_estimate": 200})
    hook({"status": "finished", "downloaded_bytes": 200, "total_bytes": 200})
    assert calls == [
        ("stage", "downloading"),
        ("stage", "downloading"),
        ("progress", 0.25),
        ("stage", "downloading"),
        ("progress", 0.5),
        ("progress", 1.0),
        ("stage", "processing"),
    ]
