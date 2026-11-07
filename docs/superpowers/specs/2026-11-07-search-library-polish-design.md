# WYC-music-streaming: search and library polish (design addendum)

Date: 2026-11-07
Base spec: `docs/superpowers/specs/2026-11-05-wyc-music-streaming-design.md`
Status: approved in chat, before plan

This addendum changes the search page, the tape label editor, and the library page.
It comes from the first real use of the deployed frontend (plan 2).
Plan 3 (albums from YouTube Music, boxes) is not changed.

## 1. Problems seen in real use

1. The artist and album fields are free text. A feat. track makes a new artist.
   Example: "The Weeknd, JENNIE & Lily Rose Depp" became its own artist folder
   next to "The Weeknd".
2. The library groups only by artist. The user wants to browse by album too.
3. Search gives 10 results and no way to see more.
4. The search box gives no suggestions while typing.

## 2. Scope

| Part | What | Backend change |
|---|---|---|
| A | Artist/album combobox in the editor; library view by album | none |
| B | Search pages: 10 results per page, at most 5 pages | `page` on `/api/search` |
| C | Suggestions while typing in the search box | new `/api/suggest` |

Out of scope: moving tracks that are already in the wrong artist folder.
The user deletes and downloads again.

## 3. Part A: combobox and album view

### 3.1 `Combobox.svelte`

One shared component: a text input with a popup list.

- Props: `value` (bindable string), `options: {value, label, hint?}[]`,
  `onpick(value)`, `createLabel?` (string or null), plus `label`, `placeholder`, `maxlength`.
- The popup opens on focus and on typing. It closes on Esc, on blur, and after a pick.
- Arrow Up/Down move the active row. Enter picks the active row.
  Enter with no active row does nothing to the list (a form submit still works).
- The last row is "+ สร้างใหม่ "<typed text>"" when `createLabel` is set,
  the typed text is not empty, and no option matches it (case-insensitive, trimmed).
  Picking it keeps the typed text.
- ARIA: input `role="combobox"`, `aria-expanded`, `aria-controls`, `aria-activedescendant`;
  list `role="listbox"`; rows `role="option"` with `aria-selected`.
- The component does not filter. The caller passes the options to show.

### 3.2 Tape label editor (`EditPanel.svelte`)

- Artist field: a `Combobox`. Options are the library artists whose name contains
  the typed text (case-insensitive), with hint "<n> เพลง". Max 8 rows.
- Album field: a `Combobox`. Options are the albums of the artist in the artist field
  (exact name, case-insensitive), filtered the same way. Empty list when the artist is new.
- Both have the create row.
- `EditPanel` takes a new prop `artists: LibraryArtist[]` (the library tree).

### 3.3 Prefill with a library artist

Pure function `matchArtist(suggested: string, names: string[]): string` in `lib/artistMatch.ts`:

1. Exact match (case-insensitive, trimmed): return the library name.
2. Else, the longest library name `n` such that `suggested` starts with `n`
   (case-insensitive) and the rest starts with a separator:
   `,` `&` ` x ` ` X ` ` feat.` ` feat ` ` ft.` ` ft ` ` with ` ` and ` `/`.
   Return `n`.
3. Else return `suggested` unchanged.

`draftFrom` keeps the YouTube guess. The search page calls `matchArtist` when it opens
the editor, and when it builds playlist items. When the prefill differs from the guess,
the artist combobox shows the full guess as the first option, with hint "ชื่อจาก YouTube".

The names map to one folder: `sanitize_name("The Weeknd")` is `The_Weeknd`,
and the library reads the name from tags, so the combobox shows "The Weeknd".

### 3.4 Library view by album

- A toggle `[ศิลปิน | อัลบั้ม]` above the filter. The view is in the URL:
  `/library` (artist view) and `/library?view=albums`. Reload keeps it.
- Pure function `albumList(artists: LibraryArtist[]): AlbumCard[]` in `lib/albumList.ts`.
  `AlbumCard = {key, album, artist, tracks}`. One card per (artist, album) pair.
  "Singles" of two artists are two cards. Sort by album name, then artist name
  (case-insensitive, `localeCompare` with `th`).
- Album view: a grid of cards (album name, artist, "<n> เพลง").
  Clicking a card opens its track list in place, with the same `TrackRow` and delete.
  One card is open at a time. The open card key is local state (not in the URL).
