# Rename and Download Feedback Implementation Plan (plan 2.6)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename or merge albums and artists from the library, show a dialog with the finished tracks when the queue empties, and make the cassette deck show real progress with stages.

**Architecture:** Backend: a `stage` column on jobs (added on startup for old databases), a yt-dlp progress hook that reports `downloading` and, on `finished`, 100 % plus `processing`; the worker's 1 s throttle never drops 100 % or a stage change. A new `rename.py` retags files with mutagen's easy interface, moves them with `unique_path`, removes empty folders and rescans; `POST /api/library/rename` guards it with a 409 while a matching job is active. Frontend: `stageText` and a striped bar in the deck, a `finished` list in the jobs state with a `<dialog>` in the layout, and a `RenameForm` (built on `Combobox`) in album cards and artist headings.

**Tech Stack:** FastAPI + yt-dlp + mutagen + SQLite (pytest, pytest-asyncio auto mode, real ffmpeg audio fixtures); SvelteKit 2 + Svelte 5 runes + Tailwind 4 (Vitest + Testing Library + jsdom). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-11-07-rename-and-download-feedback-design.md` (addendum to `docs/superpowers/specs/2026-11-05-wyc-music-streaming-design.md`; base spec §11 item 11 has the progress root cause).

## Global Constraints

- Stages: `finding` (set when a job is claimed), `downloading`, `processing`. `retry` and `recover` clear the stage.
- Progress: `PROGRESS_INTERVAL = 1.0` throttles fractions below 1.0 only. 1.0 and stage changes always go out.
- Rename: `POST /api/library/rename` `{kind: "album"|"artist", artist, album?, new_name}` → `{moved, merged}`; 400 blank/same name or missing album, 404 no match, 409 active job, 422 bad body, 500 partial (message says how many moved). Names go through `sanitize_name`; paths through `safe_resolve`.
- Rename of an artist sets `albumartist`; it sets `artist` only when that tag was empty or equal to the old name.
- Every `/api` route needs the Tailscale identity. Tests never reach YouTube.
- UI text is Thai. Code, comments, commits and docs are English.
- `npm run check` runs `svelte-check --fail-on-warnings`: zero errors and zero warnings.
- The repo is public: never commit `config.toml`, keys, or real Tailscale logins.

## Execution notes

- Backend commands run in `app/backend/` (`uv run pytest -q`). Frontend commands run in `app/frontend/` with Node from nvm (`source ~/.nvm/nvm.sh`).
- Every code block below was built and tested together before this plan was written:
  backend 157 tests pass; frontend 126 tests pass, `svelte-check` 0 errors 0 warnings, build OK.
- Checked in a browser against the dev backend with real downloads: the deck went
  "กำลังหาไฟล์…" (about 3.7 s) → "กำลังโหลด" → "กำลังแปลงไฟล์…" → idle, and the dialog opened with
  done and failed tracks; an album rename and an artist merge (with the merge notice) worked from the library page.
- That browser check found one bug, fixed in Task 2 below: a postprocessor hook marked "processing" before the
  download, because the thumbnail converter runs `before_dl`. Only the progress hook's `finished` is used.
- Diffs are against commit `0ce68f7` plus the earlier tasks of this plan, in order.

## File structure

```
app/backend/wyc_music_streaming/
  jobs.py      stage column (+ ALTER TABLE for old databases), set_stage, has_active_for
  worker.py    progress_hook(on_progress, on_stage), Downloader takes on_stage, throttle keeps 100 %
  tags.py      retag(path, *, artist, album, album_artist) via mutagen easy interface
  paths.py     remove_empty_parents(root, start) (shared by delete and rename)
  library.py   delete uses remove_empty_parents
  rename.py    NEW  rename(library, user, kind, artist, new_name, album) -> RenameResult; PartialRename
  api.py       POST /api/library/rename
app/frontend/src/
  app.css                       .bar-stripes (moving only without reduced motion)
  lib/types.ts                  JobStage, Job.stage, RenameBody, RenameTarget
  lib/format.ts                 stageText(job)
  lib/batch.ts                  NEW  noteTransition(prev, next)
  lib/jobs.svelte.ts            finished, showDone, dismissDone
  lib/api.ts                    rename(body)
  lib/components/CassetteDeck.svelte   stage text + progressbar role
  lib/components/DoneDialog.svelte     NEW  <dialog> with done and failed tracks
  lib/components/RenameForm.svelte     NEW  Combobox + merge notice
  lib/components/AlbumGrid.svelte      rename button per card
  routes/+layout.svelte         opens DoneDialog
  routes/library/+page.svelte   rename handler, artist heading rename
  vitest-setup.ts               jsdom shim for HTMLDialogElement.showModal
```

---
### Task 1: Job stage column

**Files:**
- Modify: `app/backend/wyc_music_streaming/jobs.py`
- Test: `app/backend/tests/test_jobs.py`

**Interfaces:**
- Produces: `Job.stage: str | None` (last field, default `None`), `STAGES = ("finding", "downloading", "processing")`, `JobStore.set_stage(job_id, stage)` (raises `ValueError` for an unknown stage). `claim_next` sets `finding`; `retry` and `recover` clear it.

- [ ] **Step 1: Write the failing tests**

Modify `app/backend/tests/test_jobs.py` (apply with `git apply` from the repo root, or edit by hand):

```diff
diff --git a/app/backend/tests/test_jobs.py b/app/backend/tests/test_jobs.py
index 89c995e..00c632c 100644
--- a/app/backend/tests/test_jobs.py
+++ b/app/backend/tests/test_jobs.py
@@ -99,3 +99,44 @@ def test_persists_across_reopen(tmp_path):
     s2 = JobStore(path)
     assert s2.get(a.id).video_id == "aaaaaaaaaaa"
     s2.close()
