# WYC-music-streaming — Design Spec

- Date: 2026-11-05
- Status: Draft, waiting for review
- UI design: https://claude.ai/artifact/ATcFxXTMnsSj8fzmCudor9 (direction C · Cassette)

## 1. Goal

Build a web app on the home NAS. The app lets each user:

1. Search YouTube by keyword, or paste a song / playlist URL.
2. Edit the title, artist, and album before download.
3. Download the audio into **their own** music folder on the NAS.
4. View their library (artist → album → track) and delete tracks.
5. Make Jellyfin see new tracks at once (automatic library refresh).
6. Make "boxes" (กล่องเพลง). A box is a Jellyfin playlist. The user adds tracks to a box by search, by link, or from the library.
7. Download a whole album with one search: pick the album, untick unwanted tracks, download.

### Out of scope (this version)

- Streaming / an audio player in the web app (possible phase 2)
- OIDC / SSO with an external IdP (the auth module is pluggable, so this can come later)
- Transcoding audio
- A mobile app (use the web app on mobile)
- Download sources other than YouTube / YouTube Music

Copyright: downloaded content is the user's responsibility. The system is for personal use only.

## 2. Constraints from the hardware

| Item | Value | Effect on the design |
|---|---|---|
| CPU | Core2 Duo T6600 (2 cores, 2.2 GHz) | Never transcode. Remux and tag only. Max 2 concurrent downloads. |
| RAM | 5.75 GiB (about 720 MiB in use) | Enough. Do not add heavy services. |
| OS | Ubuntu 20.04 (system Python 3.8) | Use `uv` to install Python 3.12 into `/opt/wyc-music-streaming`. Do not touch system Python. |
| Disk | HDD 298 GiB, one partition `/` (35 GiB used) | Download to a temp folder on the same filesystem, then `rename` (atomic). |
| Network | WiFi (`wlp3s0`); Ethernet is down | Recommend a LAN cable. The app works on WiFi too. |

## 3. Architecture

```
Browser (any device in the tailnet)
   │  https://<nas>.<tailnet>.ts.net
   ▼
tailscale serve  ── adds header Tailscale-User-Login
   │  http://127.0.0.1:8097
   ▼
FastAPI (WYC-music-streaming, systemd)
   ├─ serves static SvelteKit build  (/)
   ├─ /api/me         user from header → config
   ├─ /api/search     yt-dlp search / URL info
   ├─ /api/albums     ytmusicapi album search + tracklist
   ├─ /api/jobs       queue in SQLite, 2 workers
   ├─ /api/events     SSE progress per user
   ├─ /api/library    scan folder + mutagen tags
   └─ /api/boxes      Jellyfin playlists of this user
        │ writes files
        ▼
/home/wick/share/<user>/music/<Artist>/<Album>/<NN_Title>.m4a
        │
        ▼
Jellyfin  POST /Library/Refresh  (API key, debounced)
          /Playlists/...         (boxes)
```

### Names

| Where | Name |
|---|---|
| GitHub repo, page title, UI | `WYC-music-streaming` |
| systemd unit, system user, `/etc`, `/var/lib`, `/opt` | `wyc-music-streaming` (Linux names must be lowercase) |
| Python package | `wyc_music_streaming` (Python names cannot contain `-`) |
| Env var | `WYC_MUSIC_STREAMING_CONFIG` |
| App folder in the repo | `app/` (the repo also holds the NAS docs) |

### Repo layout

```
app/
  backend/
    pyproject.toml
    wyc_music_streaming/
      main.py          FastAPI app, mounts static + routers
      config.py        load and validate config.toml
      auth.py          resolve user from request (Tailscale header / dev mode)
      paths.py         safe path joining under the user's music_dir
      search.py        yt-dlp search + URL/playlist info
      albums.py        ytmusicapi album search + get_album
      metadata.py      clean YouTube titles → title/artist/album
      jobs.py          SQLite job store
      worker.py        download workers (yt-dlp → tag → move)
      library.py       scan tree, in-memory index, delete
      jellyfin.py      HTTP client: refresh (debounced), users, items, playlists
      boxes.py         box logic: ownership check, add/remove, pending poller
      events.py        SSE broadcast per user
    tests/
  frontend/
    package.json
    svelte.config.js   adapter-static, SPA fallback index.html
    src/routes/        +layout, search, boxes, boxes/[id], library, queue, denied
  deploy/
    wyc-music-streaming.service
    wyc-music-streaming-update-ytdlp.service
    wyc-music-streaming-update-ytdlp.timer
    config.example.toml
    update.sh
```

