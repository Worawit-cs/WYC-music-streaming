# Search and Library Polish Implementation Plan (plan 2.5)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pick artist and album from the library in the tape label editor, browse the library by album, page search results (10 per page, 5 pages), and suggest searches while typing.

**Architecture:** Two small backend changes: `search()` takes a `page` and slices yt-dlp's `ytsearch50:` with `playlist_items`; a new `/api/suggest` proxies Google's YouTube suggest endpoint through one shared `httpx.AsyncClient` and returns `[]` on any failure. The frontend gets pure modules (`artistMatch`, `albumList`, `libraryOptions`, `searchPages`), three components (`Combobox`, `Pager`, `AlbumGrid`), and wires them into the search page, the editor and the library page.

**Tech Stack:** FastAPI + yt-dlp + httpx (backend, pytest + pytest-asyncio auto mode); SvelteKit 2 + Svelte 5 runes + Tailwind 4 (frontend, Vitest + Testing Library). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-11-07-search-library-polish-design.md` (addendum to `docs/superpowers/specs/2026-11-05-wyc-music-streaming-design.md`).

## Global Constraints

- Search: `PAGE_SIZE = 10`, `MAX_PAGES = 5`. `/api/search?page=` accepts 1..5 (else 422). URL and playlist lookups ignore `page` and return `page: 1`, `has_more: false`.
- Suggest: `https://suggestqueries.google.com/complete/search?client=firefox&ds=yt&q=...`, timeout 3 s, at most 8 strings, any error gives `{"suggestions": []}` with status 200. Suggestions start at 2 characters, after 250 ms, only on the "เพลง" tab.
- Every `/api` route needs the Tailscale identity (403 without it). Tests never call the real Google or YouTube: use `httpx.MockTransport` and the fake `extract`.
- UI text is Thai. Code, comments, commits and docs are English.
- `npm run check` runs `svelte-check --fail-on-warnings`: zero errors and zero warnings.
- Touch targets stay at least 44px (`.btn`, `.input` already do this).
- The repo is public: never commit `config.toml`, keys, or real Tailscale logins.

## Execution notes

- Backend commands run in `app/backend/` (`uv run pytest -q`). Frontend commands run in `app/frontend/` with Node from nvm (`source ~/.nvm/nvm.sh`).
- Every code block below was built and tested together before this plan was written:
  backend 131 tests pass; frontend 97 tests pass, `svelte-check` 0 errors 0 warnings, build OK;
  checked in a browser against the dev backend (real suggestions, pages 1 and 3, editor combobox, album view).
- Diffs are against commit `139b109` plus the earlier tasks of this plan, in order.
- Known and accepted: YouTube sometimes returns the same video on two pages. The cards show it twice; nothing breaks.

## File structure

```
app/backend/wyc_music_streaming/
  search.py        + page / has_more (PAGE_SIZE, MAX_PAGES)
  suggest.py       NEW  fetch_suggestions(http, q) -> list[str]
  api.py           /api/search?page=, NEW /api/suggest
  main.py          one httpx.AsyncClient for suggest (app.state.suggest_http), suggest_transport for tests
app/backend/tests/
  test_search.py, test_api.py, NEW test_suggest.py
app/frontend/src/lib/
  artistMatch.ts     NEW  matchArtist(suggested, names): library name for "Artist, Guest & Guest"
  albumList.ts       NEW  albumList(artists): AlbumCard[] (one card per artist + album)
  libraryOptions.ts  NEW  artistOptions / albumOptions (combobox rows), libraryMatches (search rows)
  searchPages.ts     NEW  MAX_PAGES, knownLastPage(pages), pageNumbers(last)
  types.ts           SearchResponse.page / has_more, ComboOption
  api.ts             search(q, page), suggest(q, signal)
  selection.ts       draftFrom(result, libraryArtists) prefills the artist
  components/Combobox.svelte   NEW  text input + popup list (ARIA combobox), optional filter and create row
  components/Pager.svelte      NEW  « ก่อน 1 2 3 4 5 ถัดไป »
  components/AlbumGrid.svelte  NEW  album cards that open in place
  components/EditPanel.svelte  artist and album fields become Combobox
app/frontend/src/routes/
  +page.svelte          suggestions, pages, library prefill
  library/+page.svelte  [ศิลปิน | อัลบั้ม] toggle (?view=albums)
```

---
### Task 1: Backend search pages

**Files:**
- Modify: `app/backend/wyc_music_streaming/search.py`, `app/backend/wyc_music_streaming/api.py`
- Test: `app/backend/tests/test_search.py`, `app/backend/tests/test_api.py`

**Interfaces:**
- Produces: `search(query, library_ids, extract=ytdlp_extract, *, page=1) -> dict` with keys `kind, playlist_title, results, page, has_more`; raises `ValueError` for a blank query or a page outside 1..`MAX_PAGES`. Constants `PAGE_SIZE = 10`, `MAX_PAGES = 5` (`SEARCH_COUNT` is removed).
- Produces: `GET /api/search?q=&page=` (page 1..5, default 1).

- [ ] **Step 1: Write the failing tests**

Modify `app/backend/tests/test_search.py` (apply with `git apply` from the repo root, or edit by hand):

```diff
diff --git a/app/backend/tests/test_search.py b/app/backend/tests/test_search.py
index 7573234..51a3a5e 100644
--- a/app/backend/tests/test_search.py
+++ b/app/backend/tests/test_search.py
@@ -1,6 +1,6 @@
 import pytest
 
-from wyc_music_streaming.search import MAX_PLAYLIST, search
+from wyc_music_streaming.search import MAX_PAGES, MAX_PLAYLIST, PAGE_SIZE, search
 
 
 def fake(info):
@@ -13,7 +13,7 @@ def fake(info):
     return extract, calls
 
 
-def test_keyword_search_uses_ytsearch10_flat():
+def test_keyword_search_asks_for_page_one_flat():
     extract, calls = fake({
         "_type": "playlist", "title": "numb",
         "entries": [
@@ -25,10 +25,13 @@ def test_keyword_search_uses_ytsearch10_flat():
     })
     out = search("  numb  ", {"kXYiU_JCYtU"}, extract)
     [(target, opts)] = calls
-    assert target == "ytsearch10:numb"
+    assert target == "ytsearch50:numb"
+    assert opts["playlist_items"] == "1-10"
     assert opts["extract_flat"] == "in_playlist"
     assert out["kind"] == "search"
     assert out["playlist_title"] is None
+    assert out["page"] == 1
+    assert out["has_more"] is False  # only one valid entry came back
     [r] = out["results"]
     assert r == {
         "video_id": "kXYiU_JCYtU",
@@ -78,3 +81,43 @@ def test_blank_query_raises():
     extract, _ = fake({})
     with pytest.raises(ValueError):
         search("   ", set(), extract)
+
+
+def page_of(n):
+    return {"_type": "playlist", "title": "q", "entries": [
+        {"id": f"vid{i:08d}", "title": f"Song {i}", "channel": "Ch"} for i in range(n)
+    ]}
+
+
+def test_page_three_asks_for_items_21_to_30():
+    extract, calls = fake(page_of(PAGE_SIZE))
+    out = search("weeknd", set(), extract, page=3)
+    assert calls[0][1]["playlist_items"] == "21-30"
+    assert out["page"] == 3
+    assert out["has_more"] is True
+
+
+def test_last_page_has_no_more():
+    extract, _ = fake(page_of(PAGE_SIZE))
+    out = search("weeknd", set(), extract, page=MAX_PAGES)
+    assert out["has_more"] is False
+
+
+def test_short_page_has_no_more():
+    extract, _ = fake(page_of(PAGE_SIZE - 1))
+    assert search("weeknd", set(), extract, page=2)["has_more"] is False
+
+
+@pytest.mark.parametrize("page", [0, MAX_PAGES + 1])
+def test_page_out_of_range_raises(page):
+    extract, _ = fake(page_of(1))
+    with pytest.raises(ValueError):
+        search("weeknd", set(), extract, page=page)
+
+
+def test_url_lookup_ignores_page():
+    extract, calls = fake({"id": "aaaaaaaaaaa", "title": "x", "channel": "y"})
+    out = search("https://youtu.be/aaaaaaaaaaa", set(), extract, page=4)
+    assert "playlist_items" not in calls[0][1]
+    assert out["page"] == 1
+    assert out["has_more"] is False
```

Modify `app/backend/tests/test_api.py` (apply with `git apply` from the repo root, or edit by hand):

```diff
diff --git a/app/backend/tests/test_api.py b/app/backend/tests/test_api.py
index 95ceb1b..aa6f232 100644
--- a/app/backend/tests/test_api.py
+++ b/app/backend/tests/test_api.py
@@ -82,6 +82,14 @@ def test_missing_header_is_denied(config):
 def test_search_validation(client):
     assert client.get("/api/search", params={"q": ""}).status_code == 422
     assert client.get("/api/search", params={"q": "   "}).status_code == 400
+    assert client.get("/api/search", params={"q": "numb", "page": 0}).status_code == 422
+    assert client.get("/api/search", params={"q": "numb", "page": 6}).status_code == 422
+
+
+def test_search_returns_page_fields(client):
+    out = client.get("/api/search", params={"q": "numb", "page": 2}).json()
+    assert out["page"] == 2
+    assert out["has_more"] is False
 
 
 def test_download_flow(client):
```

- [ ] **Step 2: Run the tests and see them fail**

Run: `uv run pytest -q tests/test_search.py tests/test_api.py`
Expected: collection error `ImportError: cannot import name 'MAX_PAGES' from 'wyc_music_streaming.search'`.

- [ ] **Step 3: Write the code**

Modify `app/backend/wyc_music_streaming/search.py` (apply with `git apply` from the repo root, or edit by hand):

