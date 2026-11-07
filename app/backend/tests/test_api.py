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
    def downloader(job, tmp_dir, on_progress, on_stage):
        if job.video_id == "failfailfai":
            raise RuntimeError("ERROR: Video unavailable")
        return make_audio(tmp_dir / f"{job.id}.m4a"), None

    def extract(target, opts):
        return NUMB

    jf_calls = []

    def jellyfin(request):
        jf_calls.append(request)
        return httpx.Response(204)

    def suggest(request):
        return httpx.Response(200, json=[request.url.params["q"], ["numb", "numb lyrics"]])

    app = create_app(config, downloader=downloader, extract=extract,
                     jellyfin_transport=httpx.MockTransport(jellyfin),
                     suggest_transport=httpx.MockTransport(suggest), refresh_delay=0.01)
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
    assert client.get("/api/search", params={"q": "numb", "page": 0}).status_code == 422
    assert client.get("/api/search", params={"q": "numb", "page": 6}).status_code == 422


def test_suggest_returns_list(client):
    r = client.get("/api/suggest", params={"q": "num"})
    assert r.status_code == 200
    assert r.json() == {"suggestions": ["numb", "numb lyrics"]}


def test_suggest_validation(client):
    assert client.get("/api/suggest", params={"q": ""}).status_code == 422
    assert client.get("/api/suggest", params={"q": "x" * 101}).status_code == 422


def test_suggest_needs_identity(client):
    assert client.get("/api/suggest", params={"q": "num"}, headers={HEADER: "stranger@example.com"}).status_code == 403


def test_search_returns_page_fields(client):
    out = client.get("/api/search", params={"q": "numb", "page": 2}).json()
    assert out["page"] == 2
    assert out["has_more"] is False


def test_download_flow(client):
    first = client.get("/api/search", params={"q": "numb"}).json()["results"][0]
    assert first["in_library"] is False

    final_path = download_numb(client)

    assert final_path == "Linkin_Park/Singles/Numb.m4a"
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


def test_rename_album_and_artist(client):
    download_numb(client)
    r = client.post("/api/library/rename", json={
        "kind": "album", "artist": "Linkin Park", "album": "Singles", "new_name": "Meteora"})
    assert r.status_code == 200
    assert r.json() == {"moved": 1, "merged": False}
    r = client.post("/api/library/rename", json={"kind": "artist", "artist": "Linkin Park", "new_name": "LP"})
    assert r.json() == {"moved": 1, "merged": False}
    [artist] = client.get("/api/library").json()["artists"]
    assert artist["artist"] == "LP"
    assert artist["albums"][0]["album"] == "Meteora"
    assert artist["albums"][0]["tracks"][0]["path"] == "LP/Meteora/Numb.m4a"
    wait_for(lambda: client.jf_calls)


def test_rename_errors(client):
    def post(body):
        return client.post("/api/library/rename", json=body)

    assert post({"kind": "artist", "artist": "Nobody", "new_name": "X"}).status_code == 404
    download_numb(client)
    assert post({"kind": "artist", "artist": "Linkin Park", "new_name": "Linkin Park"}).status_code == 400
    assert post({"kind": "album", "artist": "Linkin Park", "new_name": "X"}).status_code == 400
    assert post({"kind": "song", "artist": "Linkin Park", "new_name": "X"}).status_code == 422
    assert post({"kind": "artist", "artist": "Linkin Park", "new_name": ""}).status_code == 422
    assert post({"kind": "artist", "artist": "Linkin Park", "new_name": "x" * 301}).status_code == 422


def test_rename_blocked_while_a_job_is_active(config, make_audio):
    def downloader(job, tmp_dir, on_progress, on_stage):
        return make_audio(tmp_dir / f"{job.id}.m4a"), None

    app = create_app(config, downloader=downloader, extract=lambda t, o: NUMB,
                     jellyfin_transport=httpx.MockTransport(lambda r: httpx.Response(204)),
                     suggest_transport=httpx.MockTransport(lambda r: httpx.Response(200, json=["", []])),
                     start_workers=False)
    with TestClient(app, headers=WICK) as c:
        make_audio(config.users["wick"].music_dir / "Linkin_Park" / "Singles" / "Old.m4a")
        c.post("/api/library/rescan")
        c.post("/api/jobs", json={"items": [
            {"video_id": "kXYiU_JCYtU", "title": "Numb", "artist": "Linkin_Park", "album": "Singles"}]})
        r = c.post("/api/library/rename", json={"kind": "artist", "artist": "Linkin_Park", "new_name": "LP"})
        assert r.status_code == 409
        assert "รอคิวหมดก่อน" in r.json()["detail"]