## 4. Auth: Tailscale identity

- `tailscale serve --bg --https=443 http://127.0.0.1:8097` proxies traffic from the tailnet and adds these headers:
  - `Tailscale-User-Login` (for example `wick@gmail.com`)
  - `Tailscale-User-Name`
- WYC-music-streaming reads `Tailscale-User-Login` and maps it to a user in config.
  - Login not in config → `403` and the "no access" page. The page shows the login and a config snippet for the admin.
  - No header → `403`. The request did not come through `tailscale serve`.
- **Trust model:** the header is trustworthy only if nobody can reach WYC-music-streaming directly.
  - The backend **must** bind `127.0.0.1` only. At startup, refuse a non-loopback `host` unless `[server] dev = true`.
  - Do not open port 8097 in UFW.
- **No session or cookie.** Each request resolves the user from the header again. There is nothing to log out from.
- **Dev mode:** `[server] dev = true` with `dev_user = "wick"` uses that user when the header is missing. The startup log prints a warning. Use this mode only on the dev machine.
- **Interface:** `auth.py` exposes `resolve_user(request) -> User | None`. A future `oidc` mode adds a new implementation of this function. Routers do not change.
- **Consequence:** the app is reachable only through Tailscale. Users at home also use the `ts.net` URL. Each user needs a Tailscale account in the tailnet.

## 5. Config

`/etc/wyc-music-streaming/config.toml` is not in git. The repo has only `deploy/config.example.toml`.

```toml
[server]
host = "127.0.0.1"
port = 8097
data_dir = "/var/lib/wyc-music-streaming"      # app.db, tmp/
dev = false
# dev_user = "wick"

[jellyfin]
url = "http://127.0.0.1:8096"
api_key_file = "/etc/wyc-music-streaming/jellyfin.key"   # chmod 640 root:wick

[download]
concurrency = 2

[users.wick]
tailscale_login = "wick@gmail.com"
music_dir = "/home/wick/share/wick/music"
jellyfin_user = "wick"          # Jellyfin user name that owns this user's boxes

[users.safeena]
tailscale_login = "safeena@gmail.com"
music_dir = "/home/wick/share/safeena/music"
jellyfin_user = "safeena"
```

Startup validation fails fast with a clear message when:

- a `music_dir` does not exist or is not writable
- a `tailscale_login` is duplicated
- the API key file is missing

`jellyfin_user` is optional. Without it, the boxes pages show "boxes are off for this user". The app resolves the name to a Jellyfin user id with `GET /Users` on first use, not at startup, so a Jellyfin outage never blocks startup.

## 6. Backend behavior

### 6.1 Search (`GET /api/search?q=`)

- If `q` is a URL: call `extract_info(url, download=False, process=False)`.
  - Single video → 1 result.
  - Playlist → its entries (`extract_flat`), up to 200.
  - YouTube Music album link (`list=OLAK5uy_...`) → return `{album_browse_id}` instead. The UI opens the album view (§6.8), so the tracks get real album tags.
- Otherwise: `ytsearch10:<q>` with `extract_flat`.
- Each result has `video_id`, `title`, `channel`, `duration`, `thumbnail_url`, and `suggested` (the output of `metadata.clean`).
- Each result also has `in_library: bool`: is the `video_id` in this user's library index?
- yt-dlp is blocking. Run it with `run_in_threadpool`. Timeout: 20 s.

### 6.2 Metadata cleanup (`metadata.clean`)

Pure function, unit-tested.

- Strip from the title (case-insensitive):
  - `(Official Music Video)`, `(Official Video)`, `(Official Audio)`
  - `(Lyrics)`, `(Lyric Video)`, `(Visualizer)`
  - `[4K ...]`, `[HD]`, `(HD)`, `| ...` suffixes