```diff
diff --git a/app/backend/wyc_music_streaming/search.py b/app/backend/wyc_music_streaming/search.py
index 5ec293e..f45a524 100644
--- a/app/backend/wyc_music_streaming/search.py
+++ b/app/backend/wyc_music_streaming/search.py
@@ -12,7 +12,8 @@ Extractor = Callable[[str, dict[str, Any]], dict[str, Any]]
 
 SEARCH_TIMEOUT = 20.0
 MAX_PLAYLIST = 200
-SEARCH_COUNT = 10
+PAGE_SIZE = 10
+MAX_PAGES = 5
 YOUTUBE_URL = re.compile(r"^https?://([\w-]+\.)?(youtube\.com|youtu\.be)/", re.IGNORECASE)
 RADIO_MIX = re.compile(r"[?&]list=RD")
 VIDEO_ID = re.compile(r"^[\w-]{11}$")
@@ -25,7 +26,7 @@ def ytdlp_extract(target: str, opts: dict[str, Any]) -> dict[str, Any]:
         return ydl.sanitize_info(ydl.extract_info(target, download=False))
 
 
-def _options(target: str, is_url: bool) -> dict[str, Any]:
+def _options(target: str, is_url: bool, page: int) -> dict[str, Any]:
     opts: dict[str, Any] = {
         "quiet": True,
         "no_warnings": True,
@@ -36,6 +37,8 @@ def _options(target: str, is_url: bool) -> dict[str, Any]:
     }
     if is_url and "v=" in target and RADIO_MIX.search(target):
         opts["noplaylist"] = True  # a "Mix" list is endless radio, not a real playlist
+    if not is_url:
+        opts["playlist_items"] = f"{(page - 1) * PAGE_SIZE + 1}-{page * PAGE_SIZE}"
     return opts
 
 
@@ -59,12 +62,20 @@ def _result(entry: dict[str, Any], playlist_title: str | None, library_ids: set[
     }
 
 
-def search(query: str, library_ids: set[str], extract: Extractor = ytdlp_extract) -> dict[str, Any]:
+def search(
+    query: str, library_ids: set[str], extract: Extractor = ytdlp_extract, *, page: int = 1
+) -> dict[str, Any]:
+    """Text search returns one page of PAGE_SIZE results; URL lookups ignore page."""
     target = query.strip()
     if not target:
         raise ValueError("empty query")
+    if not 1 <= page <= MAX_PAGES:
+        raise ValueError(f"page must be 1..{MAX_PAGES}")
     is_url = bool(YOUTUBE_URL.match(target))
-    info = extract(target if is_url else f"ytsearch{SEARCH_COUNT}:{target}", _options(target, is_url))
+    if is_url:
+        page = 1
+    search_target = f"ytsearch{PAGE_SIZE * MAX_PAGES}:{target}"
+    info = extract(target if is_url else search_target, _options(target, is_url, page))
 
     is_list = info.get("_type") == "playlist"
     playlist_title = info.get("title") if (is_url and is_list) else None
@@ -75,4 +86,8 @@ def search(query: str, library_ids: set[str], extract: Extractor = ytdlp_extract
         if e and VIDEO_ID.match(str(e.get("id", "")))
     ]
     kind = "playlist" if playlist_title else ("url" if is_url else "search")
-    return {"kind": kind, "playlist_title": playlist_title, "results": results}
+    has_more = not is_url and page < MAX_PAGES and len(results) == PAGE_SIZE
+    return {
+        "kind": kind, "playlist_title": playlist_title, "results": results,
+        "page": page, "has_more": has_more,
+    }
```

Modify `app/backend/wyc_music_streaming/api.py` (apply with `git apply` from the repo root, or edit by hand):

```diff
diff --git a/app/backend/wyc_music_streaming/api.py b/app/backend/wyc_music_streaming/api.py
index 8a69947..a283069 100644
--- a/app/backend/wyc_music_streaming/api.py
+++ b/app/backend/wyc_music_streaming/api.py
@@ -20,7 +20,7 @@ from .config import User
 from .events import format_sse
 from .jobs import NewJob
 from .paths import UnsafePath
-from .search import SEARCH_TIMEOUT, search
+from .search import MAX_PAGES, SEARCH_TIMEOUT, search
 
 log = logging.getLogger(__name__)
 router = APIRouter(prefix="/api")
@@ -62,12 +62,17 @@ async def me(user: UserDep) -> dict[str, Any]:
 
 @router.get("/search")
 async def search_route(
-    request: Request, user: UserDep, q: Annotated[str, Query(min_length=1, max_length=500)]
+    request: Request,
+    user: UserDep,
+    q: Annotated[str, Query(min_length=1, max_length=500)],
+    page: Annotated[int, Query(ge=1, le=MAX_PAGES)] = 1,
 ) -> dict[str, Any]:
     st = request.app.state
     ids = st.library.video_ids(user.name)
     try:
-        return await asyncio.wait_for(run_in_threadpool(search, q, ids, st.extract), timeout=SEARCH_TIMEOUT)
+        return await asyncio.wait_for(
+            run_in_threadpool(search, q, ids, st.extract, page=page), timeout=SEARCH_TIMEOUT
+        )
     except ValueError:
         raise HTTPException(status_code=400, detail="empty query") from None
     except TimeoutError:
```

- [ ] **Step 4: Run the tests and see them pass**

Run: `uv run pytest -q`
Expected: all tests pass (119 at this point).

- [ ] **Step 5: Commit**

```bash
git add app/backend/wyc_music_streaming/search.py \
  app/backend/wyc_music_streaming/api.py \
  app/backend/tests/test_search.py \
  app/backend/tests/test_api.py
git commit -m "feat(backend): page text search results (10 per page, 5 pages)"
```

### Task 2: Backend suggestions

**Files:**
- Create: `app/backend/wyc_music_streaming/suggest.py`, `app/backend/tests/test_suggest.py`
- Modify: `app/backend/wyc_music_streaming/api.py`, `app/backend/wyc_music_streaming/main.py`, `app/backend/tests/test_api.py`

**Interfaces:**
- Consumes: `UserDep` and `router` in `api.py`.
- Produces: `async fetch_suggestions(http: httpx.AsyncClient, q: str) -> list[str]`, constants `SUGGEST_URL`, `SUGGEST_TIMEOUT = 3.0`, `MAX_SUGGESTIONS = 8`.
- Produces: `GET /api/suggest?q=` (1..100 chars) -> `{"suggestions": [...]}`.
- Produces: `create_app(..., suggest_transport: httpx.AsyncBaseTransport | None = None)`; `app.state.suggest_http`.

The `client` fixture in `test_api.py` passes a `suggest_transport`, so no test reaches Google.

- [ ] **Step 1: Write the failing tests**

Create `app/backend/tests/test_suggest.py`:

```python
import json

import httpx
import pytest

from wyc_music_streaming.suggest import MAX_SUGGESTIONS, SUGGEST_URL, fetch_suggestions


def client_for(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_returns_at_most_max_suggestions():
    seen = []

    def handler(request):
        seen.append(request)
        words = [f"the weeknd {i}" for i in range(10)]
        return httpx.Response(200, json=["the weeknd", words, [], {}])

    async with client_for(handler) as http:
        out = await fetch_suggestions(http, "the weeknd")
    assert out == [f"the weeknd {i}" for i in range(MAX_SUGGESTIONS)]
    [request] = seen
    assert str(request.url).startswith(SUGGEST_URL)
    assert request.url.params["q"] == "the weeknd"
    assert request.url.params["client"] == "firefox"
    assert request.url.params["ds"] == "yt"


async def test_keeps_thai_text():
    body = json.dumps(["เพลง", ["เพลงไทย", "เพลงฮิต"]], ensure_ascii=False).encode()

    def handler(request):
        return httpx.Response(200, content=body, headers={"Content-Type": "text/javascript; charset=UTF-8"})

    async with client_for(handler) as http:
        assert await fetch_suggestions(http, "เพลง") == ["เพลงไทย", "เพลงฮิต"]


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500, json=["q", ["x"]]),
        httpx.Response(200, content=b"not json"),
        httpx.Response(200, json={"q": ["x"]}),
        httpx.Response(200, json=["q"]),
        httpx.Response(200, json=["q", "x"]),
    ],
    ids=["status-500", "bad-json", "dict", "short-list", "not-a-list"],
)
async def test_bad_responses_give_empty_list(response):
    async with client_for(lambda request: response) as http:
        assert await fetch_suggestions(http, "q") == []


async def test_drops_items_that_are_not_text():
    async with client_for(lambda request: httpx.Response(200, json=["q", ["ok", 3, None, " "]])) as http:
        assert await fetch_suggestions(http, "q") == ["ok"]


async def test_network_error_gives_empty_list():
    def handler(request):
        raise httpx.ConnectTimeout("too slow", request=request)

    async with client_for(handler) as http:
        assert await fetch_suggestions(http, "q") == []
```

Modify `app/backend/tests/test_api.py` (apply with `git apply` from the repo root, or edit by hand):

```diff
diff --git a/app/backend/tests/test_api.py b/app/backend/tests/test_api.py
index aa6f232..e705877 100644
--- a/app/backend/tests/test_api.py
+++ b/app/backend/tests/test_api.py
@@ -40,8 +40,12 @@ def client(config, make_audio):
         jf_calls.append(request)
         return httpx.Response(204)
 
+    def suggest(request):
+        return httpx.Response(200, json=[request.url.params["q"], ["numb", "numb lyrics"]])
+
     app = create_app(config, downloader=downloader, extract=extract,
-                     jellyfin_transport=httpx.MockTransport(jellyfin), refresh_delay=0.01)
+                     jellyfin_transport=httpx.MockTransport(jellyfin),
+                     suggest_transport=httpx.MockTransport(suggest), refresh_delay=0.01)
     with TestClient(app, headers=WICK) as c:
         c.jf_calls = jf_calls
         yield c
@@ -86,6 +90,21 @@ def test_search_validation(client):
     assert client.get("/api/search", params={"q": "numb", "page": 6}).status_code == 422
 
 
+def test_suggest_returns_list(client):
+    r = client.get("/api/suggest", params={"q": "num"})
+    assert r.status_code == 200
+    assert r.json() == {"suggestions": ["numb", "numb lyrics"]}
+
+
+def test_suggest_validation(client):
+    assert client.get("/api/suggest", params={"q": ""}).status_code == 422
+    assert client.get("/api/suggest", params={"q": "x" * 101}).status_code == 422
+
+
+def test_suggest_needs_identity(client):
+    assert client.get("/api/suggest", params={"q": "num"}, headers={HEADER: "stranger@example.com"}).status_code == 403
+
+
 def test_search_returns_page_fields(client):
     out = client.get("/api/search", params={"q": "numb", "page": 2}).json()
     assert out["page"] == 2
```

- [ ] **Step 2: Run the tests and see them fail**

Run: `uv run pytest -q tests/test_suggest.py tests/test_api.py`
Expected: collection error `ModuleNotFoundError: No module named 'wyc_music_streaming.suggest'`, and `test_api.py` fails with `TypeError: create_app() got an unexpected keyword argument 'suggest_transport'`.

- [ ] **Step 3: Write the code**

Create `app/backend/wyc_music_streaming/suggest.py`:

```python
"""Search-box suggestions from Google's YouTube suggest endpoint (not an official API).

Any failure gives an empty list: suggestions are a nice-to-have and must never break search.
"""
from __future__ import annotations

import logging

import httpx

log = logging.getLogger(__name__)

SUGGEST_URL = "https://suggestqueries.google.com/complete/search"
SUGGEST_TIMEOUT = 3.0
MAX_SUGGESTIONS = 8


async def fetch_suggestions(http: httpx.AsyncClient, q: str) -> list[str]:
    """Return up to MAX_SUGGESTIONS strings. The endpoint answers ["q", ["s1", "s2", ...], ...]."""
    try:
        response = await http.get(SUGGEST_URL, params={"client": "firefox", "ds": "yt", "q": q})
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("suggest failed: %s", exc)
        return []
    if not (isinstance(data, list) and len(data) >= 2 and isinstance(data[1], list)):
        log.warning("suggest gave an unexpected shape: %.100r", data)
        return []
    words = [s.strip() for s in data[1] if isinstance(s, str) and s.strip()]
    return words[:MAX_SUGGESTIONS]
```