+
+
+def test_claim_sets_stage_finding_and_set_stage_round_trip(store):
+    [a] = store.add("wick", [item()])
+    assert store.get(a.id).stage is None
+    assert store.claim_next().stage == "finding"
+    store.set_stage(a.id, "downloading")
+    assert store.get(a.id).stage == "downloading"
+    store.fail(a.id, "x")
+    store.retry("wick", a.id)
+    assert store.get(a.id).stage is None
+
+
+def test_recover_clears_stage(store):
+    store.add("wick", [item()])
+    store.claim_next()
+    store.recover()
+    assert store.list_for_user("wick")[0].stage is None
+
+
+def test_old_database_gets_stage_column(tmp_path):
+    import sqlite3
+
+    path = tmp_path / "old.db"
+    db = sqlite3.connect(path)
+    db.executescript("""
+        CREATE TABLE jobs (
+          id INTEGER PRIMARY KEY, user TEXT NOT NULL, video_id TEXT NOT NULL, title TEXT NOT NULL,
+          artist TEXT NOT NULL, album TEXT NOT NULL, track_no INTEGER, year TEXT, cover_url TEXT,
+          box_id TEXT, status TEXT NOT NULL, progress REAL NOT NULL DEFAULT 0, error TEXT,
+          final_path TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
+        INSERT INTO jobs (user, video_id, title, artist, album, status, created_at, updated_at)
+          VALUES ('wick', 'aaaaaaaaaaa', 'Numb', 'Linkin Park', 'Meteora', 'done', 'x', 'x');
+    """)
+    db.close()
+    s = JobStore(path)
+    assert s.get(1).stage is None
+    s.set_stage(1, "processing")
+    assert s.get(1).stage == "processing"
+    s.close()
+    JobStore(path).close()  # opening again must not try to add the column twice
```

- [ ] **Step 2: Run the tests and see them fail**

Run: `uv run pytest -q tests/test_jobs.py`
Expected: 3 new tests fail with `AttributeError` (`stage` / `set_stage`).

- [ ] **Step 3: Write the code**

Modify `app/backend/wyc_music_streaming/jobs.py` (apply with `git apply` from the repo root, or edit by hand):

```diff
diff --git a/app/backend/wyc_music_streaming/jobs.py b/app/backend/wyc_music_streaming/jobs.py
index 61d58b0..9fafc6d 100644
--- a/app/backend/wyc_music_streaming/jobs.py
+++ b/app/backend/wyc_music_streaming/jobs.py
@@ -24,11 +24,13 @@ CREATE TABLE IF NOT EXISTS jobs (
   progress    REAL NOT NULL DEFAULT 0,
   error       TEXT,
   final_path  TEXT,
+  stage       TEXT,                         -- finding / downloading / processing while downloading
   created_at  TEXT NOT NULL,
   updated_at  TEXT NOT NULL
 );
 CREATE INDEX IF NOT EXISTS jobs_user_status ON jobs(user, status);
 """
+STAGES = ("finding", "downloading", "processing")
 
 
 def _now() -> str:
@@ -64,6 +66,7 @@ class Job:
     final_path: str | None
     created_at: str
     updated_at: str
+    stage: str | None = None
 
     def to_dict(self) -> dict[str, Any]:
         return asdict(self)
@@ -78,6 +81,9 @@ class JobStore:
         with self._lock:
             self._db.execute("PRAGMA journal_mode=WAL")
             self._db.executescript(SCHEMA)
+            columns = {row["name"] for row in self._db.execute("PRAGMA table_info(jobs)")}
+            if "stage" not in columns:  # databases created before the stage column
+                self._db.execute("ALTER TABLE jobs ADD COLUMN stage TEXT")
 
     def close(self) -> None:
         self._db.close()
@@ -125,7 +131,8 @@ class JobStore:
                 return None
             job_id = row["id"]
             self._db.execute(
-                "UPDATE jobs SET status = 'downloading', progress = 0, error = NULL, updated_at = ? WHERE id = ?",
+                "UPDATE jobs SET status = 'downloading', progress = 0, error = NULL, stage = 'finding',"
+                " updated_at = ? WHERE id = ?",
                 (_now(), job_id),
             )
         return self.get(job_id)
@@ -140,6 +147,11 @@ class JobStore:
     def set_progress(self, job_id: int, fraction: float) -> None:
         self._update(job_id, "progress = ?", (max(0.0, min(1.0, fraction)),))
 
+    def set_stage(self, job_id: int, stage: str) -> None:
+        if stage not in STAGES:
+            raise ValueError(f"unknown stage {stage!r}")
+        self._update(job_id, "stage = ?", (stage,))
+
     def finish(self, job_id: int, final_path: str) -> None:
         self._update(job_id, "status = 'done', progress = 1, final_path = ?, error = NULL", (final_path,))
 
@@ -158,7 +170,7 @@ class JobStore:
     def retry(self, user: str, job_id: int) -> bool:
         with self._lock:
             cur = self._db.execute(
-                "UPDATE jobs SET status = 'queued', progress = 0, error = NULL, updated_at = ?"
+                "UPDATE jobs SET status = 'queued', progress = 0, error = NULL, stage = NULL, updated_at = ?"
                 " WHERE id = ? AND user = ? AND status = 'failed'",
                 (_now(), job_id, user),
             )
@@ -167,7 +179,8 @@ class JobStore:
     def recover(self) -> int:
         with self._lock:
             cur = self._db.execute(
-                "UPDATE jobs SET status = 'queued', progress = 0, updated_at = ? WHERE status = 'downloading'",
+                "UPDATE jobs SET status = 'queued', progress = 0, stage = NULL, updated_at = ?"
+                " WHERE status = 'downloading'",
                 (_now(),),
             )
         return cur.rowcount
```

- [ ] **Step 4: Run the tests and see them pass**

Run: `uv run pytest -q`
Expected: all tests pass (134).

- [ ] **Step 5: Commit**

```bash
git add app/backend/wyc_music_streaming/jobs.py \
  app/backend/tests/test_jobs.py
git commit -m "feat(backend): add a stage column to jobs"
```

### Task 2: Worker stages and a throttle that keeps 100 %

**Files:**
- Modify: `app/backend/wyc_music_streaming/worker.py`, `app/backend/tests/test_worker.py`, `app/backend/tests/test_api.py` (the fake downloader signature)

**Interfaces:**
- Consumes: `JobStore.set_stage` (Task 1).
- Produces: `StageFn = Callable[[str], None]`; `Downloader = Callable[[Job, Path, ProgressFn, StageFn], tuple[Path, Path | None]]`; `progress_hook(on_progress, on_stage) -> Callable[[dict], None]`; `ytdlp_download(job, tmp_dir, on_progress, on_stage)`.
- The worker drops repeated stages, and sets `processing` itself after the downloader returns.

- [ ] **Step 1: Write the failing tests**

Modify `app/backend/tests/test_worker.py` (apply with `git apply` from the repo root, or edit by hand):

```diff
diff --git a/app/backend/tests/test_worker.py b/app/backend/tests/test_worker.py
index d5ec1a1..48b934b 100644
--- a/app/backend/tests/test_worker.py
+++ b/app/backend/tests/test_worker.py
@@ -8,7 +8,7 @@ from wyc_music_streaming.events import EventBroker
 from wyc_music_streaming.jobs import JobStore, NewJob
 from wyc_music_streaming.library import Library
 from wyc_music_streaming.tags import read_tags
-from wyc_music_streaming.worker import Worker
+from wyc_music_streaming.worker import Worker, progress_hook
 
 
 class FakeRefresher:
@@ -26,8 +26,12 @@ def env(config, make_audio, tmp_path):
     events = EventBroker()
     refresher = FakeRefresher()
 
-    def good_downloader(job, tmp_dir, on_progress):
+    def good_downloader(job, tmp_dir, on_progress, on_stage):
+        on_stage("downloading")
         on_progress(0.5)
+        on_progress(0.7)  # inside the throttle window: dropped
+        on_progress(1.0)  # the last update always goes out
+        on_stage("processing")
         audio = make_audio(tmp_dir / f"{job.id}.m4a")
         thumb = tmp_dir / f"{job.id}.jpg"
         thumb.write_bytes(b"THUMB")
@@ -109,7 +113,8 @@ async def test_job_done_moves_tags_and_notifies(env):
     assert env.refresher.calls == 1
     events = drain(q)
     assert [e["type"] for e in events].count("job") >= 2
-    assert any(e["type"] == "job" and e["data"]["progress"] == 0.5 for e in events)
+    progress = [e["data"]["progress"] for e in events if e["type"] == "job" and e["data"]["status"] == "downloading"]
+    assert 0.5 in progress and 1.0 in progress and 0.7 not in progress
     assert events[-1]["type"] == "library"
     assert list(env.tmp_dir.iterdir()) == []
 
@@ -154,7 +159,7 @@ async def test_name_collision_adds_suffix(env, make_audio):
 
 
 async def test_download_error_marks_failed_and_cleans_tmp(env):
-    def broken(job, tmp_dir, on_progress):
+    def broken(job, tmp_dir, on_progress, on_stage):
         (tmp_dir / f"{job.id}.m4a.part").write_bytes(b"partial")
         raise RuntimeError("ERROR: [youtube] kXYiU_JCYtU: Sign in to confirm you're not a bot\nmore lines")
 
@@ -195,3 +200,46 @@ async def test_started_loop_processes_queued_job(env):
         for t in tasks:
             t.cancel()
         await asyncio.gather(*tasks, return_exceptions=True)
+
+
+async def test_stages_go_finding_downloading_processing(env):
+    worker = env.make_worker()
+    q = env.events.subscribe("wick")
+    job = queue_job(env)
+    assert job.stage == "finding"
+
+    await worker.process(job)
+
+    stages = [e["data"]["stage"] for e in drain(q) if e["type"] == "job" and e["data"]["status"] == "downloading"]
+    order = [s for i, s in enumerate(stages) if i == 0 or stages[i - 1] != s]
+    assert order == ["finding", "downloading", "processing"]
+
+
+async def test_processing_stage_is_set_even_if_the_downloader_never_says_so(env, make_audio):
+    def quiet(job, tmp_dir, on_progress, on_stage):
+        return make_audio(tmp_dir / f"{job.id}.m4a"), None
+
+    worker = env.make_worker(downloader=quiet)
+    q = env.events.subscribe("wick")
+    job = queue_job(env)
+    await worker.process(job)
+    stages = [e["data"]["stage"] for e in drain(q) if e["type"] == "job" and e["data"]["status"] == "downloading"]
+    assert stages[-1] == "processing"
+
+
+def test_progress_hook_maps_ytdlp_events():
+    calls = []
+    hook = progress_hook(lambda f: calls.append(("progress", f)), lambda s: calls.append(("stage", s)))
+    hook({"status": "downloading", "downloaded_bytes": 0, "total_bytes": None})
+    hook({"status": "downloading", "downloaded_bytes": 50, "total_bytes": 200})
+    hook({"status": "downloading", "downloaded_bytes": 100, "total_bytes_estimate": 200})
+    hook({"status": "finished", "downloaded_bytes": 200, "total_bytes": 200})
+    assert calls == [
+        ("stage", "downloading"),
+        ("stage", "downloading"),
+        ("progress", 0.25),
+        ("stage", "downloading"),
+        ("progress", 0.5),
+        ("progress", 1.0),
+        ("stage", "processing"),
+    ]
```

Modify `app/backend/tests/test_api.py` (apply with `git apply` from the repo root, or edit by hand):

```diff
diff --git a/app/backend/tests/test_api.py b/app/backend/tests/test_api.py
index e705877..c664de0 100644
--- a/app/backend/tests/test_api.py
+++ b/app/backend/tests/test_api.py
@@ -26,7 +26,7 @@ def wait_for(predicate, timeout=10.0):
 
 @pytest.fixture
 def client(config, make_audio):
-    def downloader(job, tmp_dir, on_progress):
+    def downloader(job, tmp_dir, on_progress, on_stage):
         if job.video_id == "failfailfai":
             raise RuntimeError("ERROR: Video unavailable")
         return make_audio(tmp_dir / f"{job.id}.m4a"), None
```

- [ ] **Step 2: Run the tests and see them fail**

Run: `uv run pytest -q tests/test_worker.py`
Expected: collection error `ImportError: cannot import name 'progress_hook' from 'wyc_music_streaming.worker'`.

- [ ] **Step 3: Write the code**

Modify `app/backend/wyc_music_streaming/worker.py` (apply with `git apply` from the repo root, or edit by hand):

```diff
diff --git a/app/backend/wyc_music_streaming/worker.py b/app/backend/wyc_music_streaming/worker.py
index e508dac..4b62d93 100644
--- a/app/backend/wyc_music_streaming/worker.py
+++ b/app/backend/wyc_music_streaming/worker.py
@@ -21,7 +21,8 @@ from .tags import TagData, write_tags
 log = logging.getLogger(__name__)
 
 ProgressFn = Callable[[float], None]
-Downloader = Callable[[Job, Path, ProgressFn], tuple[Path, Path | None]]
+StageFn = Callable[[str], None]
+Downloader = Callable[[Job, Path, ProgressFn, StageFn], tuple[Path, Path | None]]
 CoverFetcher = Callable[[str], Awaitable[bytes | None]]
 
 TMP_DIR_NAME = ".wyc-music-streaming-tmp"
@@ -40,14 +41,31 @@ class Refresher(Protocol):
     def schedule(self) -> None: ...
 
 
-def ytdlp_download(job: Job, tmp_dir: Path, on_progress: ProgressFn) -> tuple[Path, Path | None]:
-    from yt_dlp import YoutubeDL
+def progress_hook(on_progress: ProgressFn, on_stage: StageFn) -> Callable[[dict[str, Any]], None]:
+    """yt-dlp progress hook. Repeated stages are fine: the worker drops repeats.
+
+    "finished" (the bytes are all here) marks the start of processing. A postprocessor hook
+    would not do: the thumbnail converter runs before the download ("before_dl").
+    """
 
     def hook(d: dict[str, Any]) -> None:
         if d.get("status") == "downloading":
+            on_stage("downloading")
             total = d.get("total_bytes") or d.get("total_bytes_estimate")
             if total:
                 on_progress(min(d.get("downloaded_bytes", 0) / total, 1.0))
+        elif d.get("status") == "finished":
+            on_progress(1.0)
+            on_stage("processing")
+
+    return hook
+
+
+def ytdlp_download(
+    job: Job, tmp_dir: Path, on_progress: ProgressFn, on_stage: StageFn
+) -> tuple[Path, Path | None]:
+    from yt_dlp import YoutubeDL
+
 
     opts = {
         "format": "bestaudio[ext=m4a]/bestaudio",
@@ -58,7 +76,7 @@ def ytdlp_download(job: Job, tmp_dir: Path, on_progress: ProgressFn) -> tuple[Pa
         "no_warnings": True,
         "noprogress": True,
         "socket_timeout": 30,
-        "progress_hooks": [hook],
+        "progress_hooks": [progress_hook(on_progress, on_stage)],
         "postprocessors": [
             # "best" = stream copy into a taggable container (aac→.m4a, opus→.opus). Never re-encode.
             {"key": "FFmpegExtractAudio", "preferredcodec": "best"},
@@ -179,17 +197,26 @@ class Worker:
 
         loop = asyncio.get_running_loop()
         last_sent = float("-inf")
+        stage = job.stage
 
         def on_progress(fraction: float) -> None:  # runs in the yt-dlp thread
             nonlocal last_sent
             now = time.monotonic()
-            if now - last_sent < PROGRESS_INTERVAL:
-                return
+            if fraction < 1.0 and now - last_sent < PROGRESS_INTERVAL:
+                return  # throttle, but never drop the final 100 %
             last_sent = now
             loop.call_soon_threadsafe(self._progress, job.id, fraction)
 
+        def on_stage(next_stage: str) -> None:  # runs in the yt-dlp thread
+            nonlocal stage
+            if next_stage == stage:
+                return
+            stage = next_stage
+            loop.call_soon_threadsafe(self._stage, job.id, next_stage)
+
         try:
-            audio, thumb = await asyncio.to_thread(self.downloader, job, tmp_dir, on_progress)
+            audio, thumb = await asyncio.to_thread(self.downloader, job, tmp_dir, on_progress, on_stage)
+            on_stage("processing")  # cover, tags and the move still follow
             cover = await self.fetch_cover(job.cover_url) if job.cover_url else None
             if cover is None and thumb is not None and thumb.exists():
                 cover = thumb.read_bytes()
@@ -230,6 +257,10 @@ class Worker:
         self.store.set_progress(job_id, fraction)
         self._publish_job(job_id)
 
+    def _stage(self, job_id: int, stage: str) -> None:
+        self.store.set_stage(job_id, stage)
+        self._publish_job(job_id)
+
     def _publish_job(self, job_id: int) -> None:
         job = self.store.get(job_id)
         if job is not None:
```

- [ ] **Step 4: Run the tests and see them pass**

Run: `uv run pytest -q`
Expected: all tests pass (137).

- [ ] **Step 5: Commit**

```bash
git add app/backend/wyc_music_streaming/worker.py \
  app/backend/tests/test_worker.py \
  app/backend/tests/test_api.py
git commit -m "feat(backend): report download stages and never drop the final progress"
```

### Task 3: Partial retag

**Files:**
- Modify: `app/backend/wyc_music_streaming/tags.py`
- Test: `app/backend/tests/test_tags.py`

**Interfaces:**
- Produces: `retag(path, *, artist=None, album=None, album_artist=None)`; changes only the given tags on .m4a, .opus/.ogg, .mp3, .flac; adds a tag block when the file has none; raises `ValueError("cannot open ...")` for a non-audio file.

- [ ] **Step 1: Write the failing tests**

Modify `app/backend/tests/test_tags.py` (apply with `git apply` from the repo root, or edit by hand):

```diff
diff --git a/app/backend/tests/test_tags.py b/app/backend/tests/test_tags.py
index 3f35198..20cef83 100644
--- a/app/backend/tests/test_tags.py
+++ b/app/backend/tests/test_tags.py
@@ -2,7 +2,7 @@ import pytest
 from mutagen.mp4 import MP4
 from mutagen.oggopus import OggOpus
 
-from wyc_music_streaming.tags import TagData, read_tags, write_tags
+from wyc_music_streaming.tags import TagData, read_tags, retag, write_tags
 
 FULL = TagData(
     title="Faint", artist="Linkin Park", album="Meteora", album_artist="Linkin Park",
@@ -58,3 +58,36 @@ def test_read_non_audio_returns_empty(tmp_path):
 def test_write_unsupported_container(make_audio, tmp_path):
     with pytest.raises(ValueError, match="unsupported container"):
         write_tags(make_audio(tmp_path / "a.mp3"), FULL)
+
+
+@pytest.mark.parametrize("ext", [".m4a", ".opus"])
+def test_retag_changes_only_the_given_fields(make_audio, tmp_path, ext):
+    path = make_audio(tmp_path / f"a{ext}")
+    write_tags(path, FULL)
+    retag(path, album="Meteora (Live)")
+    got = read_tags(path)
+    assert got["album"] == "Meteora (Live)"
+    assert (got["title"], got["artist"], got["album_artist"], got["track_no"], got["video_id"]) == (
+        "Faint", "Linkin Park", "Linkin Park", 7, "kXYiU_JCYtU")
+    retag(path, artist="LP", album_artist="LP")
+    got = read_tags(path)
+    assert (got["artist"], got["album_artist"], got["album"]) == ("LP", "LP", "Meteora (Live)")
+    if ext == ".m4a":
+        assert MP4(path)["covr"][0] == b"COVER"
+    else:
+        assert OggOpus(path)["metadata_block_picture"]
+
+
+@pytest.mark.parametrize("ext", [".mp3", ".flac"])
+def test_retag_files_added_by_hand(make_audio, tmp_path, ext):
+    path = make_audio(tmp_path / f"a{ext}")
+    retag(path, album="Bad", album_artist="MJ")
+    got = read_tags(path)
+    assert (got["album"], got["album_artist"]) == ("Bad", "MJ")
+
+
+def test_retag_non_audio_raises(tmp_path):
+    p = tmp_path / "x.m4a"
+    p.write_bytes(b"not audio")
+    with pytest.raises(ValueError, match="cannot open"):
+        retag(p, album="x")
```

- [ ] **Step 2: Run the tests and see them fail**

Run: `uv run pytest -q tests/test_tags.py`
Expected: collection error `ImportError: cannot import name 'retag'`.

- [ ] **Step 3: Write the code**

Modify `app/backend/wyc_music_streaming/tags.py` (apply with `git apply` from the repo root, or edit by hand):

```diff
diff --git a/app/backend/wyc_music_streaming/tags.py b/app/backend/wyc_music_streaming/tags.py
index 2b92f58..c8aba43 100644
--- a/app/backend/wyc_music_streaming/tags.py
+++ b/app/backend/wyc_music_streaming/tags.py
@@ -75,6 +75,27 @@ def write_tags(path: Path, tags: TagData) -> None:
     raise ValueError(f"unsupported container: {ext}")
 
 
+def retag(
+    path: Path, *, artist: str | None = None, album: str | None = None, album_artist: str | None = None
+) -> None:
+    """Change only the given text tags (any container mutagen's easy interface knows: m4a, opus/ogg, mp3, flac).
+
+    Title, track number, year, cover and the youtube: comment stay as they are.
+    """
+    try:
+        f = MutagenFile(path, easy=True)
+    except (MutagenError, OSError) as exc:
+        raise ValueError(f"cannot open {path.name} for tagging: {exc}") from exc
+    if f is None:
+        raise ValueError(f"cannot open {path.name} for tagging")
+    if f.tags is None:
+        f.add_tags()
+    for key, value in (("artist", artist), ("album", album), ("albumartist", album_artist)):
+        if value is not None:
+            f[key] = [value]
+    f.save()
+
+
 def _parse_track(value: str | None) -> int | None:
     if not value:
         return None
```

- [ ] **Step 4: Run the tests and see them pass**

Run: `uv run pytest -q tests/test_tags.py`
Expected: 11 passed.

- [ ] **Step 5: Commit**

```bash
git add app/backend/wyc_music_streaming/tags.py \
  app/backend/tests/test_tags.py
git commit -m "feat(backend): add retag for partial tag changes"
```

### Task 4: Rename and merge

**Files:**
- Create: `app/backend/wyc_music_streaming/rename.py`, `app/backend/tests/test_rename.py`
- Modify: `app/backend/wyc_music_streaming/paths.py`, `app/backend/wyc_music_streaming/library.py`, `app/backend/wyc_music_streaming/jobs.py`, `app/backend/wyc_music_streaming/api.py`, `app/backend/tests/test_jobs.py`, `app/backend/tests/test_api.py`

**Interfaces:**
- Consumes: `retag`, `read_tags` (Task 3), `Library.tracks/rescan`, `sanitize_name`, `safe_resolve`, `unique_path`.
- Produces: `remove_empty_parents(root, start)`; `JobStore.has_active_for(user, artist, album=None) -> bool`;
  `rename(library, user, *, kind, artist, new_name, album=None) -> RenameResult(moved, merged)`;
  `PartialRename(moved, cause)` (a `RuntimeError`, message "ย้ายแล้ว <n> เพลง ก่อนเกิดปัญหา: ...");
  `POST /api/library/rename`.

Details worth knowing:
- Files without tags keep the names they showed: an album rename writes `albumartist` when the file had no artist tags; an artist rename writes `album` when the file had none.
- When the sanitized destination folder is the current folder (for example "Off_the_Wall" → "Off the Wall"), only the tags change.
- The library rescans in `finally`, so a partial failure still shows the real state.

- [ ] **Step 1: Write the failing tests**

Create `app/backend/tests/test_rename.py`:

```python
import pytest
from mutagen.mp4 import MP4

from wyc_music_streaming.library import Library
from wyc_music_streaming.rename import PartialRename, rename
from wyc_music_streaming.tags import TagData, read_tags, write_tags


@pytest.fixture
def env(config, make_audio):
    root = config.users["wick"].music_dir
    lib = Library(config.users)

    def add(rel, title, artist="MJ", album="Bad", track_artist=None, cover=None, tags=True):
        path = make_audio(root / rel)
        if tags:
            write_tags(path, TagData(title, track_artist or artist, album, artist, "aaaaaaaaaaa", cover_jpeg=cover))
        return path

    def run(**kw):
        result = rename(lib, config.users["wick"], **kw)
        return result

    def tree():
        lib.rescan("wick")
        return {(a["artist"], al["album"]): sorted(t["path"] for t in al["tracks"])
                for a in lib.tree("wick") for al in a["albums"]}

    return type("Env", (), {"root": root, "lib": lib, "add": staticmethod(add), "run": staticmethod(run),
                            "tree": staticmethod(tree)})


def test_rename_album_retags_moves_and_removes_old_folder(env):
    env.add("MJ/Bad/Bad.m4a", "Bad", cover=b"COVER")
    env.add("MJ/Bad/Smooth_Criminal.m4a", "Smooth Criminal")
    env.add("MJ/Thriller/Beat_It.m4a", "Beat It", album="Thriller")
    env.lib.rescan("wick")

    result = env.run(kind="album", artist="MJ", album="Bad", new_name="Bad (Special Edition)")

    assert (result.moved, result.merged) == (2, False)
    assert env.tree() == {
        ("MJ", "Bad (Special Edition)"): ["MJ/Bad_(Special_Edition)/Bad.m4a", "MJ/Bad_(Special_Edition)/Smooth_Criminal.m4a"],
        ("MJ", "Thriller"): ["MJ/Thriller/Beat_It.m4a"],
    }
    assert not (env.root / "MJ" / "Bad").exists()
    moved = env.root / "MJ/Bad_(Special_Edition)/Bad.m4a"
    tags = read_tags(moved)
    assert (tags["title"], tags["album"], tags["album_artist"], tags["video_id"]) == (
        "Bad", "Bad (Special Edition)", "MJ", "aaaaaaaaaaa")
    assert MP4(moved)["covr"][0] == b"COVER"


def test_rename_artist_keeps_feat_track_artists(env):
    env.add("linkinpark/Meteora/Numb.m4a", "Numb", artist="linkinpark", album="Meteora")
    env.add("linkinpark/Meteora/Faint.m4a", "Faint", artist="linkinpark", album="Meteora",
            track_artist="linkinpark feat. Jay-Z")
    env.lib.rescan("wick")

    result = env.run(kind="artist", artist="linkinpark", new_name="Linkin Park")

    assert result.moved == 2
    assert env.tree() == {("Linkin Park", "Meteora"): ["Linkin_Park/Meteora/Faint.m4a", "Linkin_Park/Meteora/Numb.m4a"]}
    numb = read_tags(env.root / "Linkin_Park/Meteora/Numb.m4a")
    faint = read_tags(env.root / "Linkin_Park/Meteora/Faint.m4a")
    assert (numb["artist"], numb["album_artist"]) == ("Linkin Park", "Linkin Park")
    assert (faint["artist"], faint["album_artist"]) == ("linkinpark feat. Jay-Z", "Linkin Park")
    assert not (env.root / "linkinpark").exists()


def test_merge_into_existing_artist_with_name_clash(env):
    env.add("The_Weeknd/Singles/One_Of_The_Girls.m4a", "One Of The Girls", artist="The Weeknd", album="Singles")
    env.add("The_Weeknd,_JENNIE_&_Lily_Rose_Depp/Singles/One_Of_The_Girls.m4a", "One Of The Girls",
            artist="The Weeknd, JENNIE & Lily Rose Depp", album="Singles")
    env.lib.rescan("wick")

    result = env.run(kind="artist", artist="The Weeknd, JENNIE & Lily Rose Depp", new_name="The Weeknd")

    assert (result.moved, result.merged) == (1, True)
    assert env.tree() == {("The Weeknd", "Singles"): [
        "The_Weeknd/Singles/One_Of_The_Girls.m4a", "The_Weeknd/Singles/One_Of_The_Girls_(2).m4a"]}


def test_untagged_files_get_tags_from_the_names_they_showed(env):
    env.add("MJ/Off_the_Wall/Rock_With_You.mp3", "x", tags=False)
    env.lib.rescan("wick")
    assert ("MJ", "Off_the_Wall") in env.tree()

    env.run(kind="album", artist="MJ", album="Off_the_Wall", new_name="Off the Wall")

    # Same folder after sanitizing: the file stays, only the tags change.
    assert env.tree() == {("MJ", "Off the Wall"): ["MJ/Off_the_Wall/Rock_With_You.mp3"]}
    tags = read_tags(env.root / "MJ/Off_the_Wall/Rock_With_You.mp3")
    assert (tags["album"], tags["album_artist"]) == ("Off the Wall", "MJ")


def test_crafted_name_stays_inside_music_dir(env):
    env.add("MJ/Bad/Bad.m4a", "Bad")
    env.lib.rescan("wick")
    env.run(kind="album", artist="MJ", album="Bad", new_name="../../etc")
    [(key, paths)] = env.tree().items()
    assert key == ("MJ", "../../etc")
    assert paths == ["MJ/etc/Bad.m4a"]


@pytest.mark.parametrize(
    ("kw", "error"),
    [
        ({"kind": "album", "artist": "MJ", "album": "Bad", "new_name": "  "}, ValueError),
        ({"kind": "album", "artist": "MJ", "album": "Bad", "new_name": "Bad"}, ValueError),
        ({"kind": "album", "artist": "MJ", "album": None, "new_name": "X"}, ValueError),
        ({"kind": "album", "artist": "MJ", "album": "Nope", "new_name": "X"}, LookupError),
        ({"kind": "artist", "artist": "Nobody", "new_name": "X"}, LookupError),
    ],
)
def test_bad_requests(env, kw, error):
    env.add("MJ/Bad/Bad.m4a", "Bad")
    env.lib.rescan("wick")
    with pytest.raises(error):
        env.run(**kw)


def test_failure_midway_reports_moved_count_and_rescans(env, monkeypatch):
    env.add("MJ/Bad/A.m4a", "A")
    env.add("MJ/Bad/B.m4a", "B")
    env.lib.rescan("wick")
    import wyc_music_streaming.rename as mod

    real = mod.retag
    calls = []

    def flaky(path, **kw):
        calls.append(path)
        if len(calls) == 2:
            raise ValueError("disk said no")
        real(path, **kw)

    monkeypatch.setattr(mod, "retag", flaky)
    with pytest.raises(PartialRename) as info:
        env.run(kind="album", artist="MJ", album="Bad", new_name="Bad 2")
    assert info.value.moved == 1
    assert "disk said no" in str(info.value)
    # The index was rescanned without our help: one track moved, one did not.
    assert sorted(t.album for t in env.lib.tracks("wick")) == ["Bad", "Bad 2"]
    assert sum(len(p) for p in env.tree().values()) == 2
```

Modify `app/backend/tests/test_jobs.py` (apply with `git apply` from the repo root, or edit by hand):

```diff
diff --git a/app/backend/tests/test_jobs.py b/app/backend/tests/test_jobs.py
index 00c632c..80102b9 100644
--- a/app/backend/tests/test_jobs.py
+++ b/app/backend/tests/test_jobs.py
@@ -140,3 +140,14 @@ def test_old_database_gets_stage_column(tmp_path):
     assert s.get(1).stage == "processing"
     s.close()
     JobStore(path).close()  # opening again must not try to add the column twice
+
+
+def test_has_active_for_artist_and_album(store):
+    a, b = store.add("wick", [item("aaaaaaaaaaa"), item("bbbbbbbbbbb", )])
+    assert store.has_active_for("wick", "Linkin Park")
+    assert store.has_active_for("wick", "Linkin Park", "Meteora")
+    assert not store.has_active_for("wick", "Linkin Park", "Hybrid Theory")
+    assert not store.has_active_for("safeena", "Linkin Park")
+    store.finish(a.id, "x.m4a")
+    store.fail(b.id, "x")
+    assert not store.has_active_for("wick", "Linkin Park")
```

Modify `app/backend/tests/test_api.py` (apply with `git apply` from the repo root, or edit by hand):

```diff
diff --git a/app/backend/tests/test_api.py b/app/backend/tests/test_api.py
index c664de0..e658fab 100644
--- a/app/backend/tests/test_api.py
+++ b/app/backend/tests/test_api.py
@@ -192,3 +192,49 @@ def test_spa_fallback(config, tmp_path):
     assert c.get("/library").text == "<html>app</html>"
     assert c.get("/app.js").text == "js"
     assert c.get("/api/nope").status_code == 404
+
+
+def test_rename_album_and_artist(client):
+    download_numb(client)
+    r = client.post("/api/library/rename", json={
+        "kind": "album", "artist": "Linkin Park", "album": "Singles", "new_name": "Meteora"})
+    assert r.status_code == 200
+    assert r.json() == {"moved": 1, "merged": False}
+    r = client.post("/api/library/rename", json={"kind": "artist", "artist": "Linkin Park", "new_name": "LP"})
+    assert r.json() == {"moved": 1, "merged": False}
+    [artist] = client.get("/api/library").json()["artists"]
+    assert artist["artist"] == "LP"
+    assert artist["albums"][0]["album"] == "Meteora"
+    assert artist["albums"][0]["tracks"][0]["path"] == "LP/Meteora/Numb.m4a"
+    wait_for(lambda: client.jf_calls)
+
+
+def test_rename_errors(client):
+    def post(body):
+        return client.post("/api/library/rename", json=body)
+
+    assert post({"kind": "artist", "artist": "Nobody", "new_name": "X"}).status_code == 404
+    download_numb(client)
+    assert post({"kind": "artist", "artist": "Linkin Park", "new_name": "Linkin Park"}).status_code == 400
+    assert post({"kind": "album", "artist": "Linkin Park", "new_name": "X"}).status_code == 400
+    assert post({"kind": "song", "artist": "Linkin Park", "new_name": "X"}).status_code == 422
+    assert post({"kind": "artist", "artist": "Linkin Park", "new_name": ""}).status_code == 422
+    assert post({"kind": "artist", "artist": "Linkin Park", "new_name": "x" * 301}).status_code == 422
+
+
+def test_rename_blocked_while_a_job_is_active(config, make_audio):
+    def downloader(job, tmp_dir, on_progress, on_stage):
+        return make_audio(tmp_dir / f"{job.id}.m4a"), None
+
+    app = create_app(config, downloader=downloader, extract=lambda t, o: NUMB,
+                     jellyfin_transport=httpx.MockTransport(lambda r: httpx.Response(204)),
+                     suggest_transport=httpx.MockTransport(lambda r: httpx.Response(200, json=["", []])),
+                     start_workers=False)
+    with TestClient(app, headers=WICK) as c:
+        make_audio(config.users["wick"].music_dir / "Linkin_Park" / "Singles" / "Old.m4a")
+        c.post("/api/library/rescan")
+        c.post("/api/jobs", json={"items": [
+            {"video_id": "kXYiU_JCYtU", "title": "Numb", "artist": "Linkin_Park", "album": "Singles"}]})
+        r = c.post("/api/library/rename", json={"kind": "artist", "artist": "Linkin_Park", "new_name": "LP"})
+        assert r.status_code == 409
+        assert "รอคิวหมดก่อน" in r.json()["detail"]
```

- [ ] **Step 2: Run the tests and see them fail**

Run: `uv run pytest -q tests/test_rename.py tests/test_jobs.py tests/test_api.py`
Expected: collection error `ModuleNotFoundError: No module named 'wyc_music_streaming.rename'`; after that file exists, `has_active_for` and the rename route tests fail (404 for the route).

- [ ] **Step 3: Write the code**

Modify `app/backend/wyc_music_streaming/paths.py` (apply with `git apply` from the repo root, or edit by hand):

```diff
diff --git a/app/backend/wyc_music_streaming/paths.py b/app/backend/wyc_music_streaming/paths.py
index 004bbad..52ac860 100644
--- a/app/backend/wyc_music_streaming/paths.py
+++ b/app/backend/wyc_music_streaming/paths.py
@@ -29,6 +29,18 @@ def safe_resolve(root: Path, rel: str) -> Path:
     return target
 
 
+def remove_empty_parents(root: Path, start: Path) -> None:
+    """Remove start and its parents while they are empty, stopping at root (root stays)."""
+    root_resolved = root.resolve()
+    folder = start
+    while folder != root_resolved and folder.is_relative_to(root_resolved):
+        try:
+            folder.rmdir()  # only succeeds when empty
+        except OSError:
+            break
+        folder = folder.parent
+
+
 def unique_path(path: Path) -> Path:
     if not path.exists():
         return path
```

Modify `app/backend/wyc_music_streaming/library.py` (apply with `git apply` from the repo root, or edit by hand):

```diff
diff --git a/app/backend/wyc_music_streaming/library.py b/app/backend/wyc_music_streaming/library.py
index c7d065a..2f2ca3c 100644
--- a/app/backend/wyc_music_streaming/library.py
+++ b/app/backend/wyc_music_streaming/library.py
@@ -8,7 +8,7 @@ from pathlib import Path
 from typing import Any
 
 from .config import User
-from .paths import safe_resolve
+from .paths import remove_empty_parents, safe_resolve
 from .tags import read_tags
 
 AUDIO_EXTS = frozenset({".m4a", ".mp3", ".opus", ".flac", ".ogg"})
@@ -114,13 +114,7 @@ class Library:
             raise FileNotFoundError(rel_path)
         target.unlink()
         root_resolved = root.resolve()
-        parent = target.parent
-        while parent != root_resolved and parent.is_relative_to(root_resolved):
-            try:
-                parent.rmdir()  # only succeeds when empty
-            except OSError:
-                break
-            parent = parent.parent
+        remove_empty_parents(root_resolved, target.parent)
         key = target.relative_to(root_resolved).as_posix()
         with self._lock:
             self._tracks[user].pop(key, None)
```

Create `app/backend/wyc_music_streaming/rename.py`:

```python
"""Rename (or merge) an album or an artist: rewrite tags, move files, drop empty folders."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

from .config import User
from .library import Library
from .paths import remove_empty_parents, safe_resolve, sanitize_name, unique_path
from .tags import read_tags, retag

Kind = Literal["album", "artist"]


@dataclass(frozen=True)
class RenameResult:
    moved: int
    merged: bool


class PartialRename(RuntimeError):
    """A track failed after `moved` tracks were already renamed."""

    def __init__(self, moved: int, cause: BaseException):
        super().__init__(f"ย้ายแล้ว {moved} เพลง ก่อนเกิดปัญหา: {cause}")
        self.moved = moved


def rename(library: Library, user: User, *, kind: Kind, artist: str, new_name: str,
           album: str | None = None) -> RenameResult:
    """artist/album are the names /api/library shows. Raises ValueError, LookupError or PartialRename."""
    new = new_name.strip()
    if kind == "album" and not album:
        raise ValueError("ต้องระบุอัลบั้ม")
    old = artist if kind == "artist" else album
    if not new:
        raise ValueError("ชื่อใหม่ว่างอยู่")
    if new == old:
        raise ValueError("ชื่อใหม่เหมือนชื่อเดิม")

    every = library.tracks(user.name)
    picked = [t for t in every if t.artist == artist and (kind == "artist" or t.album == album)]
    if not picked:
        raise LookupError("ไม่พบเพลงที่จะเปลี่ยนชื่อ")
    picked_paths = {t.path for t in picked}
    merged = any(
        t.path not in picked_paths and t.artist == (new if kind == "artist" else artist)
        and (kind == "artist" or t.album == new)
        for t in every
    )

    root = user.music_dir
    root_resolved = root.resolve()
    moved = 0
    try:
        for track in picked:
            src = safe_resolve(root, track.path)
            tags = read_tags(src)
            if kind == "album":
                dest_artist, dest_album = artist, new
                changes = {"album": new}
                if not (tags.get("album_artist") or tags.get("artist")):
                    changes["album_artist"] = artist  # keep the artist the folder gave it
            else:
                dest_artist, dest_album = new, track.album
                changes = {"album_artist": new}
                if not tags.get("artist") or tags.get("artist") == artist:
                    changes["artist"] = new  # keep "X feat. Y" track artists
                if not tags.get("album"):
                    changes["album"] = track.album
            retag(src, **changes)
            dest_dir = root_resolved / sanitize_name(dest_artist) / sanitize_name(dest_album, fallback="Singles")
            if dest_dir != src.parent:
                dest_dir.mkdir(parents=True, exist_ok=True)
                os.replace(src, unique_path(dest_dir / src.name))
                remove_empty_parents(root_resolved, src.parent)
            moved += 1
    except (OSError, ValueError) as exc:
        raise PartialRename(moved, exc) from exc
    finally:
        library.rescan(user.name)
    return RenameResult(moved=moved, merged=merged)
```

Modify `app/backend/wyc_music_streaming/jobs.py` (apply with `git apply` from the repo root, or edit by hand):

```diff
diff --git a/app/backend/wyc_music_streaming/jobs.py b/app/backend/wyc_music_streaming/jobs.py
index 9fafc6d..288074f 100644
--- a/app/backend/wyc_music_streaming/jobs.py
+++ b/app/backend/wyc_music_streaming/jobs.py
@@ -122,6 +122,16 @@ class JobStore:
             ).fetchone()
         return row is not None
 