- Artist:
  - Use yt-dlp `artist` if present.
  - Else, if the title has the form `Artist - Title`, split it.
  - Else use the channel name, minus ` - Topic` and `VEVO`.
- Album: use yt-dlp `album` if present, else `Singles`.
- Playlist downloads: the default album is the playlist title. The user can edit it once for the whole playlist.

### 6.3 Jobs

SQLite file `data_dir/app.db`, WAL mode.

```sql
CREATE TABLE jobs (
  id          INTEGER PRIMARY KEY,
  user        TEXT NOT NULL,
  video_id    TEXT NOT NULL,
  title       TEXT NOT NULL,
  artist      TEXT NOT NULL,
  album       TEXT NOT NULL,
  track_no    INTEGER,                      -- album downloads only
  year        TEXT,                         -- album downloads only
  cover_url   TEXT,                         -- album cover; NULL = use video thumbnail
  box_id      TEXT,                         -- Jellyfin playlist id; NULL = no box
  status      TEXT NOT NULL CHECK (status IN ('queued','downloading','done','failed','cancelled')),
  progress    REAL NOT NULL DEFAULT 0,      -- 0..1
  error       TEXT,
  final_path  TEXT,
  created_at  TEXT NOT NULL,                -- ISO 8601 UTC
  updated_at  TEXT NOT NULL
);
CREATE INDEX jobs_user_status ON jobs(user, status);
```

- `POST /api/jobs` with a body of `{items: [{video_id, title, artist, album, track_no?, year?, cover_url?}], box_id?}`. One job per item. A playlist or album sends many items.
- `box_id`, when present, must be a box of this user (§6.9). Every job in the request gets it.
- Duplicate rule: skip the job when the same `video_id` is in the user's library or has an active job.
  - If the request has a `box_id` and the track is already in the library, add the existing track to the box instead (§6.9). Nothing downloads again.
- At startup, set jobs in `downloading` back to `queued` (crash recovery).
- `DELETE /api/jobs/{id}` cancels a `queued` job only.
- `POST /api/jobs/{id}/retry` sets a `failed` job back to `queued`.
- `GET /api/jobs` returns the user's active jobs plus the last 50 finished jobs.

### 6.4 Worker

N = `concurrency` asyncio tasks. Each task takes the oldest `queued` job and runs yt-dlp in a thread.

1. Format: `bestaudio[ext=m4a]/bestaudio`.
2. Output: `data_dir/tmp/<job_id>.<ext>`.
   - `/var/lib` and `/home` are on the same partition on this machine.
   - At startup, probe with a real rename of an empty hidden file from `tmp` into every `music_dir`. If it fails, use `music_dir/.wyc-music-streaming-tmp`. Comparing `st_dev` is not enough: systemd `ReadWritePaths=` bind-mounts each path separately, and `rename()` across bind mounts fails with `EXDEV` (seen on the NAS, so in production the fallback is used).
3. Postprocessors:
   - Convert the thumbnail to jpg.
   - Embed the thumbnail.
   - Never use `FFmpegExtractAudio` with a different codec, because it re-encodes.
4. Tag with mutagen:
   - title, artist, album artist, album
   - track number and year, when the job has them
   - comment `youtube:<video_id>`, used for duplicate detection
   - cover: if `cover_url` is set, fetch it (httpx, 10 s timeout) and embed it in place of the video thumbnail. If the fetch fails, keep the video thumbnail.
5. Move to `music_dir/<Artist>/<Album>/<Title>.<ext>`, or `<NN>_<Title>.<ext>` when `track_no` is set (`NN` = 2 digits):
   - sanitize names: remove `/\:*?"<>|`, trim, max 120 chars, then replace each run of whitespace with `_` (example: `Linkin_Park/Singles/Numb.m4a`)
   - if the name exists, add `_(2)`
   - use `os.replace`
6. Status → `done`. Update the library index. Schedule a Jellyfin refresh. Emit an SSE event.
7. If the job has a `box_id`: insert a `box_pending` row (§6.9).

Progress comes from the yt-dlp `progress_hooks`. Send at most 1 event per second per job.

File mode: the systemd `UMask=0002` gives `664` files and `2775` dirs (setgid is inherited), group `wick`. Jellyfin can read them.