Modify `app/backend/wyc_music_streaming/api.py` (apply with `git apply` from the repo root, or edit by hand):

```diff
diff --git a/app/backend/wyc_music_streaming/api.py b/app/backend/wyc_music_streaming/api.py
index a283069..3b3f439 100644
--- a/app/backend/wyc_music_streaming/api.py
+++ b/app/backend/wyc_music_streaming/api.py
@@ -21,6 +21,7 @@ from .events import format_sse
 from .jobs import NewJob
 from .paths import UnsafePath
 from .search import MAX_PAGES, SEARCH_TIMEOUT, search
+from .suggest import fetch_suggestions
 
 log = logging.getLogger(__name__)
 router = APIRouter(prefix="/api")
@@ -81,6 +82,13 @@ async def search_route(
         raise HTTPException(status_code=502, detail=str(exc).removeprefix("ERROR: ")[:300]) from None
 
 
+@router.get("/suggest")
+async def suggest_route(
+    request: Request, user: UserDep, q: Annotated[str, Query(min_length=1, max_length=100)]
+) -> dict[str, list[str]]:
+    return {"suggestions": await fetch_suggestions(request.app.state.suggest_http, q)}
+
+
 @router.post("/jobs", status_code=201)
 async def create_jobs(request: Request, user: UserDep, body: JobsRequest) -> dict[str, Any]:
     st = request.app.state
```

Modify `app/backend/wyc_music_streaming/main.py` (apply with `git apply` from the repo root, or edit by hand):

```diff
diff --git a/app/backend/wyc_music_streaming/main.py b/app/backend/wyc_music_streaming/main.py
index 336d79c..375ad23 100644
--- a/app/backend/wyc_music_streaming/main.py
+++ b/app/backend/wyc_music_streaming/main.py
@@ -22,6 +22,7 @@ from .jellyfin import JellyfinClient, RefreshScheduler
 from .jobs import JobStore
 from .library import Library
 from .search import Extractor, ytdlp_extract
+from .suggest import SUGGEST_TIMEOUT
 from .worker import Downloader, Worker, ytdlp_download
 
 log = logging.getLogger(__name__)
@@ -60,6 +61,7 @@ def create_app(
     downloader: Downloader = ytdlp_download,
     extract: Extractor = ytdlp_extract,
     jellyfin_transport: httpx.AsyncBaseTransport | None = None,
+    suggest_transport: httpx.AsyncBaseTransport | None = None,
     refresh_delay: float = 30.0,
     rescan_interval: float = 3600.0,
     static_dir: Path | None = DEFAULT_STATIC_DIR,
@@ -80,6 +82,7 @@ def create_app(
         events = EventBroker()
         jellyfin = JellyfinClient(config.jellyfin.url, config.jellyfin.api_key, transport=jellyfin_transport)
         refresher = RefreshScheduler(jellyfin, delay=refresh_delay)
+        suggest_http = httpx.AsyncClient(timeout=SUGGEST_TIMEOUT, transport=suggest_transport)
         worker = Worker(config=config, store=store, library=library, events=events,
                         refresher=refresher, downloader=downloader)
 
@@ -90,6 +93,7 @@ def create_app(
         app.state.refresher = refresher
         app.state.worker = worker
         app.state.extract = extract
+        app.state.suggest_http = suggest_http
 
         tasks = worker.start() if start_workers else []
         tasks.append(asyncio.create_task(_rescan_forever(library, events, config.users, rescan_interval)))
@@ -103,6 +107,7 @@ def create_app(
                     await task
             await refresher.aclose()
             await jellyfin.aclose()
+            await suggest_http.aclose()
             store.close()
 
     app = FastAPI(title="WYC-music-streaming", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
```

- [ ] **Step 4: Run the tests and see them pass**

Run: `uv run pytest -q`
Expected: all tests pass (131).

- [ ] **Step 5: Commit**

```bash
git add app/backend/wyc_music_streaming/suggest.py \
  app/backend/wyc_music_streaming/api.py \
  app/backend/wyc_music_streaming/main.py \
  app/backend/tests/test_suggest.py \
  app/backend/tests/test_api.py
git commit -m "feat(backend): add /api/suggest for search-box suggestions"
```

### Task 3: Frontend pure logic and API client

**Files:**
- Create: `app/frontend/src/lib/artistMatch.ts`, `app/frontend/src/lib/albumList.ts`, `app/frontend/src/lib/libraryOptions.ts`, `app/frontend/src/lib/searchPages.ts` (each with a `.test.ts`)
- Modify: `app/frontend/src/lib/types.ts`, `app/frontend/src/lib/api.ts`, `app/frontend/src/lib/api.test.ts`

**Interfaces:**
- Consumes: `LibraryArtist`, `LibraryTrack`, `SearchResponse` from `types.ts`; `LIBRARY`, `makeTrack` from `testData.ts`.
- Produces:
  - `matchArtist(suggested: string, names: string[]): string`
  - `type AlbumCard = { key: string; album: string; artist: string; tracks: LibraryTrack[] }`, `albumList(artists: LibraryArtist[]): AlbumCard[]`
  - `artistOptions(artists: LibraryArtist[], youtubeGuess?: string): ComboOption[]`, `albumOptions(artists: LibraryArtist[], artist: string): ComboOption[]`, `libraryMatches(artists: LibraryArtist[], typed: string, limit = 3): string[]`
  - `MAX_PAGES = 5`, `knownLastPage(pages: Iterable<SearchResponse>): number`, `pageNumbers(last: number): number[]`
  - `type ComboOption = { value: string; label: string; hint?: string }`; `SearchResponse` gains `page: number; has_more: boolean`
  - `api.search(q: string, page = 1)`, `api.suggest(q: string, signal?: AbortSignal): Promise<{ suggestions: string[] }>`

Sort note: `albumList` uses `localeCompare(..., 'th')`, which puts Thai names before Latin names. The test pins that order.

- [ ] **Step 1: Write the failing tests**

Create `app/frontend/src/lib/artistMatch.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { matchArtist } from './artistMatch';

const NAMES = ['The Weeknd', 'Linkin Park', 'JENNIE', 'The Weeknd Tribute'];

describe('matchArtist', () => {
	it('returns the library spelling on an exact match, ignoring case and spaces', () => {
		expect(matchArtist('  the weeknd ', NAMES)).toBe('The Weeknd');
	});

	it.each([
		'The Weeknd, JENNIE & Lily Rose Depp',
		'The Weeknd & Ariana Grande',
		'The Weeknd x Playboi Carti',
		'The Weeknd X Playboi Carti',
		'The Weeknd feat. Daft Punk',
		'The Weeknd feat Daft Punk',
		'The Weeknd ft. Kendrick Lamar',
		'The Weeknd ft Kendrick Lamar',
		'The Weeknd with Madonna',
		'The Weeknd and Lana Del Rey',
		'The Weeknd / Daft Punk'
	])('picks the library artist at the start of %s', (guess) => {
		expect(matchArtist(guess, NAMES)).toBe('The Weeknd');
	});

	it('prefers the longest library name', () => {
		expect(matchArtist('The Weeknd Tribute, Someone', NAMES)).toBe('The Weeknd Tribute');
	});

	it('needs a separator after the name', () => {
		expect(matchArtist('The Weekndz', NAMES)).toBe('The Weekndz');
		expect(matchArtist('Linkin Parkway & Co', NAMES)).toBe('Linkin Parkway & Co');
		expect(matchArtist('JENNIEx Lisa', NAMES)).toBe('JENNIEx Lisa');
	});

	it('keeps the guess when nothing matches', () => {
		expect(matchArtist('Sade', NAMES)).toBe('Sade');
		expect(matchArtist('Sade', [])).toBe('Sade');
		expect(matchArtist('Sade', ['', '  '])).toBe('Sade');
	});
});
```

Create `app/frontend/src/lib/albumList.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { albumList } from './albumList';
import { LIBRARY, makeTrack } from './testData';
import type { LibraryArtist } from './types';

describe('albumList', () => {
	it('makes one card per artist and album, sorted by album then artist', () => {
		const cards = albumList(LIBRARY);
		expect(cards.map((c) => [c.album, c.artist, c.tracks.length])).toEqual([
			['Diamond Life', 'Sade', 1],
			['Meteora', 'Linkin Park', 2],
			['Singles', 'Linkin Park', 1]
		]);
	});

	it('keeps Singles of two artists as two cards with different keys', () => {
		const artists: LibraryArtist[] = [
			{ artist: 'The Weeknd', albums: [{ album: 'Singles', tracks: [makeTrack()] }] },
			{ artist: 'Linkin Park', albums: [{ album: 'Singles', tracks: [makeTrack()] }] }
		];
		const cards = albumList(artists);
		expect(cards.map((c) => c.artist)).toEqual(['Linkin Park', 'The Weeknd']);
		expect(new Set(cards.map((c) => c.key)).size).toBe(2);
	});

	it('sorts with the Thai locale (Thai before Latin) and ignores case', () => {
		const artists: LibraryArtist[] = [
			{
				artist: 'A',
				albums: [
					{ album: 'ไทย', tracks: [] },
					{ album: 'beta', tracks: [] },
					{ album: 'Alpha', tracks: [] }
				]
			}
		];
		expect(albumList(artists).map((c) => c.album)).toEqual(['ไทย', 'Alpha', 'beta']);
	});

	it('returns an empty list for an empty library', () => {
		expect(albumList([])).toEqual([]);
	});
});
```

Create `app/frontend/src/lib/libraryOptions.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { albumOptions, artistOptions, libraryMatches } from './libraryOptions';
import { LIBRARY } from './testData';

describe('artistOptions', () => {
	it('lists every library artist with a track count hint', () => {
		expect(artistOptions(LIBRARY)).toEqual([
			{ value: 'Linkin Park', label: 'Linkin Park', hint: '3 เพลง' },
			{ value: 'Sade', label: 'Sade', hint: '1 เพลง' }
		]);
	});

	it('puts a new YouTube guess first', () => {
		const out = artistOptions(LIBRARY, 'Linkin Park, Jay-Z');
		expect(out[0]).toEqual({ value: 'Linkin Park, Jay-Z', label: 'Linkin Park, Jay-Z', hint: 'ชื่อจาก YouTube' });
		expect(out).toHaveLength(3);
	});

	it('skips the guess when it is already a library artist', () => {
		expect(artistOptions(LIBRARY, ' sade ').map((o) => o.value)).toEqual(['Linkin Park', 'Sade']);
	});
});

describe('albumOptions', () => {
	it('lists the albums of the artist, ignoring case', () => {
		expect(albumOptions(LIBRARY, 'linkin park')).toEqual([
			{ value: 'Meteora', label: 'Meteora', hint: '2 เพลง' },
			{ value: 'Singles', label: 'Singles', hint: '1 เพลง' }
		]);
	});

	it('is empty for a new artist', () => {
		expect(albumOptions(LIBRARY, 'Nobody')).toEqual([]);
	});
});

describe('libraryMatches', () => {
	it('finds artists first, then track titles, without duplicates', () => {
		expect(libraryMatches(LIBRARY, 'numb')).toEqual(['Numb']);
		expect(libraryMatches(LIBRARY, 'a')).toEqual(['Linkin Park', 'Sade', 'Faint']);
	});

	it('needs at least one non-space character', () => {
		expect(libraryMatches(LIBRARY, '  ')).toEqual([]);
	});
});
```

