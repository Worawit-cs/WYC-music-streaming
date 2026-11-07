# WYC-music-streaming: rename and download feedback (design addendum)

Date: 2026-11-07
Base spec: `docs/superpowers/specs/2026-11-05-wyc-music-streaming-design.md`
Previous addendum: `docs/superpowers/specs/2026-11-07-search-library-polish-design.md`
Status: approved in chat, before plan

## 1. Problems seen in real use

1. Album and artist names cannot be changed after download. Real examples:
   "linkinpark" (should be "Linkin Park"), an album shown as "Off_the_Wall" (a file without
   an album tag, so the folder name shows), and "The Weeknd, JENNIE & Lily Rose Depp" as its own artist.
2. When the queue finishes there is no clear "done" moment and no list of what finished.
3. The progress bar stays near 0 % (base spec §11 item 11): the 1 s throttle drops every
   update after the first, and nothing is sent during extraction or post-processing.

## 2. Scope

| Part | What | Backend change |
|---|---|---|
| A | Rename an album or an artist; a new name that already exists merges | `POST /api/library/rename` |
| B | A dialog when the queue empties, listing what finished and what failed | none |
| C | Progress with stages: finding, downloading, processing | `jobs.stage` column, worker hooks |

Out of scope: renaming one track, moving one album to another artist, undo.

## 3. Part A: rename

### 3.1 API

`POST /api/library/rename`, body:

```json
{"kind": "album", "artist": "MJ", "album": "Off_the_Wall", "new_name": "Off The Wall"}
{"kind": "artist", "artist": "linkinpark", "new_name": "Linkin Park"}
```

- `kind`: `"album"` or `"artist"`. `album` is required for `"album"` and ignored for `"artist"`.
- `artist`, `album` are the names the library shows (`/api/library` tree), matched exactly.
- `new_name`: 1..300 chars after trim.
- Response 200: `{"moved": <n>, "merged": <bool>}`. `merged` is true when the target
  (artist, or artist + album) already had tracks before the rename.
- 400: blank `new_name`, or `new_name` equal to the old name.
- 404: no track matches.
- 409: a `queued` or `downloading` job of this user has the same artist (and album, for `"album"`).
  Detail: "มีเพลงกำลังโหลดเข้า<ศิลปิน|อัลบั้ม>นี้ รอคิวหมดก่อน".

### 3.2 What happens per track

For every library track of the user that matches (artist, and album for `"album"`):

1. Write tags with mutagen's easy interface (`mutagen.File(path, easy=True)`), which covers
   .m4a, .opus/.ogg, .mp3 and .flac:
   - `"album"`: set `album` to `new_name`.
   - `"artist"`: set `albumartist` to `new_name`; set `artist` to `new_name` only when the
     old `artist` tag equals the old name (keeps "X feat. Y" track artists).
   - Title, track number, year, cover and the `youtube:` comment stay as they are.
2. Move the file to `music_dir/<sanitize(artist)>/<sanitize(album)>/<same file name>`,
   using `unique_path` (a clash gets `_(2)`). Paths go through `safe_resolve`.
3. Remove old folders that became empty (same loop as delete).

After the loop: rescan the user's library, schedule a Jellyfin refresh, publish a `library` event.
If a track fails midway, the error is returned (500 with "ย้ายแล้ว <n> เพลง ก่อนเกิดปัญหา: <error>");
the rescan still runs, so the library shows the real state.

Jellyfin sees moved files as new items (play counts reset). Boxes (plan 3) do not exist yet.

### 3.3 Frontend

- `RenameForm.svelte`: a `Combobox` (filter, no create row) prefilled with the old name,
  options = existing names to merge into (artists for `"artist"`, albums of that artist for `"album"`).
  When the typed name matches an existing name (case-insensitive) other than the old one,
  it shows "จะรวมกับ <name> ที่มีอยู่แล้ว (<n> เพลง)" and the button reads "รวม".
  Buttons: "บันทึก" / "รวม", "ยกเลิก". Errors show under the field.
- Album view: each card gets a "แก้ชื่อ" button; the form opens inside the card.
- Artist view: each artist heading gets a "แก้ชื่อ" button; the form opens under the heading.
- After success: `library.load()`, close the form, show a notice "เปลี่ยนชื่อแล้ว <n> เพลง".
- `api.rename(body)` in `lib/api.ts`.