### 6.5 Library

- At startup, walk every user's `music_dir`. Read tags with mutagen (`.m4a`, `.mp3`, `.opus`, `.flac`, `.ogg`).
- Keep an in-memory index: `user → artist → album → [track{path, title, duration, video_id?}]`.
- Missing tags fall back to folder names.
- Refresh the index:
  - after each job
  - after each delete
  - on `POST /api/library/rescan`
- Files added through SMB appear after a rescan, or after the hourly background rescan.
- `GET /api/library` returns the tree for the current user.
- `DELETE /api/library/track` with body `{path}`:
  1. Resolve the path with `paths.safe_resolve(user, path)`. Reject anything outside `music_dir`, including after resolving symlinks.
  2. Delete the file.
  3. Remove empty album and artist dirs.
  4. Schedule a Jellyfin refresh.

### 6.6 Jellyfin refresh

- `POST {url}/Library/Refresh` with header `Authorization: MediaBrowser Token="<key>"`.
- Debounce 30 s: one refresh after a batch of jobs.
- A failure only logs a warning. It never fails the job.
- The UI button calls the same function with no debounce.

### 6.7 Events (`GET /api/events`)

- SSE stream for the current user.
- Event types: `job` (status / progress), `library` (changed), `box` (a box changed, or a pending track was added).
- The frontend reconnects automatically with `EventSource`.

### 6.8 Albums (`GET /api/albums?q=`, `GET /api/albums/{browse_id}`)

Album data comes from YouTube Music through `ytmusicapi`, without login. yt-dlp still does every download.

- Search: `YTMusic().search(q, filter="albums")`, then keep the first 10. The `limit` argument does not cap the result count.
  - Each result has `browse_id`, `title`, `artist`, `year`, `cover_url`, and `type` (Album / EP / Single).
- Album view: `get_album(browse_id)`.
  - Album fields: `title`, `artist`, `year`, `cover_url` (largest thumbnail), `track_count`.
  - Each track has `video_id`, `title`, `artists`, `track_no`, `duration`, and `in_library`.
  - A track with no `video_id` is unavailable. The UI shows it greyed out and not selectable.
- Album link: `get_album_browse_id(<OLAK5uy_ id>)` gives the `browse_id`, then the same album view.
- The UI sends the selected tracks to `POST /api/jobs`. Every item gets the album's `title`, `year`, `cover_url`, and its own `track_no`. The artist is the album artist, so all tracks land in one album folder.
- The user can edit the album name and artist once for the whole album before download.
- `ytmusicapi` is blocking. Run it with `run_in_threadpool`. Timeout: 20 s.
- Cache album views in memory for 10 minutes. Opening the same album twice makes one request.
- `ytmusicapi` is unofficial and can break when YouTube changes. Update it with yt-dlp in the weekly timer.
  - If it fails, the album tab shows an error. Song search and links still work, because they use yt-dlp only.

### 6.9 Boxes (Jellyfin playlists)

A box is a Jellyfin playlist owned by the user's `jellyfin_user`. Jellyfin is the only store. WYC-music-streaming has no box table. A playlist that the user makes in the Jellyfin app also shows as a box.

All calls use the API key and pass `userId`.

| Action | WYC-music-streaming route | Jellyfin call |
|---|---|---|
| List boxes | `GET /api/boxes` | `GET /Items?userId=&includeItemTypes=Playlist&recursive=true` |
| Create | `POST /api/boxes {name}` | `POST /Playlists {Name, UserId, MediaType: "Audio", IsPublic: false}` |
| Rename | `PATCH /api/boxes/{id} {name}` | `POST /Playlists/{id} {Name}` |
| Delete box | `DELETE /api/boxes/{id}` | `DELETE /Items/{id}` (deletes the playlist only, never the audio files) |
| Box tracks | `GET /api/boxes/{id}` | `GET /Playlists/{id}/Items?userId=&fields=Path` |
| Add tracks | `POST /api/boxes/{id}/tracks {paths}` | `POST /Playlists/{id}/Items?ids=...&userId=` |
| Remove track | `DELETE /api/boxes/{id}/tracks/{entry_id}` | `DELETE /Playlists/{id}/Items?entryIds=...` |