Create `app/frontend/src/lib/searchPages.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { MAX_PAGES, knownLastPage, pageNumbers } from './searchPages';

const page = (n: number, has_more: boolean) => ({
	kind: 'search' as const,
	playlist_title: null,
	results: [],
	page: n,
	has_more
});

describe('searchPages', () => {
	it('allows every page until one says there is no more', () => {
		expect(knownLastPage([])).toBe(MAX_PAGES);
		expect(knownLastPage([page(1, true), page(2, true)])).toBe(MAX_PAGES);
	});

	it('stops at the first page without more', () => {
		expect(knownLastPage([page(1, true), page(3, false)])).toBe(3);
		expect(knownLastPage([page(4, false), page(2, false)])).toBe(2);
	});

	it('numbers the pages from 1 to the last one', () => {
		expect(pageNumbers(5)).toEqual([1, 2, 3, 4, 5]);
		expect(pageNumbers(1)).toEqual([1]);
	});
});
```

Modify `app/frontend/src/lib/api.test.ts` (apply with `git apply` from the repo root, or edit by hand):

```diff
diff --git a/app/frontend/src/lib/api.test.ts b/app/frontend/src/lib/api.test.ts
index 251571f..e15f864 100644
--- a/app/frontend/src/lib/api.test.ts
+++ b/app/frontend/src/lib/api.test.ts
@@ -14,13 +14,28 @@ function fakeFetch(status: number, body: unknown) {
 }
 
 describe('createApi', () => {
-	it('encodes the search query', async () => {
-		const { fn, calls } = fakeFetch(200, { kind: 'search', playlist_title: null, results: [] });
+	it('encodes the search query and asks for page 1 by default', async () => {
+		const { fn, calls } = fakeFetch(200, { kind: 'search', playlist_title: null, results: [], page: 1, has_more: true });
 		const out = await createApi(fn).search('numb linkin park');
-		expect(calls[0].url).toBe('/api/search?q=numb%20linkin%20park');
+		expect(calls[0].url).toBe('/api/search?q=numb%20linkin%20park&page=1');
 		expect(out.kind).toBe('search');
 	});
 
+	it('asks for another search page', async () => {
+		const { fn, calls } = fakeFetch(200, { kind: 'search', playlist_title: null, results: [], page: 3, has_more: true });
+		await createApi(fn).search('numb', 3);
+		expect(calls[0].url).toBe('/api/search?q=numb&page=3');
+	});
+
+	it('passes the abort signal to suggest', async () => {
+		const { fn, calls } = fakeFetch(200, { suggestions: ['เพลงไทย'] });
+		const ctrl = new AbortController();
+		const out = await createApi(fn).suggest('เพลง', ctrl.signal);
+		expect(calls[0].url).toBe(`/api/suggest?q=${encodeURIComponent('เพลง')}`);
+		expect(calls[0].init?.signal).toBe(ctrl.signal);
+		expect(out.suggestions).toEqual(['เพลงไทย']);
+	});
+
 	it('posts jobs as JSON', async () => {
 		const { fn, calls } = fakeFetch(201, { created: [], skipped: [] });
 		const item = { video_id: 'kXYiU_JCYtU', title: 'Numb', artist: 'Linkin Park', album: 'Singles' };
```

- [ ] **Step 2: Run the tests and see them fail**

Run: `npx vitest run src/lib`
Expected: the four new test files fail with `Failed to resolve import` (for example `./artistMatch`), and `api.test.ts` fails on the `&page=1` URL and on `suggest is not a function`.

- [ ] **Step 3: Write the code**

Create `app/frontend/src/lib/artistMatch.ts`:

```ts
/** After a library name, the rest of a YouTube artist guess must start with one of these. */
const SEPARATOR = /^(\s*[,&/]|\s+(x|feat\.?|ft\.?|with|and)\s)/i;

/**
 * Prefill the artist with a name already in the library when the YouTube guess is that
 * artist plus guests ("The Weeknd, JENNIE & Lily Rose Depp" -> "The Weeknd").
 * Exact match first (case-insensitive), then the longest library name followed by a separator.
 */
export function matchArtist(suggested: string, names: string[]): string {
	const guess = suggested.trim();
	const lower = guess.toLowerCase();
	const exact = names.find((n) => n.trim() && n.trim().toLowerCase() === lower);
	if (exact) return exact;
	let best = '';
	for (const name of names) {
		const n = name.trim().toLowerCase();
		if (!n || n.length <= best.trim().length) continue;
		if (lower.startsWith(n) && SEPARATOR.test(guess.slice(n.length))) best = name;
	}
	return best || suggested;
}
```

Create `app/frontend/src/lib/albumList.ts`:

```ts
import type { LibraryArtist, LibraryTrack } from './types';

/** One album of one artist, for the library album view. */
export type AlbumCard = { key: string; album: string; artist: string; tracks: LibraryTrack[] };

const compare = (a: string, b: string) => a.localeCompare(b, 'th', { sensitivity: 'base' });

/** Flatten the artist tree into album cards, sorted by album name, then artist name. */
export function albumList(artists: LibraryArtist[]): AlbumCard[] {
	const cards = artists.flatMap((a) =>
		a.albums.map((al) => ({
			key: JSON.stringify([a.artist, al.album]),
			album: al.album,
			artist: a.artist,
			tracks: al.tracks
		}))
	);
	return cards.sort((x, y) => compare(x.album, y.album) || compare(x.artist, y.artist));
}
```

Create `app/frontend/src/lib/libraryOptions.ts`:

```ts
import type { ComboOption, LibraryArtist } from './types';

const fold = (s: string) => s.trim().toLowerCase();
const count = (n: number) => `${n} เพลง`;

/** Artist combobox rows: every library artist, plus the YouTube guess on top when it is not one of them. */
export function artistOptions(artists: LibraryArtist[], youtubeGuess?: string): ComboOption[] {
	const rows: ComboOption[] = artists.map((a) => ({
		value: a.artist,
		label: a.artist,
		hint: count(a.albums.reduce((n, al) => n + al.tracks.length, 0))
	}));
	const guess = youtubeGuess?.trim();
	if (guess && !artists.some((a) => fold(a.artist) === fold(guess))) {
		rows.unshift({ value: guess, label: guess, hint: 'ชื่อจาก YouTube' });
	}
	return rows;
}

/** Album combobox rows: the albums of the artist named in the artist field (empty for a new artist). */
export function albumOptions(artists: LibraryArtist[], artist: string): ComboOption[] {
	const albums = artists.find((a) => fold(a.artist) === fold(artist))?.albums ?? [];
	return albums.map((al) => ({ value: al.album, label: al.album, hint: count(al.tracks.length) }));
}

/** Search-box rows from the library: artist names first, then track titles. */
export function libraryMatches(artists: LibraryArtist[], typed: string, limit = 3): string[] {
	const needle = fold(typed);
	if (!needle) return [];
	const out: string[] = [];
	const add = (s: string) => {
		if (out.length < limit && fold(s).includes(needle) && !out.some((o) => fold(o) === fold(s))) out.push(s);
	};
	for (const a of artists) add(a.artist);
	for (const a of artists) for (const al of a.albums) for (const t of al.tracks) add(t.title);
	return out;
}
```

Create `app/frontend/src/lib/searchPages.ts`:

```ts
import type { SearchResponse } from './types';

/** Matches MAX_PAGES in app/backend/wyc_music_streaming/search.py. */
export const MAX_PAGES = 5;

/** The last page worth offering: MAX_PAGES until a fetched page says has_more=false. */
export function knownLastPage(pages: Iterable<SearchResponse>): number {
	let last = MAX_PAGES;
	for (const p of pages) if (!p.has_more) last = Math.min(last, p.page);
	return last;
}

export function pageNumbers(last: number): number[] {
	return Array.from({ length: last }, (_, i) => i + 1);
}
```

Modify `app/frontend/src/lib/types.ts` (apply with `git apply` from the repo root, or edit by hand):

```diff
diff --git a/app/frontend/src/lib/types.ts b/app/frontend/src/lib/types.ts
index fc2eb10..3d1d82f 100644
--- a/app/frontend/src/lib/types.ts
+++ b/app/frontend/src/lib/types.ts
@@ -18,6 +18,8 @@ export type SearchResponse = {
 	kind: 'search' | 'url' | 'playlist';
 	playlist_title: string | null;
 	results: SearchResult[];
+	page: number;
+	has_more: boolean;
 };
 
 export type JobStatus = 'queued' | 'downloading' | 'done' | 'failed' | 'cancelled';
@@ -71,3 +73,6 @@ export type LibraryTrack = {
 export type LibraryAlbum = { album: string; tracks: LibraryTrack[] };
 
 export type LibraryArtist = { artist: string; albums: LibraryAlbum[] };
+
+/** One row of a Combobox popup. */
+export type ComboOption = { value: string; label: string; hint?: string };
```

Modify `app/frontend/src/lib/api.ts` (apply with `git apply` from the repo root, or edit by hand):

```diff
diff --git a/app/frontend/src/lib/api.ts b/app/frontend/src/lib/api.ts
index 669423a..e554848 100644
--- a/app/frontend/src/lib/api.ts
+++ b/app/frontend/src/lib/api.ts
@@ -26,8 +26,9 @@ export function createApi(
 	fetchFn: FetchFn = (input, init) => fetch(input, init),
 	onDenied: (info: DeniedInfo) => void = () => {}
 ) {
-	async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
+	async function request<T>(method: string, path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
 		const init: RequestInit = { method };
+		if (signal) init.signal = signal;
 		if (body !== undefined) {
 			init.headers = { 'Content-Type': 'application/json' };
 			init.body = JSON.stringify(body);
@@ -51,7 +52,10 @@ export function createApi(
 
 	return {
 		me: () => request<Me>('GET', '/me'),
-		search: (q: string) => request<SearchResponse>('GET', `/search?q=${encodeURIComponent(q)}`),
+		search: (q: string, page = 1) =>
+			request<SearchResponse>('GET', `/search?q=${encodeURIComponent(q)}&page=${page}`),
+		suggest: (q: string, signal?: AbortSignal) =>
+			request<{ suggestions: string[] }>('GET', `/suggest?q=${encodeURIComponent(q)}`, undefined, signal),
 		createJobs: (items: JobItem[]) => request<CreateJobsResponse>('POST', '/jobs', { items }),
 		listJobs: () => request<{ jobs: Job[] }>('GET', '/jobs'),
 		cancelJob: (id: number) => request<void>('DELETE', `/jobs/${id}`),
```

