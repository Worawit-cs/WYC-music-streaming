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