- **Ownership:** the API key is admin, so Jellyfin does not protect one user's playlists from another. Before every box call, WYC-music-streaming checks that `{id}` is in this user's box list. If not → `404`.
- **Path → Jellyfin item id:**
  - WYC-music-streaming keeps one map `path → item id` per user. It fills the map with `GET /Items?userId=&includeItemTypes=Audio&recursive=true&fields=Path`. The `userId` limits the result to the libraries that this Jellyfin user can see, so a map holds only that user's tracks.
  - It reloads the map after each Jellyfin refresh, and when a lookup misses.
  - Jellyfin must see the files at the same path as WYC-music-streaming. The Jellyfin music library must point at `/home/wick/share/...`. See §11.
- **Box tracks in the UI:** each Jellyfin item is matched by `Path` to the library index. The match gives `video_id` (for the search result states) and the file info.
- **Search result states inside a box:**
  - not in library → "download + add to box" (job with `box_id`)
  - in library, not in box → "in library · add to box" (`POST /api/boxes/{id}/tracks`, no download)
  - in box → "already in box" (disabled)
- **New downloads (pending):** a new file has no Jellyfin item id until Jellyfin scans it.

  ```sql
  CREATE TABLE box_pending (
    job_id      INTEGER PRIMARY KEY REFERENCES jobs(id),
    user        TEXT NOT NULL,
    box_id      TEXT NOT NULL,
    path        TEXT NOT NULL,
    attempts    INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL
  );
  ```

  - A poller runs every 30 s while `box_pending` has rows. It reloads the path map, adds each found track to its box, and deletes the row.
  - After 20 attempts (about 10 minutes), the row stays and the UI shows "Jellyfin has not seen this file" with a retry button. Retry sets `attempts` to 0 and triggers a Jellyfin refresh.
  - The box page lists pending rows with the state "waiting for Jellyfin scan".
- **Delete a track from the library:** Jellyfin drops the item on its next scan. The item also leaves every playlist. WYC-music-streaming does nothing extra.
- **Library page:** each track has "add to box". It opens a small list of the user's boxes.

## 7. Frontend

- SvelteKit + `adapter-static` (SPA, `fallback: 'index.html'`) + Tailwind.
- Build on the NAS with Node from `nvm`. FastAPI serves `frontend/build/`.
- Fonts: self-host with `@fontsource/bai-jamjuree` and `@fontsource/space-mono`, so pages need no external requests.
- Design tokens (from canvas C):

| Token | Value |
|---|---|
| ground | `#EFE6D2` |
| card | `#FBF6EA` |
| ink | `#1E1B16` |
| orange | `#D9541E` |
| teal | `#1F6F78` |
| yellow | `#E8C86A` |
| muted text | `#5C5345` |

  - Style: border 2px ink, radius 6–10px, hard shadow `5px 5px 0`.

### Routes

| Route | Content |
|---|---|
| `/` (search) | Song / album / link tabs, result cards, "write the tape label" edit panel, cassette deck card for the current download, next queue, tape shelf summary |
| `/boxes` | "New box name" form, grid of cassette cards (name, track count, "in Jellyfin") |
| `/boxes/[id]` | Left: song / album / link tabs; every result adds to this box. Right: track list with × (remove from box only), pending tracks, "+ add from library", rename, delete box |
| `/library` | Artist list, album cards with tracks, inline delete confirm, filter box, "Jellyfin rescan" button, "add to box" per track |
| `/queue` | All active jobs plus history, retry failed jobs |
| `/denied` | Shown on 403 from `/api/me`. Shows the login and a config snippet |

- Playlist URL: show all entries with checkboxes, all selected by default. One album field applies to the whole batch.
- Album tab: album results with cover, year, and type. Opening one shows the tracklist with checkboxes, all selected by default, and a "download album" button.
- Mobile: every layout stacks at phone width. Touch targets are at least 44px.

## 8. Errors