+    def has_active_for(self, user: str, artist: str, album: str | None = None) -> bool:
+        """A queued or downloading job of this user goes to this artist (and album, when given)."""
+        sql = "SELECT 1 FROM jobs WHERE user = ? AND artist = ? AND status IN ('queued','downloading')"
+        params: tuple[Any, ...] = (user, artist)
+        if album is not None:
+            sql += " AND album = ?"
+            params += (album,)
+        with self._lock:
+            return self._db.execute(sql + " LIMIT 1", params).fetchone() is not None
+
     def claim_next(self) -> Job | None:
         with self._lock:
             row = self._db.execute(
```

Modify `app/backend/wyc_music_streaming/api.py` (apply with `git apply` from the repo root, or edit by hand):

```diff
diff --git a/app/backend/wyc_music_streaming/api.py b/app/backend/wyc_music_streaming/api.py
index 3b3f439..be5b6b8 100644
--- a/app/backend/wyc_music_streaming/api.py
+++ b/app/backend/wyc_music_streaming/api.py
@@ -7,7 +7,7 @@ from __future__ import annotations
 
 import asyncio
 import logging
-from typing import Annotated, Any
+from typing import Annotated, Any, Literal
 
 from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
 from fastapi.responses import StreamingResponse
@@ -20,6 +20,7 @@ from .config import User
 from .events import format_sse
 from .jobs import NewJob
 from .paths import UnsafePath
+from .rename import PartialRename, rename
 from .search import MAX_PAGES, SEARCH_TIMEOUT, search
 from .suggest import fetch_suggestions
 
@@ -56,6 +57,13 @@ class TrackRef(BaseModel):
     path: str = Field(min_length=1, max_length=1000)
 
 
+class RenameRequest(BaseModel):
+    kind: Literal["album", "artist"]
+    artist: str = Field(min_length=1, max_length=300)
+    album: str | None = Field(default=None, max_length=300)
+    new_name: str = Field(min_length=1, max_length=300)
+
+
 @router.get("/me")
 async def me(user: UserDep) -> dict[str, Any]:
     return {"name": user.name, "login": user.tailscale_login, "jellyfin_user": user.jellyfin_user}
@@ -152,6 +160,31 @@ async def rescan_library(request: Request, user: UserDep) -> dict[str, int]:
     return {"tracks": count}
 
 
+@router.post("/library/rename")
+async def rename_route(request: Request, user: UserDep, body: RenameRequest) -> dict[str, Any]:
+    st = request.app.state
+    album = body.album if body.kind == "album" else None
+    if st.store.has_active_for(user.name, body.artist, album):
+        what = "อัลบั้ม" if album is not None else "ศิลปิน"
+        raise HTTPException(status_code=409, detail=f"มีเพลงกำลังโหลดเข้า{what}นี้ รอคิวหมดก่อน")
+    try:
+        result = await run_in_threadpool(
+            rename, st.library, user, kind=body.kind, artist=body.artist, album=album, new_name=body.new_name
+        )
+    except ValueError as exc:
+        raise HTTPException(status_code=400, detail=str(exc)) from None
+    except LookupError:
+        raise HTTPException(status_code=404, detail="ไม่พบเพลงที่จะเปลี่ยนชื่อ") from None
+    except PartialRename as exc:
+        log.warning("rename for %s stopped midway: %s", user.name, exc)
+        st.refresher.schedule()
+        st.events.publish(user.name, "library", {"renamed": exc.moved})
+        raise HTTPException(status_code=500, detail=str(exc)) from None
+    st.refresher.schedule()
+    st.events.publish(user.name, "library", {"renamed": result.moved})
+    return {"moved": result.moved, "merged": result.merged}
+
+
 @router.delete("/library/track", status_code=204)
 async def delete_track(request: Request, user: UserDep, body: TrackRef) -> Response:
     st = request.app.state
```

- [ ] **Step 4: Run the tests and see them pass**

Run: `uv run pytest -q`
Expected: all tests pass (157).

- [ ] **Step 5: Commit**

```bash
git add app/backend/wyc_music_streaming/rename.py \
  app/backend/wyc_music_streaming/paths.py \
  app/backend/wyc_music_streaming/library.py \
  app/backend/wyc_music_streaming/jobs.py \
  app/backend/wyc_music_streaming/api.py \
  app/backend/tests/test_rename.py \
  app/backend/tests/test_jobs.py \
  app/backend/tests/test_api.py
git commit -m "feat(backend): rename or merge an album or an artist"
```

### Task 5: Stages in the cassette deck

**Files:**
- Create: `app/frontend/src/lib/components/CassetteDeck.test.ts`
- Modify: `app/frontend/src/lib/types.ts`, `app/frontend/src/lib/testData.ts`, `app/frontend/src/lib/format.ts`, `app/frontend/src/lib/format.test.ts`, `app/frontend/src/app.css`, `app/frontend/src/lib/components/CassetteDeck.svelte`

**Interfaces:**
- Consumes: `Job.stage` from the backend (Task 1).
- Produces: `type JobStage = 'finding' | 'downloading' | 'processing'`; `Job.stage: JobStage | null`; `stageText(job: Job): string`; CSS class `.bar-stripes`.
- The deck bar gets `role="progressbar"` with `aria-valuetext`; `aria-valuenow` only while downloading.

- [ ] **Step 1: Write the failing tests**

Modify `app/frontend/src/lib/format.test.ts` (apply with `git apply` from the repo root, or edit by hand):

```diff
diff --git a/app/frontend/src/lib/format.test.ts b/app/frontend/src/lib/format.test.ts
index 46aa52a..d379b00 100644
--- a/app/frontend/src/lib/format.test.ts
+++ b/app/frontend/src/lib/format.test.ts
@@ -1,6 +1,7 @@
 import { describe, expect, it } from 'vitest';
 import { ApiError } from './api';
-import { errorText, formatDuration, percent } from './format';
+import { errorText, formatDuration, percent, stageText } from './format';
+import { makeJob } from './testData';
 
 describe('formatDuration', () => {
 	it.each([
@@ -37,3 +38,13 @@ describe('errorText', () => {
 		expect(errorText(new TypeError('Failed to fetch'))).toBe('ติดต่อเซิร์ฟเวอร์ไม่ได้');
 	});
 });
+
+describe('stageText', () => {
+	it('names each stage of a downloading job', () => {
+		const job = makeJob({ status: 'downloading', progress: 0.42 });
+		expect(stageText({ ...job, stage: 'finding' })).toBe('กำลังหาไฟล์…');
+		expect(stageText({ ...job, stage: null })).toBe('กำลังหาไฟล์…');
+		expect(stageText({ ...job, stage: 'downloading' })).toBe('กำลังโหลด 42%');
+		expect(stageText({ ...job, stage: 'processing' })).toBe('กำลังแปลงไฟล์…');
+	});
+});
```

Create `app/frontend/src/lib/components/CassetteDeck.test.ts`:

```ts
import { render, screen } from '@testing-library/svelte';
import { describe, expect, it } from 'vitest';
import { makeJob } from '../testData';
import CassetteDeck from './CassetteDeck.svelte';

function bar() {
	return screen.getByRole('progressbar');
}

describe('CassetteDeck', () => {
	it('is idle without a job', () => {
		render(CassetteDeck, { job: null });
		expect(screen.getByText('เครื่องว่าง เลือกเพลงเพื่อเริ่มอัด')).toBeInTheDocument();
		expect(screen.queryByRole('progressbar')).toBeNull();
	});

	it('shows a moving bar without a number while it looks for the file', () => {
		render(CassetteDeck, { job: makeJob({ status: 'downloading', stage: 'finding' }) });
		expect(screen.getByText('กำลังหาไฟล์…')).toBeInTheDocument();
		expect(bar()).not.toHaveAttribute('aria-valuenow');
		expect(bar().firstElementChild).toHaveClass('bar-stripes');
	});

	it('shows the percent while it downloads', () => {
		render(CassetteDeck, { job: makeJob({ status: 'downloading', stage: 'downloading', progress: 0.42 }) });
		expect(screen.getByText('กำลังโหลด 42%')).toBeInTheDocument();
		expect(bar()).toHaveAttribute('aria-valuenow', '42');
		expect(bar().firstElementChild).toHaveStyle({ width: '42%' });
		expect(bar().firstElementChild).not.toHaveClass('bar-stripes');
	});

	it('shows a full striped bar while it processes the file', () => {
		render(CassetteDeck, { job: makeJob({ status: 'downloading', stage: 'processing', progress: 1 }) });
		expect(screen.getByText('กำลังแปลงไฟล์…')).toBeInTheDocument();
		expect(bar().firstElementChild).toHaveClass('bar-stripes');
		expect(bar().firstElementChild).toHaveStyle({ width: '100%' });
	});
});
```

- [ ] **Step 2: Run the tests and see them fail**

Run: `npx vitest run src/lib/format.test.ts src/lib/components/CassetteDeck.test.ts`
Expected: `stageText` is not exported, and the deck tests fail with `Unable to find role="progressbar"`.

- [ ] **Step 3: Write the code**

Modify `app/frontend/src/lib/types.ts` (apply with `git apply` from the repo root, or edit by hand):

```diff
diff --git a/app/frontend/src/lib/types.ts b/app/frontend/src/lib/types.ts
index 3d1d82f..240f2b3 100644
--- a/app/frontend/src/lib/types.ts
+++ b/app/frontend/src/lib/types.ts
@@ -24,6 +24,9 @@ export type SearchResponse = {
 
 export type JobStatus = 'queued' | 'downloading' | 'done' | 'failed' | 'cancelled';
 
+/** Where a downloading job is: looking up the video, downloading bytes, or converting and tagging. */
+export type JobStage = 'finding' | 'downloading' | 'processing';
+
 export type Job = {
 	id: number;
 	user: string;
@@ -41,6 +44,7 @@ export type Job = {
 	final_path: string | null;
 	created_at: string;
 	updated_at: string;
+	stage: JobStage | null;
 };
 
 export type JobItem = {
```

Modify `app/frontend/src/lib/testData.ts` (apply with `git apply` from the repo root, or edit by hand):

```diff
diff --git a/app/frontend/src/lib/testData.ts b/app/frontend/src/lib/testData.ts
index 2273862..96cfd43 100644
--- a/app/frontend/src/lib/testData.ts
+++ b/app/frontend/src/lib/testData.ts
@@ -19,6 +19,7 @@ export function makeJob(overrides: Partial<Job> = {}): Job {
 		final_path: null,
 		created_at: '2026-11-06T15:00:00Z',
 		updated_at: '2026-11-06T15:00:00Z',
+		stage: null,
 		...overrides
 	};
 }
```

Modify `app/frontend/src/lib/format.ts` (apply with `git apply` from the repo root, or edit by hand):

```diff
diff --git a/app/frontend/src/lib/format.ts b/app/frontend/src/lib/format.ts
index cd5bdc5..638e543 100644
--- a/app/frontend/src/lib/format.ts
+++ b/app/frontend/src/lib/format.ts
@@ -1,5 +1,5 @@
 import { ApiError } from './api';
-import type { JobStatus } from './types';
+import type { Job, JobStatus } from './types';
 
 /** 187 → "3:07", 3725 → "1:02:05", null → "–:––". */
 export function formatDuration(seconds: number | null | undefined): string {
@@ -24,6 +24,13 @@ export const STATUS_LABEL: Record<JobStatus, string> = {
 	cancelled: 'ยกเลิกแล้ว'
 };
 
+/** The cassette deck line for a downloading job. No stage yet counts as "finding". */
+export function stageText(job: Job): string {
+	if (job.stage === 'downloading') return `กำลังโหลด ${percent(job.progress)}`;
+	if (job.stage === 'processing') return 'กำลังแปลงไฟล์…';
+	return 'กำลังหาไฟล์…';
+}
+
 /** One line of text for the UI from any error thrown by the API client. */
 export function errorText(error: unknown): string {
 	if (error instanceof ApiError) {
```

Modify `app/frontend/src/app.css` (apply with `git apply` from the repo root, or edit by hand):

```diff
diff --git a/app/frontend/src/app.css b/app/frontend/src/app.css
index c464d73..de656a5 100644
--- a/app/frontend/src/app.css
+++ b/app/frontend/src/app.css
@@ -51,4 +51,24 @@
 	.label {
 		@apply font-mono text-xs tracking-wide text-muted uppercase;
 	}
+	/* Progress without a number: diagonal stripes, moving unless the user asked for reduced motion. */
+	.bar-stripes {
+		background-image: repeating-linear-gradient(
+			-45deg,
+			var(--color-teal) 0 8px,
+			var(--color-yellow) 8px 16px
+		);
+		background-size: 22.6px 22.6px;
+	}
+	@media (prefers-reduced-motion: no-preference) {
+		.bar-stripes {
+			animation: bar-stripes 0.8s linear infinite;
+		}
+	}
+}
+
+@keyframes bar-stripes {
+	to {
+		background-position: 22.6px 0;
+	}
 }
```

Modify `app/frontend/src/lib/components/CassetteDeck.svelte` (apply with `git apply` from the repo root, or edit by hand):

```diff
diff --git a/app/frontend/src/lib/components/CassetteDeck.svelte b/app/frontend/src/lib/components/CassetteDeck.svelte
index 042b081..43ab73b 100644
--- a/app/frontend/src/lib/components/CassetteDeck.svelte
+++ b/app/frontend/src/lib/components/CassetteDeck.svelte
@@ -1,8 +1,12 @@
 <script lang="ts">
-	import { percent } from '$lib/format';
+	import { percent, stageText } from '$lib/format';
 	import type { Job } from '$lib/types';
 
 	let { job }: { job: Job | null } = $props();
+
+	// A number only while bytes arrive; before and after that the bar shows moving stripes.
+	const counting = $derived(job?.stage === 'downloading');
+	const width = $derived(!job ? '0%' : job.stage === 'downloading' ? percent(job.progress) : '100%');
 </script>
 
 <section class="card space-y-3 p-4" aria-label="เครื่องอัดเทป">
@@ -23,10 +27,18 @@
 			<p class="truncate font-semibold">{job.title}</p>
 			<p class="truncate text-sm text-muted">{job.artist}</p>
 		</div>
-		<div class="h-3 overflow-hidden rounded border-2 border-ink bg-ground">
-			<div class="h-full bg-teal transition-[width]" style:width={percent(job.progress)}></div>
+		<div
+			class="h-3 overflow-hidden rounded border-2 border-ink bg-ground"
+			role="progressbar"
+			aria-label="ความคืบหน้า"
+			aria-valuemin={0}
+			aria-valuemax={100}
+			aria-valuenow={counting ? Math.round(job.progress * 100) : undefined}
+			aria-valuetext={stageText(job)}
+		>
+			<div class={['h-full bg-teal transition-[width]', !counting && 'bar-stripes']} style:width={width}></div>
 		</div>
-		<p class="text-right font-mono text-xs">{percent(job.progress)}</p>
+		<p class="text-right font-mono text-xs">{stageText(job)}</p>
 	{:else}
 		<p class="text-sm text-muted">เครื่องว่าง เลือกเพลงเพื่อเริ่มอัด</p>
 	{/if}
```

- [ ] **Step 4: Run the tests and see them pass**

Run: `npx vitest run && npm run check`
Expected: all tests pass (102); svelte-check 0 errors 0 warnings.

- [ ] **Step 5: Commit**

```bash
git add app/frontend/src/lib/types.ts \
  app/frontend/src/lib/testData.ts \
  app/frontend/src/lib/format.ts \
  app/frontend/src/lib/format.test.ts \
  app/frontend/src/app.css \
  app/frontend/src/lib/components/CassetteDeck.svelte \
  app/frontend/src/lib/components/CassetteDeck.test.ts
git commit -m "feat(frontend): show download stages in the cassette deck"
```

### Task 6: Dialog when the queue empties

**Files:**
- Create: `app/frontend/src/lib/batch.ts`, `app/frontend/src/lib/batch.test.ts`, `app/frontend/src/lib/jobs.svelte.test.ts`, `app/frontend/src/lib/components/DoneDialog.svelte`, `app/frontend/src/lib/components/DoneDialog.test.ts`
- Modify: `app/frontend/src/lib/jobs.svelte.ts`, `app/frontend/vitest-setup.ts`, `app/frontend/src/routes/+layout.svelte`

**Interfaces:**
- Produces: `noteTransition(prev: Job | undefined, next: Job): 'done' | 'failed' | null`;
  `jobs.finished: Job[]`, `jobs.showDone: boolean`, `jobs.dismissDone()`; `<DoneDialog finished onclose />`.
- `jobs.load()` compares the old list with the new one, so jobs that ended while the event stream was down still count.

- [ ] **Step 1: Write the failing tests**

Create `app/frontend/src/lib/batch.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { noteTransition } from './batch';
import { makeJob } from './testData';

describe('noteTransition', () => {
	it.each([
		['queued', 'done', 'done'],
		['downloading', 'done', 'done'],
		['downloading', 'failed', 'failed'],
		['queued', 'failed', 'failed'],
		['queued', 'downloading', null],
		['done', 'done', null],
		['failed', 'queued', null],
		['queued', 'cancelled', null]
	] as const)('%s → %s gives %s', (before, after, expected) => {
		expect(noteTransition(makeJob({ status: before }), makeJob({ status: after }))).toBe(expected);
	});

	it('ignores a job it never saw active', () => {
		expect(noteTransition(undefined, makeJob({ status: 'done' }))).toBeNull();
	});
});
```

Create `app/frontend/src/lib/jobs.svelte.test.ts`:

```ts
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { makeJob } from './testData';

vi.mock('./client', () => ({ api: { listJobs: vi.fn() } }));

const { api } = await import('./client');
const { jobs } = await import('./jobs.svelte');

describe('jobs state', () => {
	beforeEach(() => {
		jobs.list = [];
		jobs.dismissDone();
	});

	it('collects jobs that end while the page is open and shows the dialog when the queue empties', () => {
		jobs.apply(makeJob({ id: 1, status: 'downloading' }));
		jobs.apply(makeJob({ id: 2, status: 'queued', video_id: 'bbbbbbbbbbb' }));
		jobs.apply(makeJob({ id: 1, status: 'done' }));
		expect(jobs.finished.map((j) => j.id)).toEqual([1]);
		expect(jobs.showDone).toBe(false); // job 2 still waits
		jobs.apply(makeJob({ id: 2, status: 'downloading', video_id: 'bbbbbbbbbbb' }));
		jobs.apply(makeJob({ id: 2, status: 'failed', video_id: 'bbbbbbbbbbb' }));
		expect(jobs.finished.map((j) => [j.id, j.status])).toEqual([
			[1, 'done'],
			[2, 'failed']
		]);
		expect(jobs.showDone).toBe(true);
		jobs.dismissDone();
		expect(jobs.finished).toEqual([]);
		expect(jobs.showDone).toBe(false);
	});

	it('does not count jobs that were already finished when the page opened', async () => {
		vi.mocked(api.listJobs).mockResolvedValue({ jobs: [makeJob({ id: 9, status: 'done' })] });
		await jobs.load();
		expect(jobs.finished).toEqual([]);
	});

	it('notices jobs that ended while the event stream was down', async () => {
		jobs.apply(makeJob({ id: 3, status: 'downloading' }));
		vi.mocked(api.listJobs).mockResolvedValue({ jobs: [makeJob({ id: 3, status: 'done' })] });
		await jobs.load();
		expect(jobs.finished.map((j) => j.id)).toEqual([3]);
		expect(jobs.showDone).toBe(true);
	});
});
```

Create `app/frontend/src/lib/components/DoneDialog.test.ts`:

```ts
import { fireEvent, render, screen } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import { makeJob } from '../testData';
import DoneDialog from './DoneDialog.svelte';

const done = [
	makeJob({ id: 1, status: 'done', title: 'Thriller', artist: 'MJ', album: 'Thriller' }),
	makeJob({ id: 2, status: 'done', title: 'Beat It', artist: 'MJ', album: 'Thriller' })
];
const failed = makeJob({ id: 3, status: 'failed', title: 'Bad', artist: 'MJ', album: 'Bad' });

describe('DoneDialog', () => {
	it('lists the finished tracks and focuses the close button', () => {
		render(DoneDialog, { finished: done, onclose: vi.fn() });
		const dialog = screen.getByRole('dialog', { name: 'อัดเทปเสร็จแล้ว 2 เพลง' });
		expect(dialog).toHaveAttribute('open');
		expect(screen.getByText('Thriller · MJ / Thriller')).toBeInTheDocument();
		expect(screen.getByText('Beat It · MJ / Thriller')).toBeInTheDocument();
		expect(screen.queryByText(/โหลดไม่ได้/)).toBeNull();
		expect(screen.getByRole('button', { name: 'ปิด' })).toHaveFocus();
	});

	it('lists failed tracks with a link to the queue', () => {
		render(DoneDialog, { finished: [...done, failed], onclose: vi.fn() });
		expect(screen.getByText('โหลดไม่ได้ 1 เพลง')).toBeInTheDocument();
		expect(screen.getByText('Bad · MJ / Bad')).toBeInTheDocument();
		expect(screen.getByRole('link', { name: 'ดูคิว' })).toHaveAttribute('href', '/queue');
	});

	it('names only failures when nothing finished well', () => {
		render(DoneDialog, { finished: [failed], onclose: vi.fn() });
		expect(screen.getByRole('dialog', { name: 'อัดเทปไม่สำเร็จ' })).toBeInTheDocument();
	});

	it('closes from the button, the library link and Escape', async () => {
		const onclose = vi.fn();
		render(DoneDialog, { finished: done, onclose });
		await fireEvent.click(screen.getByRole('button', { name: 'ปิด' }));
		await fireEvent.click(screen.getByRole('link', { name: 'เปิดคลังเพลง' }));
		await fireEvent(screen.getByRole('dialog'), new Event('cancel'));
		expect(onclose).toHaveBeenCalledTimes(3);
	});
});
```

- [ ] **Step 2: Run the tests and see them fail**

Run: `npx vitest run src/lib/batch.test.ts src/lib/jobs.svelte.test.ts src/lib/components/DoneDialog.test.ts`
Expected: `Failed to resolve import "./batch"` and `"./DoneDialog.svelte"`; the jobs state tests fail (`dismissDone is not a function`).

- [ ] **Step 3: Write the code**

Create `app/frontend/src/lib/batch.ts`:

```ts
import { isActive } from './jobList';
import type { Job } from './types';

/** 'done' or 'failed' when a job we saw active has just ended that way; otherwise null. */
export function noteTransition(prev: Job | undefined, next: Job): 'done' | 'failed' | null {
	if (!prev || !isActive(prev)) return null;
	return next.status === 'done' || next.status === 'failed' ? next.status : null;
}
```

Create `app/frontend/src/lib/jobs.svelte.ts`:

```ts
import { noteTransition } from './batch';
import { api } from './client';
import { isActive, sortJobs, upsertJob } from './jobList';
import type { Job } from './types';

class JobsState {
	list = $state<Job[]>([]);
	active = $derived(this.list.filter(isActive));
	current = $derived(this.list.find((j) => j.status === 'downloading') ?? null);
	queued = $derived(this.list.filter((j) => j.status === 'queued'));
	/** Jobs that ended (done or failed) while this page was open, since the last dialog. */
	finished = $state<Job[]>([]);
	/** Open the "done" dialog: something ended and nothing is left in the queue. */
	showDone = $derived(this.finished.length > 0 && this.active.length === 0);

	async load() {
		const before = new Map(this.list.map((j) => [j.id, j]));
		this.list = sortJobs((await api.listJobs()).jobs);
		for (const job of this.list) this.note(before.get(job.id), job);
	}

	apply(job: Job) {
		this.note(this.list.find((j) => j.id === job.id), job);
		this.list = upsertJob(this.list, job);
	}

	dismissDone() {
		this.finished = [];
	}

	private note(prev: Job | undefined, next: Job) {
		if (noteTransition(prev, next)) this.finished = [...this.finished.filter((j) => j.id !== next.id), next];
	}
}

export const jobs = new JobsState();
```

Create `app/frontend/src/lib/components/DoneDialog.svelte`:

```svelte
<script lang="ts">
	import type { Job } from '$lib/types';

	type Props = { finished: Job[]; onclose: () => void };
	let { finished, onclose }: Props = $props();

	let dialog = $state<HTMLDialogElement | null>(null);
	let closeButton = $state<HTMLButtonElement | null>(null);

	const done = $derived(finished.filter((j) => j.status === 'done'));
	const failed = $derived(finished.filter((j) => j.status === 'failed'));
	const title = $derived(done.length ? `อัดเทปเสร็จแล้ว ${done.length} เพลง` : 'อัดเทปไม่สำเร็จ');

	$effect(() => {
		if (!dialog || dialog.open) return;
		dialog.showModal();
		closeButton?.focus();
	});

	const line = (j: Job) => `${j.title} · ${j.artist} / ${j.album}`;
</script>

<dialog
	bind:this={dialog}
	aria-labelledby="done-title"
	class="card m-auto w-[min(32rem,calc(100vw-2rem))] p-0 backdrop:bg-ink/50"
	oncancel={(e) => {
		e.preventDefault();
		onclose();
	}}
>
	<div class="space-y-4 p-5">
		<h2 id="done-title" class="text-xl font-bold">{title}</h2>
		{#if done.length}
			<ul class="max-h-[50vh] space-y-1 overflow-auto">
				{#each done as job (job.id)}
					<li class="flex gap-2">
						<span aria-hidden="true" class="text-teal">✓</span>
						<span class="min-w-0 break-words">{line(job)}</span>
					</li>
				{/each}
			</ul>
		{/if}
		{#if failed.length}
			<div class="space-y-1 rounded-md border-2 border-orange p-3">
				<p class="font-semibold text-orange">โหลดไม่ได้ {failed.length} เพลง</p>
				<ul class="space-y-1">
					{#each failed as job (job.id)}
						<li class="flex gap-2">
							<span aria-hidden="true" class="text-orange">✗</span>
							<span class="min-w-0 break-words">{line(job)}</span>
						</li>
					{/each}
				</ul>
				<a href="/queue" class="text-sm text-teal underline" onclick={onclose}>ดูคิว</a>
			</div>
		{/if}
		<div class="flex flex-wrap justify-end gap-2">
			<a href="/library" class="btn btn-teal" onclick={onclose}>เปิดคลังเพลง</a>
			<button bind:this={closeButton} class="btn" onclick={onclose}>ปิด</button>
		</div>
	</div>
</dialog>
```

Modify `app/frontend/vitest-setup.ts` (apply with `git apply` from the repo root, or edit by hand):

```diff
diff --git a/app/frontend/vitest-setup.ts b/app/frontend/vitest-setup.ts
index bb02c60..c50a0a5 100644
--- a/app/frontend/vitest-setup.ts
+++ b/app/frontend/vitest-setup.ts
@@ -1 +1,11 @@
 import '@testing-library/jest-dom/vitest';
+
+// jsdom has no modal <dialog> API yet: enough of it for components that call showModal().
+if (typeof HTMLDialogElement !== 'undefined' && !HTMLDialogElement.prototype.showModal) {
+	HTMLDialogElement.prototype.showModal = function (this: HTMLDialogElement) {
+		this.open = true;
+	};
+	HTMLDialogElement.prototype.close = function (this: HTMLDialogElement) {
+		this.open = false;
+	};
+}
```

Modify `app/frontend/src/routes/+layout.svelte` (apply with `git apply` from the repo root, or edit by hand):

```diff
diff --git a/app/frontend/src/routes/+layout.svelte b/app/frontend/src/routes/+layout.svelte
index 61fab39..f9cc6f0 100644
--- a/app/frontend/src/routes/+layout.svelte
+++ b/app/frontend/src/routes/+layout.svelte
@@ -4,6 +4,7 @@
 	import { page } from '$app/state';
 	import { ApiError } from '$lib/api';
 	import { api } from '$lib/client';
+	import DoneDialog from '$lib/components/DoneDialog.svelte';
 	import Nav from '$lib/components/Nav.svelte';
 	import { connectEvents } from '$lib/events';
 	import { errorText } from '$lib/format';
@@ -75,4 +76,7 @@
 			<p class="text-muted">กำลังโหลด…</p>
 		{/if}
 	</main>
+	{#if jobs.showDone && !denied}
+		<DoneDialog finished={jobs.finished} onclose={() => jobs.dismissDone()} />
+	{/if}
 </div>
```

- [ ] **Step 4: Run the tests and see them pass**

Run: `npx vitest run && npm run check`
Expected: all tests pass (118); svelte-check 0 errors 0 warnings.

- [ ] **Step 5: Commit**

```bash
git add app/frontend/src/lib/batch.ts \
  app/frontend/src/lib/batch.test.ts \
  app/frontend/src/lib/jobs.svelte.ts \
  app/frontend/src/lib/jobs.svelte.test.ts \
  app/frontend/src/lib/components/DoneDialog.svelte \
  app/frontend/src/lib/components/DoneDialog.test.ts \
  app/frontend/vitest-setup.ts \
  app/frontend/src/routes/+layout.svelte
git commit -m "feat(frontend): show a dialog with finished tracks when the queue empties"
```

### Task 7: Rename from the library

**Files:**
- Create: `app/frontend/src/lib/components/RenameForm.svelte`, `app/frontend/src/lib/components/RenameForm.test.ts`
- Modify: `app/frontend/src/lib/types.ts`, `app/frontend/src/lib/api.ts`, `app/frontend/src/lib/api.test.ts`, `app/frontend/src/lib/components/AlbumGrid.svelte`, `app/frontend/src/lib/components/AlbumGrid.test.ts`, `app/frontend/src/routes/library/+page.svelte`

**Interfaces:**
- Consumes: `POST /api/library/rename` (Task 4), `Combobox` (plan 2.5).
- Produces: `type RenameBody`, `type RenameTarget = { name: string; tracks: number }`, `api.rename(body)`;
  `<RenameForm kind oldName existing onsubmit oncancel />` (sends the existing spelling on a merge);
  `AlbumGrid` props `onrename?(card, newName)` and `allCards?` (unfiltered cards for the merge list).

- [ ] **Step 1: Write the failing tests**

Create `app/frontend/src/lib/components/RenameForm.test.ts`:

```ts
import { fireEvent, render, screen } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import { ApiError } from '../api';
import RenameForm from './RenameForm.svelte';

const existing = [
	{ name: 'The Weeknd', tracks: 26 },
	{ name: 'MJ', tracks: 43 }
];

function setup(onsubmit = vi.fn().mockResolvedValue(undefined)) {
	const oncancel = vi.fn();
	render(RenameForm, { kind: 'artist', oldName: 'The Weeknd, JENNIE & Lily Rose Depp', existing, onsubmit, oncancel });
	return { onsubmit, oncancel, input: screen.getByLabelText('ชื่อศิลปินใหม่') as HTMLInputElement };
}

describe('RenameForm', () => {
	it('starts with the old name and blocks saving it unchanged', () => {
		const { input } = setup();
		expect(input.value).toBe('The Weeknd, JENNIE & Lily Rose Depp');
		expect(screen.getByRole('button', { name: 'บันทึก' })).toBeDisabled();
	});

	it('saves a new name', async () => {
		const { input, onsubmit } = setup();
		await fireEvent.input(input, { target: { value: '  The Weeknd & Friends ' } });
		await fireEvent.click(screen.getByRole('button', { name: 'บันทึก' }));
		expect(onsubmit).toHaveBeenCalledWith('The Weeknd & Friends');
	});

	it('warns before a merge and sends the existing spelling', async () => {
		const { input, onsubmit } = setup();
		await fireEvent.input(input, { target: { value: 'the weeknd' } });
		expect(screen.getByText('จะรวมกับ The Weeknd ที่มีอยู่แล้ว (26 เพลง)')).toBeInTheDocument();
		await fireEvent.click(screen.getByRole('button', { name: 'รวม' }));
		expect(onsubmit).toHaveBeenCalledWith('The Weeknd');
	});

	it('shows the server error and stays open', async () => {
		const onsubmit = vi.fn().mockRejectedValue(new ApiError(409, 'มีเพลงกำลังโหลดเข้าศิลปินนี้ รอคิวหมดก่อน'));
		const { input } = setup(onsubmit);
		await fireEvent.input(input, { target: { value: 'X' } });
		await fireEvent.click(screen.getByRole('button', { name: 'บันทึก' }));
		expect(await screen.findByRole('alert')).toHaveTextContent('มีเพลงกำลังโหลดเข้าศิลปินนี้ รอคิวหมดก่อน');
		expect(screen.getByRole('button', { name: 'บันทึก' })).toBeEnabled();
	});

	it('cancels', async () => {
		const { oncancel } = setup();
		await fireEvent.click(screen.getByRole('button', { name: 'ยกเลิก' }));
		expect(oncancel).toHaveBeenCalledOnce();
	});
});
```

Modify `app/frontend/src/lib/components/AlbumGrid.test.ts` (apply with `git apply` from the repo root, or edit by hand):

```diff
diff --git a/app/frontend/src/lib/components/AlbumGrid.test.ts b/app/frontend/src/lib/components/AlbumGrid.test.ts
index 9c13270..faa5b90 100644
--- a/app/frontend/src/lib/components/AlbumGrid.test.ts
+++ b/app/frontend/src/lib/components/AlbumGrid.test.ts
@@ -37,4 +37,24 @@ describe('AlbumGrid', () => {
 		await fireEvent.click(screen.getByRole('button', { name: 'ลบเลย' }));
 		expect(ondelete).toHaveBeenCalledWith('Sade/Diamond_Life/Smooth_Operator.m4a');
 	});
+
+	it('renames an album from its card and offers the other albums of that artist', async () => {
+		const onrename = vi.fn().mockResolvedValue(undefined);
+		render(AlbumGrid, { cards, ondelete: vi.fn(), onrename });
+		await fireEvent.click(screen.getByRole('button', { name: 'แก้ชื่ออัลบั้ม Meteora' }));
+		const input = screen.getByLabelText('ชื่ออัลบั้มใหม่') as HTMLInputElement;
+		expect(input.value).toBe('Meteora');
+		await fireEvent.focus(input);
+		expect(screen.getAllByRole('option').map((o) => o.textContent?.replace(/\s+/g, ' ').trim())).toEqual([
+			'Singles 1 เพลง'
+		]);
+		await fireEvent.input(input, { target: { value: 'Meteora (Live)' } });
+		await fireEvent.click(screen.getByRole('button', { name: 'บันทึก' }));
+		expect(onrename).toHaveBeenCalledWith(cards[1], 'Meteora (Live)');
+	});
+
+	it('has no rename button without onrename', () => {
+		render(AlbumGrid, { cards, ondelete: vi.fn() });
+		expect(screen.queryByRole('button', { name: /แก้ชื่อ/ })).toBeNull();
+	});
 });
```

Modify `app/frontend/src/lib/api.test.ts` (apply with `git apply` from the repo root, or edit by hand):

```diff
diff --git a/app/frontend/src/lib/api.test.ts b/app/frontend/src/lib/api.test.ts
index e15f864..4181e29 100644
--- a/app/frontend/src/lib/api.test.ts
+++ b/app/frontend/src/lib/api.test.ts
@@ -66,4 +66,13 @@ describe('createApi', () => {
 		const err = await createApi(fn).retryJob(1).catch((e) => e);
 		expect(err.message).toBe('only a failed job can be retried');
 	});
+
+	it('posts a rename', async () => {
+		const { fn, calls } = fakeFetch(200, { moved: 2, merged: true });
+		const body = { kind: 'artist' as const, artist: 'linkinpark', new_name: 'Linkin Park' };
+		const out = await createApi(fn).rename(body);
+		expect(calls[0].url).toBe('/api/library/rename');
+		expect(JSON.parse(String(calls[0].init?.body))).toEqual(body);
+		expect(out).toEqual({ moved: 2, merged: true });
+	});
 });
```

- [ ] **Step 2: Run the tests and see them fail**

Run: `npx vitest run src/lib/components src/lib/api.test.ts`
Expected: `Failed to resolve import "./RenameForm.svelte"`; the AlbumGrid rename test cannot find the button; `rename is not a function`.

- [ ] **Step 3: Write the code**

Modify `app/frontend/src/lib/types.ts` (apply with `git apply` from the repo root, or edit by hand):

```diff
diff --git a/app/frontend/src/lib/types.ts b/app/frontend/src/lib/types.ts
index 240f2b3..9468dbf 100644
--- a/app/frontend/src/lib/types.ts
+++ b/app/frontend/src/lib/types.ts
@@ -78,5 +78,11 @@ export type LibraryAlbum = { album: string; tracks: LibraryTrack[] };
 
 export type LibraryArtist = { artist: string; albums: LibraryAlbum[] };
 
+/** POST /api/library/rename. album is needed only for kind "album". */
+export type RenameBody = { kind: 'album' | 'artist'; artist: string; album?: string; new_name: string };
+
+/** An existing artist or album that a rename can merge into. */
+export type RenameTarget = { name: string; tracks: number };
+
 /** One row of a Combobox popup. */
 export type ComboOption = { value: string; label: string; hint?: string };
```

Modify `app/frontend/src/lib/api.ts` (apply with `git apply` from the repo root, or edit by hand):

```diff
diff --git a/app/frontend/src/lib/api.ts b/app/frontend/src/lib/api.ts
index e554848..41cdac7 100644
--- a/app/frontend/src/lib/api.ts
+++ b/app/frontend/src/lib/api.ts
@@ -4,6 +4,7 @@ import type {
 	JobItem,
 	LibraryArtist,
 	Me,
+	RenameBody,
 	SearchResponse
 } from './types';
 
@@ -63,6 +64,7 @@ export function createApi(
 		library: () => request<{ artists: LibraryArtist[] }>('GET', '/library'),
 		rescanLibrary: () => request<{ tracks: number }>('POST', '/library/rescan'),
 		deleteTrack: (path: string) => request<void>('DELETE', '/library/track', { path }),
+		rename: (body: RenameBody) => request<{ moved: number; merged: boolean }>('POST', '/library/rename', body),
 		refreshJellyfin: () => request<{ ok: boolean }>('POST', '/jellyfin/refresh')
 	};
 }
```

Create `app/frontend/src/lib/components/RenameForm.svelte`:

```svelte
<script lang="ts">
	import { errorText } from '$lib/format';
	import type { RenameTarget } from '$lib/types';
	import Combobox from './Combobox.svelte';

	type Props = {
		kind: 'album' | 'artist';
		oldName: string;
		/** Other artists (or other albums of the same artist) the new name may merge into. */
		existing: RenameTarget[];
		/** Resolves when the rename is done; a rejection shows its message. */
		onsubmit: (newName: string) => Promise<void>;
		oncancel: () => void;
	};
	let { kind, oldName, existing, onsubmit, oncancel }: Props = $props();

	// Writable derived: it resets when the parent passes another oldName.
	let name = $derived(oldName);
	let busy = $state(false);
	let error = $state<string | null>(null);

	const fold = (s: string) => s.trim().toLowerCase();
	const options = $derived(existing.map((e) => ({ value: e.name, label: e.name, hint: `${e.tracks} เพลง` })));
	const mergeInto = $derived(
		fold(name) === fold(oldName) ? undefined : existing.find((e) => fold(e.name) === fold(name))
	);
	const unchanged = $derived(!name.trim() || name.trim() === oldName);

	async function submit(event: SubmitEvent) {
		event.preventDefault();
		if (unchanged || busy) return;
		busy = true;
		error = null;
		try {
			await onsubmit(mergeInto ? mergeInto.name : name.trim());
		} catch (e) {
			error = errorText(e);
		} finally {
			busy = false;
		}
	}
</script>

<form class="space-y-2" onsubmit={submit}>
	<Combobox
		bind:value={name}
		{options}
		label={kind === 'album' ? 'ชื่ออัลบั้มใหม่' : 'ชื่อศิลปินใหม่'}
		maxlength={300}
		filter
	/>
	{#if mergeInto}
		<p class="text-sm">จะรวมกับ {mergeInto.name} ที่มีอยู่แล้ว ({mergeInto.tracks} เพลง)</p>
	{/if}
	{#if error}
		<p role="alert" class="text-sm text-orange">{error}</p>
	{/if}
	<div class="flex flex-wrap gap-2">
		<button class="btn btn-primary" type="submit" disabled={unchanged || busy}>
			{busy ? 'กำลังย้าย…' : mergeInto ? 'รวม' : 'บันทึก'}
		</button>
		<button class="btn" type="button" onclick={oncancel} disabled={busy}>ยกเลิก</button>
	</div>
</form>
```

Create `app/frontend/src/lib/components/AlbumGrid.svelte`:

```svelte
<script lang="ts">
	import type { AlbumCard } from '$lib/albumList';
	import RenameForm from './RenameForm.svelte';
	import TrackRow from './TrackRow.svelte';

	type Props = {
		cards: AlbumCard[];
		ondelete: (path: string) => Promise<void> | void;
		/** When set, each card gets a rename button. */
		onrename?: (card: AlbumCard, newName: string) => Promise<void>;
		/** Every album card (unfiltered), for the merge list. Defaults to cards. */
		allCards?: AlbumCard[];
	};
	let { cards, ondelete, onrename, allCards }: Props = $props();

	let open = $state<string | null>(null);
	let editing = $state<string | null>(null);

	function otherAlbums(card: AlbumCard) {
		return (allCards ?? cards)
			.filter((c) => c.artist === card.artist && c.key !== card.key)
			.map((c) => ({ name: c.album, tracks: c.tracks.length }));
	}
</script>

<ul class="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
	{#each cards as card, i (card.key)}
		{@const isOpen = open === card.key}
		{@const isEditing = editing === card.key}
		<li class={['card', (isOpen || isEditing) && 'sm:col-span-2 xl:col-span-3']}>
			<div class="flex items-center gap-2 pr-3">
				<button
					class="flex min-w-0 flex-1 items-center gap-3 p-4 text-left"
					aria-expanded={isOpen}
					aria-controls={`album-${i}`}
					onclick={() => (open = isOpen ? null : card.key)}
				>
					<span
						aria-hidden="true"
						class="grid size-12 shrink-0 place-items-center rounded border-2 border-ink bg-yellow font-mono text-lg"
					>
						{card.album.slice(0, 1).toUpperCase()}
					</span>
					<span class="min-w-0">
						<span class="block truncate font-semibold">{card.album}</span>
						<span class="block truncate text-sm text-muted">{card.artist}</span>
						<span class="font-mono text-xs text-muted">{card.tracks.length} เพลง</span>
					</span>
				</button>
				{#if onrename && !isEditing}
					<button class="btn shrink-0" aria-label={`แก้ชื่ออัลบั้ม ${card.album}`} onclick={() => (editing = card.key)}>
						แก้ชื่อ
					</button>
				{/if}
			</div>
			{#if onrename && isEditing}
				<div class="border-t-2 border-ink p-4">
					<RenameForm
						kind="album"
						oldName={card.album}
						existing={otherAlbums(card)}
						onsubmit={async (name) => {
							await onrename(card, name);
							editing = null;
						}}
						oncancel={() => (editing = null)}
					/>
				</div>
			{/if}
			{#if isOpen}
				<ul id={`album-${i}`} class="border-t-2 border-ink px-4 pb-2">
					{#each card.tracks as track (track.path)}
						<TrackRow {track} {ondelete} />
					{/each}
				</ul>
			{/if}
		</li>
	{/each}
</ul>
```

Modify `app/frontend/src/routes/library/+page.svelte` (apply with `git apply` from the repo root, or edit by hand):

```diff
diff --git a/app/frontend/src/routes/library/+page.svelte b/app/frontend/src/routes/library/+page.svelte
index e3d25f9..ab3cb3f 100644
--- a/app/frontend/src/routes/library/+page.svelte
+++ b/app/frontend/src/routes/library/+page.svelte
@@ -1,12 +1,14 @@
 <script lang="ts">
 	import { page } from '$app/state';
-	import { albumList } from '$lib/albumList';
+	import { albumList, type AlbumCard } from '$lib/albumList';
 	import { api } from '$lib/client';
 	import AlbumGrid from '$lib/components/AlbumGrid.svelte';
+	import RenameForm from '$lib/components/RenameForm.svelte';
 	import TrackRow from '$lib/components/TrackRow.svelte';
 	import { errorText } from '$lib/format';
 	import { library } from '$lib/library.svelte';
 	import { filterLibrary } from '$lib/libraryFilter';
+	import type { RenameBody } from '$lib/types';
 
 	let filter = $state('');
 	let busy = $state<'rescan' | 'jellyfin' | null>(null);
@@ -21,6 +23,23 @@
 
 	const shown = $derived(filterLibrary(library.artists, filter));
 	const cards = $derived(view === 'albums' ? albumList(shown) : []);
+	const allCards = $derived(view === 'albums' ? albumList(library.artists) : []);
+
+	let editingArtist = $state<string | null>(null);
+	const artistCounts = $derived(
+		library.artists.map((a) => ({ name: a.artist, tracks: a.albums.reduce((n, al) => n + al.tracks.length, 0) }))
+	);
+
+	/** Rename on the server, reload the library, and say what happened. Errors go back to the form. */
+	async function rename(body: RenameBody) {
+		const { moved, merged } = await api.rename(body);
+		await library.load();
+		error = null;
+		notice = merged ? `รวมแล้ว ${moved} เพลง` : `เปลี่ยนชื่อแล้ว ${moved} เพลง`;
+	}
+
+	const renameAlbum = (card: AlbumCard, name: string) =>
+		rename({ kind: 'album', artist: card.artist, album: card.album, new_name: name });
 
 	async function remove(path: string) {
 		await api.deleteTrack(path);
@@ -81,7 +100,7 @@
 	{:else if shown.length === 0}
 		<p class="text-muted">{filter.trim() ? 'ไม่พบเพลงที่ตรงกับคำค้น' : 'คลังยังว่าง ลองโหลดเพลงจากหน้าค้นหา'}</p>
 	{:else if view === 'albums'}
-		<AlbumGrid {cards} ondelete={remove} />
+		<AlbumGrid {cards} {allCards} ondelete={remove} onrename={renameAlbum} />
 	{:else}
 		<div class="grid gap-6 md:grid-cols-[200px_1fr]">
 			<nav class="hidden md:block" aria-label="ศิลปิน">
@@ -94,7 +113,32 @@
 			<div class="min-w-0 space-y-8">
 				{#each shown as artist, i (artist.artist)}
 					<section id={`artist-${i}`} class="space-y-3">
-						<h2 class="text-xl font-bold">{artist.artist}</h2>
+						<div class="flex flex-wrap items-center gap-2">
+							<h2 class="min-w-0 text-xl font-bold break-words">{artist.artist}</h2>
+							{#if editingArtist !== artist.artist}
+								<button
+									class="btn"
+									aria-label={`แก้ชื่อศิลปิน ${artist.artist}`}
+									onclick={() => (editingArtist = artist.artist)}
+								>
+									แก้ชื่อ
+								</button>
+							{/if}
+						</div>
+						{#if editingArtist === artist.artist}
+							<div class="card p-4">
+								<RenameForm
+									kind="artist"
+									oldName={artist.artist}
+									existing={artistCounts.filter((a) => a.name !== artist.artist)}
+									onsubmit={async (name) => {
+										await rename({ kind: 'artist', artist: artist.artist, new_name: name });
+										editingArtist = null;
+									}}
+									oncancel={() => (editingArtist = null)}
+								/>
+							</div>
+						{/if}
 						{#each artist.albums as album (album.album)}
 							<article class="card p-4">
 								<h3 class="font-semibold">
```

- [ ] **Step 4: Run the tests and see them pass**

Run: `npx vitest run && npm run check && npm run build`
Expected: 126 tests pass; svelte-check 0 errors 0 warnings; build writes `build/`.

- [ ] **Step 5: Commit**

```bash
git add app/frontend/src/lib/types.ts \
  app/frontend/src/lib/api.ts \
  app/frontend/src/lib/api.test.ts \
  app/frontend/src/lib/components/RenameForm.svelte \
  app/frontend/src/lib/components/RenameForm.test.ts \
  app/frontend/src/lib/components/AlbumGrid.svelte \
  app/frontend/src/lib/components/AlbumGrid.test.ts \
  app/frontend/src/routes/library/+page.svelte
git commit -m "feat(frontend): rename or merge albums and artists from the library"
```

### Task 8: Deploy on the NAS and smoke test

The user runs these steps on the NAS (as `wick`). Push first, with the user's OK.

- [ ] **Step 1: Update and rebuild**

```bash
sudo /opt/wyc-music-streaming/repo/app/deploy/update.sh 2>&1 | tail -20
```

Expected: `Wrote site to "build"` and `active (running)`. The first start adds the `stage` column to the existing `app.db`.

- [ ] **Step 2: Smoke test from the phone and the laptop** (`https://wick-vpccw15fh.tail4810aa.ts.net/`)

1. Download 2–3 tracks: the deck shows "กำลังหาไฟล์…" (stripes), then "กำลังโหลด n%", then "กำลังแปลงไฟล์…".
2. When the queue empties, the dialog lists the finished tracks; "ปิด" and Esc close it; "เปิดคลังเพลง" opens the library.
3. Album view: "แก้ชื่อ" on "Off_the_Wall" → "Off the Wall": the card shows the new name; Jellyfin shows it after its scan.
4. Artist view: rename "linkinpark" → "Linkin Park"; rename "The Weeknd, JENNIE & Lily Rose Depp" → "the weeknd": the form says it will merge into "The Weeknd", the button says "รวม", and the tracks end up under "The Weeknd".
5. Start a download and try to rename its artist while it waits: the form shows "มีเพลงกำลังโหลดเข้าศิลปินนี้ รอคิวหมดก่อน".

- [ ] **Step 3: Record the result**

Mark base spec §11 item 11 as fixed (with the date), add a "Deploy result" section to the addendum, then:

```bash
git add docs/superpowers/specs/2026-11-05-wyc-music-streaming-design.md docs/superpowers/specs/2026-11-07-rename-and-download-feedback-design.md
git commit -m "docs(spec): record rename and download feedback on the NAS"
```

## Spec coverage

| Spec section | Task |
|---|---|
| §3.1 rename API | 4 |
| §3.2 per-track steps (retag, move, prune, rescan) | 3, 4 |
| §3.3 rename UI | 7 |
| §4 dialog when the queue empties | 6 |
| §5.1 stages, throttle | 1, 2 |
| §5.2 deck | 5 |
| §6 tests | every task |