## 4. Part B: dialog when the queue empties

- `jobs.svelte.ts` keeps `finished: Job[]` for this page session: a job goes in when an
  event moves it from `queued`/`downloading` to `done` or `failed`.
  (Jobs that end while the page is closed are not shown; the queue page still lists them.)
- When `finished` is not empty and there is no `queued`/`downloading` job, the layout opens
  `DoneDialog.svelte` (`<dialog>` with `showModal()`, Esc closes, focus on "ปิด").
- Content:
  - Title "อัดเทปเสร็จแล้ว <n> เพลง" (n = done count).
  - Done rows: "✓ <title> · <artist> / <album>".
  - When some failed: "โหลดไม่ได้ <m> เพลง" with their titles and a link "ดูคิว" (`/queue`).
  - Buttons: "เปิดคลังเพลง" (`/library`) and "ปิด".
- Closing clears `finished`.
- Pure helper `lib/batch.ts`: `noteTransition(prev: Job | undefined, next: Job): 'done' | 'failed' | null`.

## 5. Part C: progress with stages

### 5.1 Backend

- `jobs` table: new column `stage TEXT` (NULL, or `finding` / `downloading` / `processing`).
  `JobStore.__init__` adds it with `ALTER TABLE jobs ADD COLUMN stage TEXT` when missing
  (old databases on the NAS). `Job` gains `stage: str | None`.
- Worker: when it claims a job, stage = `finding`, progress 0.
- `ytdlp_download(job, tmp_dir, on_progress, on_stage)`:
  - first `downloading` hook call: `on_stage("downloading")`;
  - `finished` hook: `on_progress(1.0)` then `on_stage("processing")`;
  - `postprocessor_hooks` `started`: `on_stage("processing")` (repeat calls are ignored).
- The worker's throttle (`PROGRESS_INTERVAL = 1.0`) applies only to fractions below 1.0.
  A fraction of 1.0 and every stage change are always sent.
- The `Downloader` type gains the `on_stage` argument; test fakes call it.

### 5.2 Frontend

- `Job.stage` in `types.ts`.
- `CassetteDeck.svelte`, for the current job:
  - `finding`: "กำลังหาไฟล์…" and an indeterminate bar (striped; the stripes move only when the user has not asked for reduced motion).
  - `downloading`: "กำลังโหลด <n>%" and the normal bar.
  - `processing`: "กำลังแปลงไฟล์…" and a full bar with the stripes.
- Pure helper `stageText(job)` in `lib/format.ts`.

## 6. Tests

Backend (pytest):

- rename album: tags rewritten, files moved, old folder removed, `moved` count.
- rename artist: `albumartist` set; `artist` changed only when it equaled the old name.
- merge into an existing album / artist: `merged: true`; a file name clash gets `_(2)`.
- 409 with an active job; 404 for no match; 400 for blank or same name; 422 for a bad body;
  a crafted name cannot escape `music_dir` (names go through `sanitize_name`, so `..` becomes `Unknown` and `/` is removed).
- tags: easy-interface write for .m4a and .opus keeps title and cover.
- jobs: an old database without `stage` gets the column; `set_stage` round trip.
- worker: stage order `finding` → `downloading` → `processing` → done; the 1.0 progress is
  sent even inside the throttle window.

Frontend (vitest):

- `noteTransition`: queued→done, downloading→failed, done→done (null), unknown prev.
- jobs state: `finished` fills from events; `showDone` when the queue empties.
- `DoneDialog`: counts, done rows, failed section and link, close clears.
- `RenameForm`: merge notice and button text, submit payload, error text.
- `stageText` and the deck labels.

## 7. Files

Backend:
- Create: `wyc_music_streaming/rename.py` (rename logic), `tests/test_rename.py`
- Modify: `tags.py` (`retag`), `jobs.py` (`stage`), `worker.py` (stages, throttle), `api.py` (route),
  tests for each

Frontend:
- Create: `lib/batch.ts`, `lib/components/RenameForm.svelte`, `lib/components/DoneDialog.svelte`
  (each with a test file)
- Modify: `lib/types.ts`, `lib/api.ts`, `lib/format.ts`, `lib/jobs.svelte.ts`,
  `lib/components/CassetteDeck.svelte`, `lib/components/AlbumGrid.svelte`,
  `routes/+layout.svelte`, `routes/library/+page.svelte`, and their tests