- The filter works in both views. It runs `filterLibrary` first, then `albumList`.

## 4. Part B: search pages

### 4.1 API

`GET /api/search?q=<text>&page=<1..5>` (`page` defaults to 1; outside 1..5 gives 422).

- Text search: yt-dlp target `ytsearch50:<q>` with `playlist_items="<start>-<end>"`,
  where `start = (page-1)*10 + 1` and `end = page*10`. Checked on 2026-11-07:
  pages 1 and 5 each return 10 entries, about 2 s each.
- Response adds `page: int` and `has_more: bool`.
  `has_more = page < 5 and len(results) == 10`.
- URL and playlist lookups ignore `page`. They return `page: 1`, `has_more: false`.
- Constants in `search.py`: `PAGE_SIZE = 10`, `MAX_PAGES = 5`.
  `SEARCH_COUNT` goes away.

### 4.2 Frontend

- Pure module `lib/searchPages.ts`: `pageNumbers(current, knownLast): number[]`
  and the rule for `knownLast` (5 until a page has `has_more: false`, then that page).
- The search page keeps a `Map<number, SearchResponse>` for the current query.
  A new query clears it. Going back to a fetched page does not call the API.
- A pager under the results: `« ก่อน`, page numbers, `ถัดไป »`.
  The current page has `aria-current="page"`. Shown only for `kind: "search"`.
- Changing page scrolls to the top of the results (smooth unless reduced motion).
- While a page loads, the pager buttons are disabled and the old results stay.

## 5. Part C: suggestions while typing

### 5.1 API

`GET /api/suggest?q=<text>` (1..100 chars). Needs the Tailscale identity like every `/api` route.

- Calls `https://suggestqueries.google.com/complete/search?client=firefox&ds=yt&q=<q>`
  with `httpx.AsyncClient`, timeout 3 s.
  The response is JSON: `[query, [s1, s2, ...], ...]`.
- Returns `{"suggestions": [...]}`, at most 8 strings.
- Any error (network, timeout, non-200, bad JSON, wrong shape) returns
  `{"suggestions": []}` with status 200, and logs one warning line.
- This endpoint is not an official API. If it breaks, the dropdown is empty and search still works.

### 5.2 Frontend

- Only on the "เพลง" tab. The search input becomes a `Combobox` (no create row).
- Start at 2 or more characters, after 250 ms with no typing.
  A new request aborts the old one (`AbortController`). Errors show nothing.
- Rows: YouTube suggestions first, then up to 3 library matches
  (artists and track titles that contain the text, case-insensitive), hint "มีแล้ว".
- Picking a row puts its text in the box and runs the search at page 1.
- `api.suggest(q, signal)` in `lib/api.ts`.

## 6. Tests

Backend (pytest):

- `search`: page 1 and page 3 pass the right `playlist_items`; `has_more` true on a full page,
  false on a short page and on page 5; URL lookups return `page: 1`, `has_more: false`.
- `/api/search`: `page=0` and `page=6` give 422.
- `suggest`: success (8 of 10 kept), timeout, non-200, bad JSON, wrong shape all give `[]`.
  httpx is mocked with `httpx.MockTransport`.
- `/api/suggest`: 403 without identity; returns the list with identity.

Frontend (vitest):

- `matchArtist`: exact, case, each separator, longest wins, no match, empty names.
- `albumList`: one card per pair, two "Singles" cards, sort order, Thai names.
- `searchPages`: numbers for each current page, cut at `knownLast`.
- `Combobox`: arrows, Enter, Esc, create row shown and hidden, ARIA attributes.
- `EditPanel`: artist options from the library, album options follow the artist.
- Library page: the toggle changes `?view=`, opening a card shows its tracks.

## 7. Files

Backend:
- Modify: `search.py`, `api.py`, `tests/test_search.py`, `tests/test_api.py`
- Create: `suggest.py`, `tests/test_suggest.py`

Frontend:
- Create: `lib/artistMatch.ts`, `lib/albumList.ts`, `lib/searchPages.ts`,
  `lib/components/Combobox.svelte` (each with a test file)
- Modify: `lib/types.ts`, `lib/api.ts`, `lib/components/EditPanel.svelte`,
  `routes/+page.svelte`, `routes/library/+page.svelte`, and their tests