- [ ] **Step 4: Run the tests and see them pass**

Run: `npx vitest run && npm run check`
Expected: all tests pass; svelte-check 0 errors 0 warnings.

- [ ] **Step 5: Commit**

```bash
git add app/frontend/src/lib/artistMatch.ts \
  app/frontend/src/lib/artistMatch.test.ts \
  app/frontend/src/lib/albumList.ts \
  app/frontend/src/lib/albumList.test.ts \
  app/frontend/src/lib/libraryOptions.ts \
  app/frontend/src/lib/libraryOptions.test.ts \
  app/frontend/src/lib/searchPages.ts \
  app/frontend/src/lib/searchPages.test.ts \
  app/frontend/src/lib/types.ts \
  app/frontend/src/lib/api.ts \
  app/frontend/src/lib/api.test.ts
git commit -m "feat(frontend): add artist match, album list, search pages and suggest client"
```

### Task 4: Combobox component

**Files:**
- Create: `app/frontend/src/lib/components/Combobox.svelte`, `app/frontend/src/lib/components/Combobox.test.ts`

**Interfaces:**
- Consumes: `ComboOption` from `types.ts`.
- Produces: `<Combobox bind:value options label hideLabel? placeholder? maxlength? createLabel? filter? onpick? />`
  - `value: string` (bindable), `options: ComboOption[]`, `label: string` (a real `<label for>`; `hideLabel` makes it `sr-only`)
  - `createLabel: string | null`: adds a last row `+ <createLabel> "<text>"` when the text matches no option value
  - `filter: boolean`: filters options by label, but only after the user types (focus shows them all)
  - `onpick(value: string)`: called after a row is picked (mouse or Enter)

Keys: ArrowDown/ArrowUp move the active row (wrapping), Enter picks the active row (and only then prevents the form submit), Escape closes. Rows keep the input focused with `preventDefault` on `mousedown`, so keyboard handling stays on the input (`aria-activedescendant`).

- [ ] **Step 1: Write the failing tests**

Create `app/frontend/src/lib/components/Combobox.test.ts`:

```ts
import { fireEvent, render, screen } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import Combobox from './Combobox.svelte';

const options = [
	{ value: 'Linkin Park', label: 'Linkin Park', hint: '3 เพลง' },
	{ value: 'Sade', label: 'Sade' }
];

function setup(props: Record<string, unknown> = {}) {
	const onpick = vi.fn();
	render(Combobox, { value: '', options, label: 'ศิลปิน', onpick, ...props });
	return { onpick, input: screen.getByRole('combobox', { name: 'ศิลปิน' }) as HTMLInputElement };
}

describe('Combobox', () => {
	it('opens the list on focus and wires the ARIA attributes', async () => {
		const { input } = setup();
		expect(input).toHaveAttribute('aria-expanded', 'false');
		await fireEvent.focus(input);
		const list = screen.getByRole('listbox');
		expect(input).toHaveAttribute('aria-expanded', 'true');
		expect(input).toHaveAttribute('aria-controls', list.id);
		const text = screen.getAllByRole('option').map((o) => o.textContent?.replace(/\s+/g, ' ').trim());
		expect(text).toEqual(['Linkin Park 3 เพลง', 'Sade']);
	});

	it('moves with the arrow keys and picks with Enter', async () => {
		const { input, onpick } = setup();
		await fireEvent.focus(input);
		await fireEvent.keyDown(input, { key: 'ArrowDown' });
		await fireEvent.keyDown(input, { key: 'ArrowDown' });
		const active = screen.getAllByRole('option')[1];
		expect(active).toHaveAttribute('aria-selected', 'true');
		expect(input).toHaveAttribute('aria-activedescendant', active.id);
		await fireEvent.keyDown(input, { key: 'Enter' });
		expect(onpick).toHaveBeenCalledWith('Sade');
		expect(input.value).toBe('Sade');
		expect(screen.queryByRole('listbox')).toBeNull();
	});

	it('wraps from the top to the last row with ArrowUp', async () => {
		const { input } = setup();
		await fireEvent.focus(input);
		await fireEvent.keyDown(input, { key: 'ArrowUp' });
		expect(screen.getAllByRole('option')[1]).toHaveAttribute('aria-selected', 'true');
	});

	it('closes on Escape', async () => {
		const { input } = setup();
		await fireEvent.focus(input);
		await fireEvent.keyDown(input, { key: 'Escape' });
		expect(screen.queryByRole('listbox')).toBeNull();
	});

	it('picks a row with the mouse', async () => {
		const { input, onpick } = setup();
		await fireEvent.focus(input);
		await fireEvent.click(screen.getByRole('option', { name: /Linkin Park/ }));
		expect(onpick).toHaveBeenCalledWith('Linkin Park');
		expect(input.value).toBe('Linkin Park');
	});

	it('offers a create row only for new text', async () => {
		const { input, onpick } = setup({ createLabel: 'สร้างใหม่' });
		await fireEvent.input(input, { target: { value: 'The Weeknd' } });
		const create = screen.getByRole('option', { name: '+ สร้างใหม่ "The Weeknd"' });
		await fireEvent.click(create);
		expect(onpick).toHaveBeenCalledWith('The Weeknd');
		await fireEvent.input(input, { target: { value: 'sade' } });
		expect(screen.queryByRole('option', { name: /สร้างใหม่/ })).toBeNull();
	});

	it('leaves Enter alone when no row is active', async () => {
		const { input, onpick } = setup();
		await fireEvent.focus(input);
		const event = new KeyboardEvent('keydown', { key: 'Enter', cancelable: true, bubbles: true });
		input.dispatchEvent(event);
		expect(event.defaultPrevented).toBe(false);
		expect(onpick).not.toHaveBeenCalled();
	});

	it('filters only after typing when filter is on', async () => {
		const { input } = setup({ value: 'Sade', filter: true });
		await fireEvent.focus(input);
		expect(screen.getAllByRole('option')).toHaveLength(2);
		await fireEvent.input(input, { target: { value: 'park' } });
		expect(screen.getAllByRole('option').map((o) => o.textContent?.replace(/\s+/g, ' ').trim())).toEqual([
			'Linkin Park 3 เพลง'
		]);
	});
});
```

- [ ] **Step 2: Run the tests and see them fail**

Run: `npx vitest run src/lib/components/Combobox.test.ts`
Expected: FAIL with `Failed to resolve import "./Combobox.svelte"`.

- [ ] **Step 3: Write the code**

Create `app/frontend/src/lib/components/Combobox.svelte`:

```svelte
<script lang="ts">
	import type { ComboOption } from '$lib/types';

	type Props = {
		value: string;
		options: ComboOption[];
		label: string;
		/** Show the label only to screen readers. */
		hideLabel?: boolean;
		placeholder?: string;
		maxlength?: number;
		/** When set, new text gets a last row "+ <createLabel> "<text>"". */
		createLabel?: string | null;
		/** Filter the options by the text, but only after the user types (focus shows them all). */
		filter?: boolean;
		onpick?: (value: string) => void;
	};
	let {
		value = $bindable(),
		options,
		label,
		hideLabel = false,
		placeholder,
		maxlength,
		createLabel = null,
		filter = false,
		onpick
	}: Props = $props();

	const uid = $props.id();
	let open = $state(false);
	let active = $state(-1);
	let typed = $state(false);

	const fold = (s: string) => s.trim().toLowerCase();
	const rows = $derived.by(() => {
		const text = value.trim();
		const shown = filter && typed ? options.filter((o) => fold(o.label).includes(fold(text))) : options;
		const isNew = createLabel && text && !options.some((o) => fold(o.value) === fold(text));
		return isNew ? [...shown, { value: text, label: `+ ${createLabel} "${text}"` }] : shown;
	});
	const showList = $derived(open && rows.length > 0);

	function pick(next: string) {
		value = next;
		open = false;
		active = -1;
		typed = false;
		onpick?.(next);
	}

	function onkeydown(event: KeyboardEvent) {
		if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
			event.preventDefault();
			if (!rows.length) return;
			open = true;
			const step = event.key === 'ArrowDown' ? 1 : -1;
			active = active < 0 && step < 0 ? rows.length - 1 : (active + step + rows.length) % rows.length;
		} else if (event.key === 'Enter' && showList && active >= 0) {
			event.preventDefault();
			pick(rows[active].value);
		} else if (event.key === 'Escape' && showList) {
			event.preventDefault();
			open = false;
			active = -1;
		}
	}
</script>

<div class={['relative', !hideLabel && 'space-y-1']}>
	<label for={uid} class={hideLabel ? 'sr-only' : 'label block'}>{label}</label>
	<input
		id={uid}
		class="input"
		role="combobox"
		autocomplete="off"
		aria-autocomplete="list"
		aria-expanded={showList}
		aria-controls={`${uid}-list`}
		aria-activedescendant={showList && active >= 0 ? `${uid}-opt-${active}` : undefined}
		bind:value
		{placeholder}
		{maxlength}
		onfocus={() => {
			open = true;
			typed = false;
		}}
		onblur={() => {
			open = false;
			active = -1;
		}}
		oninput={() => {
			open = true;
			active = -1;
			typed = true;
		}}
		{onkeydown}
	/>
	{#if showList}
		<ul id={`${uid}-list`} role="listbox" aria-label={label} class="card absolute inset-x-0 z-20 mt-1 max-h-64 overflow-auto p-1">
			{#each rows as row, i}
				<!-- Keys go through the input (aria-activedescendant), so the row needs no key handler.
				     preventDefault on mousedown keeps focus in the input. -->
				<!-- svelte-ignore a11y_click_events_have_key_events -->
				<li
					id={`${uid}-opt-${i}`}
					role="option"
					tabindex="-1"
					aria-selected={i === active}
					class={['flex cursor-pointer items-center justify-between gap-2 rounded px-2 py-1.5', i === active && 'bg-yellow']}
					onmousedown={(e) => e.preventDefault()}
					onclick={() => pick(row.value)}
				>
					<span class="truncate">{row.label}</span>
					{#if row.hint}<span class="shrink-0 font-mono text-xs text-muted">{row.hint}</span>{/if}
				</li>
			{/each}
		</ul>
	{/if}
</div>
```

- [ ] **Step 4: Run the tests and see them pass**

Run: `npx vitest run && npm run check`
Expected: all tests pass; svelte-check 0 errors 0 warnings.

- [ ] **Step 5: Commit**

```bash
git add app/frontend/src/lib/components/Combobox.svelte \
  app/frontend/src/lib/components/Combobox.test.ts
git commit -m "feat(frontend): add Combobox component"
```