| Case | Behavior |
|---|---|
| yt-dlp extract fails (video blocked, region, age) | Job `failed`, error text shown, "retry" button |
| yt-dlp out of date (YouTube changed) | Same as above. The error text suggests running the update timer now |
| Search timeout | 504. The UI shows "search took too long" |
| Disk full | Job `failed`. The tmp file is removed |
| Jellyfin offline | Warning in the log. The job still succeeds |
| Path traversal attempt | 400 and a log entry |
| Header missing / unknown user | 403, `/denied` |
| `ytmusicapi` fails | Album tab shows an error. Song search and links still work |
| Jellyfin offline, box action | 503. The UI shows "Jellyfin is offline". Downloads still work; pending rows wait |
| Box id of another user | 404 |
| `jellyfin_user` missing or not found | Boxes pages show "boxes are off for this user" |

## 9. Deployment (GitHub → old PC)

```
sudo mkdir -p /opt/wyc-music-streaming && sudo chown wick: /opt/wyc-music-streaming
git clone https://github.com/Worawit-cs/WYC-music-streaming.git /opt/wyc-music-streaming/repo
sudo /opt/wyc-music-streaming/repo/app/deploy/update.sh
```

`update.sh` (idempotent):

1. `git -C /opt/wyc-music-streaming/repo pull --ff-only`
2. As the repo owner (`wick`), with `UV_PYTHON_INSTALL_DIR=/opt/wyc-music-streaming/python`: `uv sync --frozen --no-dev --python 3.12`, then `uv pip install -U "yt-dlp[default]"`. The uv Python must live outside home dirs so the service user can run it.
3. `npm ci && npm run build` in `frontend/`.
4. Install the units to `/etc/systemd/system/`, then run `systemctl daemon-reload`.
5. `systemctl restart wyc-music-streaming`.

One-time setup (documented in README):

- `sudo useradd --system --gid wick --home-dir /var/lib/wyc-music-streaming --create-home wyc-music-streaming`
- Create `/etc/wyc-music-streaming/config.toml` and `jellyfin.key` (the key comes from Jellyfin Dashboard → API Keys).
- `sudo apt install ffmpeg unzip`
- Install `uv` and Deno **system-wide**. The service runs as `wyc-music-streaming` and cannot see binaries in `~wick/`:

  ```
  curl -LsSf https://astral.sh/uv/install.sh | sudo env UV_INSTALL_DIR=/usr/local/bin sh
  curl -fsSL https://deno.land/install.sh | sudo env DENO_INSTALL=/usr/local sh -s -- -y --no-modify-path
  deno --version   # must print a version for every user
  ```

- `update.sh` also runs `sudo deno upgrade`. YouTube changes can need a newer Deno as well as a newer yt-dlp.
- `sudo tailscale serve --bg --https=443 http://127.0.0.1:8097`
- In the Tailscale admin console, enable HTTPS certificates and MagicDNS.

`wyc-music-streaming.service` (key lines):

```ini
[Service]
User=wyc-music-streaming
Group=wick
UMask=0002
WorkingDirectory=/opt/wyc-music-streaming/repo/app/backend
ExecStart=/opt/wyc-music-streaming/repo/app/backend/.venv/bin/python -m wyc_music_streaming
Environment=WYC_MUSIC_STREAMING_CONFIG=/etc/wyc-music-streaming/config.toml
Restart=on-failure
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/var/lib/wyc-music-streaming /home/wick/share
```

The app reads host and port from the validated config. The loopback check in config.py therefore covers the real listen address.

`wyc-music-streaming-update-ytdlp.timer`:

- Runs weekly: `uv pip install -U "yt-dlp[default]" ytmusicapi`, then restarts wyc-music-streaming.
- Runs as `wick`. The restart line runs as root through systemd's `+` prefix.

## 10. Testing

- **Unit (pytest):**
  - `metadata.clean`: a table of real YouTube titles
  - `paths.safe_resolve`: `..`, absolute paths, symlinks out of the root
  - `auth.resolve_user`: header present / missing / unknown, dev mode
  - config validation
  - name sanitizing (whitespace → `_`) and the `_(2)` collision rule
- **Integration (pytest + tmp dirs):**
  - worker with yt-dlp mocked: job flow queued → done, file moved, tags written, duplicate skipped, crash recovery
  - library scan and delete
  - Jellyfin refresh with debounce (httpx mock)
  - albums: `ytmusicapi` mocked with recorded JSON; unavailable tracks; album link → browse id
  - boxes (httpx mock of Jellyfin): ownership check, add from library, pending poller adds after the item appears, gives up after 20 attempts
  - job with `box_id` for a track already in the library: no download, track added to box
- **Frontend:** `svelte-check` + a few Vitest component tests for the edit panel and the delete confirm.
- **Manual smoke test on the NAS:**
  1. Search, download 1 track, and see it in Jellyfin.
  2. Download a playlist.
  3. Delete a track.
  4. Open from a device whose Tailscale login is not in config, and see `/denied`.
  5. `curl http://<lan-ip>:8097` must fail.
  6. Download an album from the album tab. Jellyfin shows one album with track numbers and cover.
  7. Create a box, add 1 library track and 1 new download. Both appear in the Jellyfin app playlist.

## 11. Risks, verify first

1. ~~Deno on Ubuntu 20.04 / Core2 Duo~~: **verified 2026-11-05**.
   - Stack: Deno 2.9.8, uv 0.13.7, Python 3.12, `yt-dlp[default]`.
   - yt-dlp reported `JS runtimes: deno-2.9.8`.
   - Downloaded format 140 (m4a, 2.89 MiB) successfully.
2. ~~`tailscale serve` with UFW~~: **verified 2026-11-06**. `https://<nas>.<tailnet>.ts.net` opens from another tailnet device with no UFW change.
3. ~~Tailscale version~~: **verified**. Version 1.98.4 supports `tailscale serve --bg`.
4. **Node on 20.04.** Not yet tested. Check that `nvm install --lts` gives a working Node (glibc 2.31).
5. ~~ffmpeg~~: **verified 2026-11-06**. ffmpeg 4.2.7 from the Ubuntu 20.04 repo. Stream copy to m4a works.
6. ~~Jellyfin version ≥ 10.9~~: **verified 2026-11-05**. Version 10.11.8.
7. ~~ytmusicapi without login~~: **verified 2026-11-05** on the NAS.
   - `search(filter="albums")` returned Meteora first, with `year` and `browseId`.
   - `get_album` returned `audioPlaylistId` (`OLAK5uy_...`) and tracks with `trackNumber` and `videoId`.
   - `limit=3` returned 20 results. `limit` is not a maximum, so the code slices the list to 10.
8. ~~Same file paths in Jellyfin~~: **verified 2026-11-05**. Each user has their own library, and both match the `music_dir` values in config:
   - "Wick Music" → `/home/wick/share/wick/music`
   - "Safeena Music" → `/home/wick/share/safeena/music`
9. **First deploy and smoke test: done 2026-11-06** (plan 1, Task 15), with `app/deploy/nas-setup.sh`.
   - `check-nas.sh`: no FAIL. `systemctl status wyc-music-streaming`: active (running).
   - `GET /api/me` over `https://<nas>.<tailnet>.ts.net` from another tailnet device: 200 with the right user.
   - Unknown `Tailscale-User-Login`: 403. `curl http://<lan-ip>:8097`: connection refused.
   - Search "numb linkin park": 10 results; the first one cleaned to `Numb` / `Linkin Park`.
   - Download job: done in about 9 s. File `Linkin_Park/Singles/Numb.m4a`, mode `664`, owner `wyc-music-streaming`, group `wick`. The track shows in Jellyfin.
   - Found and fixed during the deploy:
     - `EXDEV` on the final move: systemd `ReadWritePaths=` bind-mounts `/var/lib/wyc-music-streaming` and `/home/wick/share` separately, so the worker now probes a real rename (see §6.4) and uses `music_dir/.wyc-music-streaming-tmp` on the NAS.
     - `config.toml` and `jellyfin.key` use group `wick`. There is no `wyc-music-streaming` group, because the service user is created with `--gid wick`.
     - File and folder names use `_` for spaces (§6.4 step 5), as the owner asked.
   - Service start takes about 5 s (it scans the music folders first). Wait for it before the first request.

## 12. Later (not in this version)

- Phase 2: streaming (`Range` endpoint + player bar), or move to Navidrome
- `oidc` auth mode (Pocket ID / Authelia)
- Upgrade Ubuntu 20.04 → 24.04