### Task 5: Library artist and album in the tape label editor

**Files:**
- Modify: `app/frontend/src/lib/selection.ts`, `app/frontend/src/lib/selection.test.ts`, `app/frontend/src/lib/components/EditPanel.svelte`, `app/frontend/src/lib/components/EditPanel.test.ts`, `app/frontend/src/routes/+page.svelte`

**Interfaces:**
- Consumes: `matchArtist` (Task 3), `artistOptions`, `albumOptions` (Task 3), `Combobox` (Task 4).
- Produces: `draftFrom(result: SearchResult, libraryArtists: string[] = []): Draft` (artist prefilled by `matchArtist`).
- Produces: `EditPanel` props `artists?: LibraryArtist[]`, `youtubeArtist?: string` (shown as the first row, hint "ชื่อจาก YouTube", when the prefill differs from the guess).

- [ ] **Step 1: Write the failing tests**

Modify `app/frontend/src/lib/selection.test.ts` (apply with `git apply` from the repo root, or edit by hand):

```diff
diff --git a/app/frontend/src/lib/selection.test.ts b/app/frontend/src/lib/selection.test.ts
index 09a312c..ed16f16 100644
--- a/app/frontend/src/lib/selection.test.ts
+++ b/app/frontend/src/lib/selection.test.ts
@@ -16,6 +16,12 @@ describe('selection', () => {
 		expect(draftFrom(makeResult())).toEqual(draft);
 	});
 
+	it('prefills the artist with a library name when the guess has guests', () => {
+		const result = makeResult({ suggested: { title: 'Numb', artist: 'Linkin Park, Jay-Z', album: 'Singles' } });
+		expect(draftFrom(result, ['Linkin Park']).artist).toBe('Linkin Park');
+		expect(draftFrom(result).artist).toBe('Linkin Park, Jay-Z');
+	});
+
 	it('validates blank and long fields', () => {
 		expect(validateDraft(draft)).toBeNull();
 		expect(validateDraft({ ...draft, title: ' ' })).toBe('กรอกชื่อเพลงก่อน');
```

Modify `app/frontend/src/lib/components/EditPanel.test.ts` (apply with `git apply` from the repo root, or edit by hand):

```diff
diff --git a/app/frontend/src/lib/components/EditPanel.test.ts b/app/frontend/src/lib/components/EditPanel.test.ts
index d7a5a21..57d6446 100644
--- a/app/frontend/src/lib/components/EditPanel.test.ts
+++ b/app/frontend/src/lib/components/EditPanel.test.ts
@@ -1,5 +1,6 @@
 import { fireEvent, render, screen } from '@testing-library/svelte';
 import { describe, expect, it, vi } from 'vitest';
+import { LIBRARY } from '../testData';
 import EditPanel from './EditPanel.svelte';
 
 const draft = { video_id: 'kXYiU_JCYtU', title: 'Numb', artist: 'Linkin Park', album: 'Singles' };
@@ -29,4 +30,32 @@ describe('EditPanel', () => {
 		await fireEvent.click(screen.getByRole('button', { name: 'ยกเลิก' }));
 		expect(oncancel).toHaveBeenCalledOnce();
 	});
+
+	it('offers library artists and the albums of the chosen artist', async () => {
+		render(EditPanel, { draft, artists: LIBRARY, onsubmit: vi.fn(), oncancel: vi.fn() });
+		await fireEvent.focus(screen.getByLabelText('ศิลปิน'));
+		expect(screen.getAllByRole('option').map((o) => o.textContent?.replace(/\s+/g, ' ').trim())).toEqual([
+			'Linkin Park 3 เพลง',
+			'Sade 1 เพลง'
+		]);
+		await fireEvent.click(screen.getByRole('option', { name: /Sade/ }));
+		await fireEvent.focus(screen.getByLabelText('อัลบั้ม'));
+		expect(screen.getAllByRole('option').map((o) => o.textContent?.replace(/\s+/g, ' ').trim())).toEqual([
+			'Diamond Life 1 เพลง',
+			'+ สร้างใหม่ "Singles"'
+		]);
+	});
+
+	it('shows the YouTube guess when the prefill came from the library', async () => {
+		render(EditPanel, {
+			draft,
+			artists: LIBRARY,
+			youtubeArtist: 'Linkin Park, Jay-Z',
+			onsubmit: vi.fn(),
+			oncancel: vi.fn()
+		});
+		await fireEvent.focus(screen.getByLabelText('ศิลปิน'));
+		expect(screen.getAllByRole('option')[0]).toHaveTextContent('Linkin Park, Jay-Z');
+		expect(screen.getAllByRole('option')[0]).toHaveTextContent('ชื่อจาก YouTube');
+	});
 });
```

- [ ] **Step 2: Run the tests and see them fail**

Run: `npx vitest run src/lib/selection.test.ts src/lib/components/EditPanel.test.ts`
Expected: the new selection test fails (artist stays `Linkin Park, Jay-Z`), and the two new EditPanel tests fail with `Unable to find role="option"`.

- [ ] **Step 3: Write the code**

Modify `app/frontend/src/lib/selection.ts` (apply with `git apply` from the repo root, or edit by hand):

```diff
diff --git a/app/frontend/src/lib/selection.ts b/app/frontend/src/lib/selection.ts
index 0884cc7..fedb213 100644
--- a/app/frontend/src/lib/selection.ts
+++ b/app/frontend/src/lib/selection.ts
@@ -1,3 +1,4 @@
+import { matchArtist } from './artistMatch';
 import { isActive } from './jobList';
 import type { CreateJobsResponse, Job, JobItem, SearchResult } from './types';
 
@@ -13,8 +14,10 @@ const FIELDS = [
 	['album', 'อัลบั้ม']
 ] as const;
 
-export function draftFrom(result: SearchResult): Draft {
-	return { video_id: result.video_id, ...result.suggested };
+/** libraryArtists: names already in the library, used to prefill the artist (see matchArtist). */
+export function draftFrom(result: SearchResult, libraryArtists: string[] = []): Draft {
+	const { title, artist, album } = result.suggested;
+	return { video_id: result.video_id, title, artist: matchArtist(artist, libraryArtists), album };
 }
 
 /** null when the draft is valid, else one message for the user. Limits match the backend (300). */
```

Modify `app/frontend/src/lib/components/EditPanel.svelte` (apply with `git apply` from the repo root, or edit by hand):

```diff
diff --git a/app/frontend/src/lib/components/EditPanel.svelte b/app/frontend/src/lib/components/EditPanel.svelte
index 5e24625..92ccff8 100644
--- a/app/frontend/src/lib/components/EditPanel.svelte
+++ b/app/frontend/src/lib/components/EditPanel.svelte
@@ -1,20 +1,30 @@
 <script lang="ts">
+	import { albumOptions, artistOptions } from '$lib/libraryOptions';
 	import { validateDraft, type Draft } from '$lib/selection';
+	import type { LibraryArtist } from '$lib/types';
+	import Combobox from './Combobox.svelte';
 
 	type Props = {
 		draft: Draft;
+		/** The library tree, for the artist and album lists. */
+		artists?: LibraryArtist[];
+		/** The artist YouTube suggested, shown in the list when the prefill differs. */
+		youtubeArtist?: string;
 		busy?: boolean;
 		error?: string | null;
 		onsubmit: (draft: Draft) => void;
 		oncancel: () => void;
 	};
-	let { draft, busy = false, error = null, onsubmit, oncancel }: Props = $props();
+	let { draft, artists = [], youtubeArtist, busy = false, error = null, onsubmit, oncancel }: Props = $props();
 
 	// Writable deriveds: they reset when the parent passes a new draft.
 	let title = $derived(draft.title);
 	let artist = $derived(draft.artist);
 	let album = $derived(draft.album);
 
+	const artistRows = $derived(artistOptions(artists, youtubeArtist));
+	const albumRows = $derived(albumOptions(artists, artist));
+
 	const current = $derived({ video_id: draft.video_id, title, artist, album });
 	const problem = $derived(validateDraft(current));
 
@@ -30,14 +40,8 @@
 		<span class="label">ชื่อเพลง</span>
 		<input class="input" bind:value={title} maxlength="300" />
 	</label>
-	<label class="block space-y-1">
-		<span class="label">ศิลปิน</span>
-		<input class="input" bind:value={artist} maxlength="300" />
-	</label>
-	<label class="block space-y-1">
-		<span class="label">อัลบั้ม</span>
-		<input class="input" bind:value={album} maxlength="300" />
-	</label>
+	<Combobox bind:value={artist} options={artistRows} label="ศิลปิน" maxlength={300} createLabel="สร้างใหม่" filter />
+	<Combobox bind:value={album} options={albumRows} label="อัลบั้ม" maxlength={300} createLabel="สร้างใหม่" filter />
 	{#if problem}
 		<p role="alert" class="text-sm text-orange">{problem}</p>
 	{/if}
```

Modify `app/frontend/src/routes/+page.svelte` (apply with `git apply` from the repo root, or edit by hand):

```diff
diff --git a/app/frontend/src/routes/+page.svelte b/app/frontend/src/routes/+page.svelte
index ddefc07..5a2c613 100644
--- a/app/frontend/src/routes/+page.svelte
+++ b/app/frontend/src/routes/+page.svelte
@@ -37,6 +37,13 @@
 	let editorBox = $state<HTMLElement | null>(null);
 
 	const placeholder = $derived(TABS.find((t) => t.id === tab)!.placeholder);
+	const artistNames = $derived(library.artists.map((a) => a.artist));
+	// The YouTube guess, only when the editor was prefilled with a different library name.
+	const youtubeArtist = $derived.by(() => {
+		if (!editing) return undefined;
+		const guess = response?.results.find((r) => r.video_id === editing!.video_id)?.suggested.artist;
+		return guess && guess !== editing.artist ? guess : undefined;
+	});
 	const isPlaylist = $derived(response?.kind === 'playlist');
 
 	// The editor sits above the results: bring it into view when a card far down opens it.
@@ -76,7 +83,7 @@
 				picked = defaultSelection(res.results, library.videoIds);
 				batchAlbum = res.playlist_title ?? '';
 			} else if (res.kind === 'url' && res.results.length === 1 && stateOf(res.results[0].video_id) === 'new') {
-				editing = draftFrom(res.results[0]);
+				editing = draftFrom(res.results[0], artistNames);
 			}
 		} catch (e) {
 			searchError = errorText(e);
@@ -108,7 +115,7 @@
 		if (!response) return;
 		const items = response.results
 			.filter((r) => picked.includes(r.video_id))
-			.map((r) => toJobItem(draftFrom(r), batchAlbum));
+			.map((r) => toJobItem(draftFrom(r, artistNames), batchAlbum));
 		if (items.length) void send(items);
 	}
 </script>
@@ -146,6 +153,8 @@
 			<div bind:this={editorBox} class="scroll-mt-4">
 				<EditPanel
 					draft={editing}
+					artists={library.artists}
+					{youtubeArtist}
 					busy={sending}
 					error={sendError}
 					onsubmit={(d) => void send([toJobItem(d)])}
@@ -189,7 +198,7 @@
 							ondownload={() => {
 								notice = null;
 								sendError = null;
-								editing = draftFrom(result);
+								editing = draftFrom(result, artistNames);
 							}}
 						/>
 					{/each}
```

- [ ] **Step 4: Run the tests and see them pass**

Run: `npx vitest run && npm run check`
Expected: all tests pass; svelte-check 0 errors 0 warnings.

- [ ] **Step 5: Commit**

```bash
git add app/frontend/src/lib/selection.ts \
  app/frontend/src/lib/selection.test.ts \
  app/frontend/src/lib/components/EditPanel.svelte \
  app/frontend/src/lib/components/EditPanel.test.ts \
  app/frontend/src/routes/+page.svelte
git commit -m "feat(frontend): pick artist and album from the library in the tape label editor"
```

### Task 6: Search pages and typing suggestions

**Files:**
- Create: `app/frontend/src/lib/components/Pager.svelte`, `app/frontend/src/lib/components/Pager.test.ts`
- Modify: `app/frontend/src/routes/+page.svelte`

**Interfaces:**
- Consumes: `pageNumbers`, `knownLastPage` (Task 3), `libraryMatches` (Task 3), `api.search(q, page)`, `api.suggest(q, signal)` (Task 3), `Combobox` (Task 4).
- Produces: `<Pager page last busy? ongo />` with `ongo(page: number)`; the current page has `aria-current="page"`.

How the search page works after this task:
- `startSearch(text)` clears the page cache (`SvelteMap<number, SearchResponse>`), fetches page 1 and stores it. `goPage(n)` uses the cache or fetches, then scrolls to the top of the results.
- The pager shows only for `kind: "search"` and only when `knownLastPage > 1`.
- A `$effect` fetches suggestions 250 ms after typing stops (2+ chars, song tab, text differs from the last search), aborting the previous request. Rows: YouTube first, then up to 3 library matches with hint "มีแล้ว". Picking a row runs the search. The list is empty while the text equals the last search, so it closes after a search.

- [ ] **Step 1: Write the failing tests**

Create `app/frontend/src/lib/components/Pager.test.ts`:

```ts
import { fireEvent, render, screen } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import Pager from './Pager.svelte';

describe('Pager', () => {
	it('shows each page and marks the current one', () => {
		render(Pager, { page: 2, last: 5, ongo: vi.fn() });
		const numbers = ['1', '2', '3', '4', '5'].map((n) => screen.getByRole('button', { name: n }));
		expect(numbers[1]).toHaveAttribute('aria-current', 'page');
		expect(numbers[0]).not.toHaveAttribute('aria-current');
	});

	it('goes to the clicked, previous and next page', async () => {
		const ongo = vi.fn();
		render(Pager, { page: 2, last: 5, ongo });
		await fireEvent.click(screen.getByRole('button', { name: '4' }));
		await fireEvent.click(screen.getByRole('button', { name: '« ก่อน' }));
		await fireEvent.click(screen.getByRole('button', { name: 'ถัดไป »' }));
		expect(ongo.mock.calls).toEqual([[4], [1], [3]]);
	});

	it('does nothing on the current page', async () => {
		const ongo = vi.fn();
		render(Pager, { page: 2, last: 5, ongo });
		await fireEvent.click(screen.getByRole('button', { name: '2' }));
		expect(ongo).not.toHaveBeenCalled();
	});

	it('disables previous on the first page and next on the last page', () => {
		render(Pager, { page: 1, last: 1, ongo: vi.fn() });
		expect(screen.getByRole('button', { name: '« ก่อน' })).toBeDisabled();
		expect(screen.getByRole('button', { name: 'ถัดไป »' })).toBeDisabled();
	});

	it('disables every button while a page loads', () => {
		render(Pager, { page: 2, last: 3, busy: true, ongo: vi.fn() });
		for (const button of screen.getAllByRole('button')) expect(button).toBeDisabled();
	});
});
```

- [ ] **Step 2: Run the tests and see them fail**

Run: `npx vitest run src/lib/components/Pager.test.ts`
Expected: FAIL with `Failed to resolve import "./Pager.svelte"`.

- [ ] **Step 3: Write the code**

Create `app/frontend/src/lib/components/Pager.svelte`:

```svelte
<script lang="ts">
	import { pageNumbers } from '$lib/searchPages';

	type Props = { page: number; last: number; busy?: boolean; ongo: (page: number) => void };
	let { page, last, busy = false, ongo }: Props = $props();
</script>

<nav aria-label="หน้าผลค้นหา" class="flex flex-wrap items-center justify-center gap-2">
	<button class="btn" disabled={busy || page <= 1} onclick={() => ongo(page - 1)}>« ก่อน</button>
	{#each pageNumbers(last) as n (n)}
		<button
			class={['btn font-mono', n === page && 'btn-teal']}
			aria-current={n === page ? 'page' : undefined}
			disabled={busy}
			onclick={() => n !== page && ongo(n)}
		>
			{n}
		</button>
	{/each}
	<button class="btn" disabled={busy || page >= last} onclick={() => ongo(page + 1)}>ถัดไป »</button>
</nav>
```

Modify `app/frontend/src/routes/+page.svelte` (apply with `git apply` from the repo root, or edit by hand):

```diff
diff --git a/app/frontend/src/routes/+page.svelte b/app/frontend/src/routes/+page.svelte
index 5a2c613..c4f93aa 100644
--- a/app/frontend/src/routes/+page.svelte
+++ b/app/frontend/src/routes/+page.svelte
@@ -1,11 +1,16 @@
 <script lang="ts">
+	import { SvelteMap } from 'svelte/reactivity';
 	import { api } from '$lib/client';
 	import CassetteDeck from '$lib/components/CassetteDeck.svelte';
+	import Combobox from '$lib/components/Combobox.svelte';
 	import EditPanel from '$lib/components/EditPanel.svelte';
+	import Pager from '$lib/components/Pager.svelte';
 	import ResultCard from '$lib/components/ResultCard.svelte';
 	import { errorText } from '$lib/format';
 	import { jobs } from '$lib/jobs.svelte';
 	import { library } from '$lib/library.svelte';
+	import { libraryMatches } from '$lib/libraryOptions';
+	import { knownLastPage } from '$lib/searchPages';
 	import {
 		cardState,
 		defaultSelection,
@@ -14,7 +19,7 @@
 		toJobItem,
 		type Draft
 	} from '$lib/selection';
-	import type { JobItem, SearchResponse } from '$lib/types';
+	import type { ComboOption, JobItem, SearchResponse } from '$lib/types';
 
 	type Tab = 'song' | 'link';
 	const TABS: { id: Tab; label: string; placeholder: string }[] = [
@@ -34,7 +39,19 @@
 	let picked = $state<string[]>([]);
 	let batchAlbum = $state('');
 
+	// Text search pages: one query at a time, fetched pages kept until the next query.
+	let query = $state('');
+	let page = $state(1);
+	let paging = $state(false);
+	const pages = new SvelteMap<number, SearchResponse>();
+	const lastPage = $derived(knownLastPage(pages.values()));
+
+	// Suggestions while typing (song tab only).
+	let suggestions = $state<string[]>([]);
+	let suggestCtrl: AbortController | null = null;
+
 	let editorBox = $state<HTMLElement | null>(null);
+	let resultsTop = $state<HTMLElement | null>(null);
 
 	const placeholder = $derived(TABS.find((t) => t.id === tab)!.placeholder);
 	const artistNames = $derived(library.artists.map((a) => a.artist));
@@ -53,6 +70,36 @@
 		editorBox.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' });
 	});
 
+	$effect(() => {
+		const text = q.trim();
+		suggestCtrl?.abort();
+		if (tab !== 'song' || text.length < 2 || text === query) {
+			suggestions = [];
+			return;
+		}
+		const timer = setTimeout(async () => {
+			const ctrl = new AbortController();
+			suggestCtrl = ctrl;
+			try {
+				const res = await api.suggest(text, ctrl.signal);
+				if (suggestCtrl === ctrl) suggestions = res.suggestions;
+			} catch {
+				// Suggestions are optional: ignore aborts and errors.
+			}
+		}, 250);
+		return () => clearTimeout(timer);
+	});
+
+	const fold = (s: string) => s.trim().toLowerCase();
+	const suggestRows = $derived.by((): ComboOption[] => {
+		if (tab !== 'song' || q.trim() === query) return [];
+		const fromYoutube = suggestions.map((s) => ({ value: s, label: s }));
+		const owned = libraryMatches(library.artists, q)
+			.filter((m) => !suggestions.some((s) => fold(s) === fold(m)))
+			.map((m) => ({ value: m, label: m, hint: 'มีแล้ว' }));
+		return [...fromYoutube, ...owned];
+	});
+
 	function stateOf(videoId: string) {
 		return cardState(videoId, library.videoIds, jobs.list);
 	}
@@ -62,14 +109,22 @@
 		searchError = null;
 	}
 
-	async function runSearch(event: SubmitEvent) {
+	function runSearch(event: SubmitEvent) {
 		event.preventDefault();
-		const query = q.trim();
-		if (!query || searching) return;
-		if (tab === 'link' && !/^https?:\/\//i.test(query)) {
+		void startSearch(q);
+	}
+
+	async function startSearch(text: string) {
+		const wanted = text.trim();
+		if (!wanted || searching) return;
+		if (tab === 'link' && !/^https?:\/\//i.test(wanted)) {
 			searchError = 'วางลิงก์ที่ขึ้นต้นด้วย https://';
 			return;
 		}
+		q = wanted;
+		query = wanted;
+		page = 1;
+		pages.clear();
 		searching = true;
 		searchError = null;
 		notice = null;
@@ -77,7 +132,8 @@
 		editing = null;
 		response = null;
 		try {
-			const res = await api.search(query);
+			const res = await api.search(wanted);
+			pages.set(1, res);
 			response = res;
 			if (res.kind === 'playlist') {
 				picked = defaultSelection(res.results, library.videoIds);
@@ -92,6 +148,33 @@
 		}
 	}
 
+	async function goPage(n: number) {
+		if (paging || n === page || n < 1 || n > lastPage) return;
+		searchError = null;
+		const cached = pages.get(n);
+		if (cached) {
+			showPage(n, cached);
+			return;
+		}
+		paging = true;
+		try {
+			const res = await api.search(query, n);
+			pages.set(n, res);
+			showPage(n, res);
+		} catch (e) {
+			searchError = errorText(e);
+		} finally {
+			paging = false;
+		}
+	}
+
+	function showPage(n: number, res: SearchResponse) {
+		page = n;
+		response = res;
+		const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
+		resultsTop?.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' });
+	}
+
 	async function send(items: JobItem[]) {
 		sending = true;
 		sendError = null;
@@ -135,8 +218,22 @@
 			{/each}
 		</div>
 
-		<form class="flex gap-2" onsubmit={runSearch}>
-			<input class="input" bind:value={q} {placeholder} aria-label={placeholder} maxlength="500" />
+		<form class="flex items-start gap-2" onsubmit={runSearch}>
+			<div class="min-w-0 flex-1">
+				{#if tab === 'song'}
+					<Combobox
+						bind:value={q}
+						options={suggestRows}
+						label={placeholder}
+						hideLabel
+						{placeholder}
+						maxlength={500}
+						onpick={(text) => void startSearch(text)}
+					/>
+				{:else}
+					<input class="input" bind:value={q} {placeholder} aria-label={placeholder} maxlength="500" />
+				{/if}
+			</div>
 			<button class="btn btn-primary shrink-0" type="submit" disabled={searching || !q.trim()}>
 				{searching ? 'กำลังหา…' : 'ค้นหา'}
 			</button>
@@ -183,6 +280,7 @@
 			</div>
 		{/if}
 
+		<div bind:this={resultsTop} class="scroll-mt-4"></div>
 		{#if response}
 			{#if response.results.length === 0}
 				<p class="text-muted">ไม่พบเพลง</p>
@@ -204,6 +302,9 @@
 					{/each}
 				</ul>
 			{/if}
+			{#if response.kind === 'search' && lastPage > 1}
+				<Pager {page} last={lastPage} busy={paging} ongo={(n) => void goPage(n)} />
+			{/if}
 		{/if}
 	</section>
 
```

- [ ] **Step 4: Run the tests and see them pass**

Run: `npx vitest run && npm run check`
Expected: all tests pass; svelte-check 0 errors 0 warnings.

- [ ] **Step 5: Commit**

```bash
git add app/frontend/src/lib/components/Pager.svelte \
  app/frontend/src/lib/components/Pager.test.ts \
  app/frontend/src/routes/+page.svelte
git commit -m "feat(frontend): add search pages and typing suggestions"
```

### Task 7: Library view by album

**Files:**
- Create: `app/frontend/src/lib/components/AlbumGrid.svelte`, `app/frontend/src/lib/components/AlbumGrid.test.ts`
- Modify: `app/frontend/src/routes/library/+page.svelte`

**Interfaces:**
- Consumes: `albumList`, `AlbumCard` (Task 3), `TrackRow`, `filterLibrary`, `page` from `$app/state`.
- Produces: `<AlbumGrid cards ondelete />`; one card open at a time; the open card spans the full row.
- The view lives in the URL: `/library` (artists) and `/library?view=albums`. The toggle is two links, so reload and back keep the view.

- [ ] **Step 1: Write the failing tests**

Create `app/frontend/src/lib/components/AlbumGrid.test.ts`:

```ts
import { fireEvent, render, screen } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import { albumList } from '../albumList';
import { LIBRARY } from '../testData';
import AlbumGrid from './AlbumGrid.svelte';

const cards = albumList(LIBRARY);

describe('AlbumGrid', () => {
	it('shows one closed card per album', () => {
		render(AlbumGrid, { cards, ondelete: vi.fn() });
		const buttons = screen.getAllByRole('button', { expanded: false });
		expect(buttons).toHaveLength(3);
		expect(buttons[1]).toHaveTextContent('Meteora');
		expect(buttons[1]).toHaveTextContent('Linkin Park');
		expect(buttons[1]).toHaveTextContent('2 เพลง');
		expect(screen.queryByText('Faint')).toBeNull();
	});

	it('opens one card at a time', async () => {
		render(AlbumGrid, { cards, ondelete: vi.fn() });
		await fireEvent.click(screen.getByRole('button', { name: /Meteora/ }));
		expect(screen.getByRole('button', { name: /Meteora/ })).toHaveAttribute('aria-expanded', 'true');
		expect(screen.getByText('Faint')).toBeInTheDocument();
		await fireEvent.click(screen.getByRole('button', { name: /Diamond Life/ }));
		expect(screen.queryByText('Faint')).toBeNull();
		expect(screen.getByText('Smooth Operator')).toBeInTheDocument();
		await fireEvent.click(screen.getByRole('button', { name: /Diamond Life/ }));
		expect(screen.queryByText('Smooth Operator')).toBeNull();
	});

	it('deletes through the track row', async () => {
		const ondelete = vi.fn();
		render(AlbumGrid, { cards, ondelete });
		await fireEvent.click(screen.getByRole('button', { name: /Diamond Life/ }));
		await fireEvent.click(screen.getByRole('button', { name: 'ลบ Smooth Operator' }));
		await fireEvent.click(screen.getByRole('button', { name: 'ลบเลย' }));
		expect(ondelete).toHaveBeenCalledWith('Sade/Diamond_Life/Smooth_Operator.m4a');
	});
});
```

- [ ] **Step 2: Run the tests and see them fail**

Run: `npx vitest run src/lib/components/AlbumGrid.test.ts`
Expected: FAIL with `Failed to resolve import "./AlbumGrid.svelte"`.

- [ ] **Step 3: Write the code**

Create `app/frontend/src/lib/components/AlbumGrid.svelte`:

```svelte
<script lang="ts">
	import type { AlbumCard } from '$lib/albumList';
	import TrackRow from './TrackRow.svelte';

	type Props = { cards: AlbumCard[]; ondelete: (path: string) => Promise<void> | void };
	let { cards, ondelete }: Props = $props();

	let open = $state<string | null>(null);
</script>

<ul class="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
	{#each cards as card, i (card.key)}
		{@const isOpen = open === card.key}
		<li class={['card', isOpen && 'sm:col-span-2 xl:col-span-3']}>
			<button
				class="flex w-full items-center gap-3 p-4 text-left"
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
index 8ecda13..e3d25f9 100644
--- a/app/frontend/src/routes/library/+page.svelte
+++ b/app/frontend/src/routes/library/+page.svelte
@@ -1,5 +1,8 @@
 <script lang="ts">
+	import { page } from '$app/state';
+	import { albumList } from '$lib/albumList';
 	import { api } from '$lib/client';
+	import AlbumGrid from '$lib/components/AlbumGrid.svelte';
 	import TrackRow from '$lib/components/TrackRow.svelte';
 	import { errorText } from '$lib/format';
 	import { library } from '$lib/library.svelte';
@@ -10,7 +13,14 @@
 	let notice = $state<string | null>(null);
 	let error = $state<string | null>(null);
 
+	const VIEWS = [
+		{ id: 'artists', label: 'ศิลปิน', href: '/library' },
+		{ id: 'albums', label: 'อัลบั้ม', href: '/library?view=albums' }
+	] as const;
+	const view = $derived(page.url.searchParams.get('view') === 'albums' ? 'albums' : 'artists');
+
 	const shown = $derived(filterLibrary(library.artists, filter));
+	const cards = $derived(view === 'albums' ? albumList(shown) : []);
 
 	async function remove(path: string) {
 		await api.deleteTrack(path);
@@ -49,6 +59,14 @@
 		</button>
 	</div>
 
+	<nav class="flex gap-2" aria-label="มุมมองคลังเพลง">
+		{#each VIEWS as v (v.id)}
+			<a href={v.href} class={['btn', view === v.id && 'btn-teal']} aria-current={view === v.id ? 'page' : undefined}>
+				{v.label}
+			</a>
+		{/each}
+	</nav>
+
 	<input class="input" bind:value={filter} placeholder="กรองตามศิลปิน อัลบั้ม หรือชื่อเพลง" aria-label="กรองคลังเพลง" />
 
 	{#if notice}
@@ -62,6 +80,8 @@
 		<p class="text-muted">กำลังโหลด…</p>
 	{:else if shown.length === 0}
 		<p class="text-muted">{filter.trim() ? 'ไม่พบเพลงที่ตรงกับคำค้น' : 'คลังยังว่าง ลองโหลดเพลงจากหน้าค้นหา'}</p>
+	{:else if view === 'albums'}
+		<AlbumGrid {cards} ondelete={remove} />
 	{:else}
 		<div class="grid gap-6 md:grid-cols-[200px_1fr]">
 			<nav class="hidden md:block" aria-label="ศิลปิน">
```

- [ ] **Step 4: Run the tests and see them pass**

Run: `npx vitest run && npm run check && npm run build`
Expected: 97 tests pass; svelte-check 0 errors 0 warnings; build writes `build/`.

- [ ] **Step 5: Commit**

```bash
git add app/frontend/src/lib/components/AlbumGrid.svelte \
  app/frontend/src/lib/components/AlbumGrid.test.ts \
  app/frontend/src/routes/library/+page.svelte
git commit -m "feat(frontend): add library view by album"
```

### Task 8: Deploy on the NAS and smoke test

The user runs these steps on the NAS (as `wick`). Push first, with the user's OK.

- [ ] **Step 1: Update and rebuild**

```bash
sudo /opt/wyc-music-streaming/repo/app/deploy/update.sh 2>&1 | tail -20
```

Expected: `Wrote site to "build"` and `active (running)`.

- [ ] **Step 2: Check the suggest route through the service**

```bash
sleep 5
curl -s -o /dev/null -w '%{http_code}\n' 'http://127.0.0.1:8097/api/suggest?q=numb'
```

Expected: `403` (no Tailscale identity on localhost), which shows the route exists.

- [ ] **Step 3: Smoke test from the phone and the laptop** (`https://wick-vpccw15fh.tail4810aa.ts.net/`)

1. Type "the weeknd b": suggestions appear; ArrowDown + Enter (or tap) runs the search.
2. The pager shows `1 2 3 4 5`; page 3 loads; page 1 comes back at once.
3. Open the editor on a feat. track of an artist you already have (for example "The Weeknd ft. ..."): the artist field shows "The Weeknd"; the list has the full YouTube name with "ชื่อจาก YouTube".
4. The album field lists that artist's albums; typing a new name shows "+ สร้างใหม่".
5. `/library` → "อัลบั้ม": cards per album; open one; delete still works; reload keeps `?view=albums`.
6. Phone width: the search box, the list and the pager fit without side scrolling.

- [ ] **Step 4: Record the result**

Add the date and the results under §11 of the base spec, then:

```bash
git add docs/superpowers/specs/2026-11-05-wyc-music-streaming-design.md
git commit -m "docs(spec): record search and library polish on the NAS"
```

## Spec coverage

| Spec section | Task |
|---|---|
| §3.1 Combobox | 4 |
| §3.2 editor fields | 3 (`artistOptions`, `albumOptions`), 5 |
| §3.3 prefill (`matchArtist`) | 3, 5 |
| §3.4 album view | 3 (`albumList`), 7 |
| §4.1 search API pages | 1 |
| §4.2 pager and page cache | 3 (`searchPages`), 6 |
| §5.1 suggest API | 2 |
| §5.2 suggestions in the search box | 3 (`api.suggest`, `libraryMatches`), 6 |
| §6 tests | every task |
