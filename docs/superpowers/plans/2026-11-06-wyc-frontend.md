# WYC-music-streaming Frontend Implementation Plan (plan 2 of 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the SvelteKit web UI (Cassette style) for search + download, the queue, and the library, served by the FastAPI backend from plan 1.

**Architecture:** A SvelteKit SPA (`adapter-static`, `fallback: 'index.html'`, `ssr = false`) in `app/frontend/`. A typed API client talks to `/api/*`. App-wide state lives in Svelte 5 rune classes (`*.svelte.ts`) and is kept live by one `EventSource` on `/api/events`. Pure logic (validation, sorting, filtering) sits in plain TS modules with unit tests; components get Vitest + Testing Library tests. The backend already mounts `app/frontend/build/` at `/` (`SPAStaticFiles` in `main.py`), so no backend change is needed.

**Tech Stack:** SvelteKit 2.70, Svelte 5.57 (runes), Vite 7.3, Tailwind CSS 4.3 (`@tailwindcss/vite`), TypeScript 5.9, Vitest 3.2 + jsdom 26 + @testing-library/svelte 5.4, @fontsource (Bai Jamjuree, Space Mono). Node 24 LTS through nvm.

**Spec:** `docs/superpowers/specs/2026-11-05-wyc-music-streaming-design.md` (§7 Frontend, §6 for the API, §8 Errors). Plan 1: `docs/superpowers/plans/2026-11-05-wyc-backend-core.md`.

**Scope:** routes `/` (song + link tabs), `/queue`, `/library`, `/denied`. **Not in this plan** (plan 3, together with their backend): the album tab, `/boxes`, `/boxes/[id]`, and "add to box" in the library.

## Global Constraints

- SvelteKit + `adapter-static` (SPA, `fallback: 'index.html'`) + Tailwind. FastAPI serves `app/frontend/build/`.
- Fonts are self-hosted with `@fontsource/bai-jamjuree` and `@fontsource/space-mono`. No external requests for fonts or scripts. (YouTube thumbnails from `i.ytimg.com` are the only external images.)
- Design tokens (canvas C): ground `#EFE6D2`, card `#FBF6EA`, ink `#1E1B16`, orange `#D9541E`, teal `#1F6F78`, yellow `#E8C86A`, muted text `#5C5345`.
- Style: border 2px ink, radius 6–10px, hard shadow `5px 5px 0`.
- Mobile: every layout stacks at phone width. Touch targets are at least 44px (`min-h-11`).
- UI text is Thai. Code, comments, commits and docs are English.
- Build on the NAS with Node from `nvm` (`update.sh` runs `npm ci && npm run build` as `wick` when `app/frontend/package.json` exists).
- Pin dependency versions exactly as listed in Task 1. Commit `package-lock.json`.
  `@testing-library/jest-dom` stays at exactly `6.9.1`: 6.10.0 is a broken release (deprecated by its authors).
- `npm run check` runs `svelte-check --fail-on-warnings`: zero errors and zero warnings.
- The repo is public: never commit `config.toml`, keys, or real Tailscale logins.

## Execution notes

- **Network:** `npm install` (Task 1) needs the network. A sandboxed executor without network (Codex) must get `node_modules/` from the controller first: the controller runs Task 1 Step 2 before dispatching.
- All commands run in `app/frontend/` unless a step says otherwise. Use Node 24 (`source ~/.nvm/nvm.sh`).
- Every code block below was built and tested together before this plan was written (47 tests pass, `svelte-check` 0/0, build OK).

## File structure

```
app/frontend/
  package.json, package-lock.json
  svelte.config.js        adapter-static, SPA fallback
  vite.config.ts          tailwind + sveltekit + vitest, /api proxy to :8097
  vitest-setup.ts         jest-dom matchers
  tsconfig.json
  static/robots.txt
  src/
    app.html, app.d.ts
    app.css               Tailwind + design tokens + .card/.btn/.input/.label
    lib/
      types.ts            API shapes
      api.ts              createApi(): typed fetch client, ApiError, 403 → onDenied
      format.ts           formatDuration, percent, STATUS_LABEL, errorText
      selection.ts        Draft, validateDraft, toJobItem, cardState, defaultSelection, summarizeCreate
      jobList.ts          isActive, sortJobs, upsertJob
      libraryFilter.ts    filterLibrary, libraryVideoIds, trackCount
      events.ts           connectEvents(): SSE /api/events
      testData.ts         factories for tests
      session.svelte.ts   session.me, session.deniedLogin
      client.ts           app-wide `api` (403 → goto('/denied'))
      jobs.svelte.ts      jobs state (list, active, current, queued)
      library.svelte.ts   library state (artists, videoIds, trackCount)
      components/
        Nav.svelte, ResultCard.svelte, EditPanel.svelte, CassetteDeck.svelte,
        JobRow.svelte, TrackRow.svelte (+ *.test.ts)
    routes/
      +layout.ts          ssr = false
      +layout.svelte      header, nav, boot (me, jobs, library), SSE
      +page.svelte        search
      queue/+page.svelte
      library/+page.svelte
      denied/+page.svelte
```

---

### Task 1: Scaffold, design tokens, API client and formatting

**Files:**
- Create: `app/frontend/package.json`, `svelte.config.js`, `vite.config.ts`, `vitest-setup.ts`, `tsconfig.json`, `static/robots.txt`
- Create: `app/frontend/src/app.html`, `src/app.d.ts`, `src/app.css`, `src/routes/+layout.ts`, `src/routes/+layout.svelte` (temporary), `src/routes/+page.svelte` (temporary)
- Create: `app/frontend/src/lib/types.ts`, `src/lib/api.ts`, `src/lib/format.ts`
- Test: `app/frontend/src/lib/api.test.ts`, `src/lib/format.test.ts`
- Modify: `.gitignore` (add `app/frontend/.svelte-kit/`), `app/README.md` (dev section)

**Interfaces:**
- Produces: `createApi(fetchFn?, onDenied?)` returning `{ me, search, createJobs, listJobs, cancelJob, retryJob, library, rescanLibrary, deleteTrack, refreshJellyfin }`; `type Api`; `class ApiError { status: number; detail: unknown }`; `type DeniedInfo = { login: string | null }`.
- Produces: `formatDuration(seconds: number | null | undefined): string`, `percent(fraction: number): string`, `STATUS_LABEL: Record<JobStatus, string>`, `errorText(error: unknown): string`.
- Produces: all API types in `types.ts` (`Me`, `SearchResult`, `SearchResponse`, `Job`, `JobStatus`, `JobItem`, `CreateJobsResponse`, `LibraryTrack`, `LibraryAlbum`, `LibraryArtist`).
- Produces: CSS classes `.card`, `.btn`, `.btn-primary`, `.btn-teal`, `.input`, `.label`; Tailwind colors `ground card ink orange teal yellow muted`; shadows `shadow-hard`, `shadow-hard-sm`.

- [ ] **Step 1: Write the config files**

`app/frontend/package.json`:

```json
{
  "name": "wyc-music-streaming-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite dev",
    "build": "vite build",
    "preview": "vite preview",
    "check": "svelte-kit sync && svelte-check --tsconfig ./tsconfig.json --fail-on-warnings",
    "test": "vitest run",
    "prepare": "svelte-kit sync || echo ''"
  },
  "devDependencies": {
    "@fontsource/bai-jamjuree": "^5.3.0",
    "@fontsource/space-mono": "^5.3.0",
    "@sveltejs/adapter-static": "^3.0.11",
    "@sveltejs/kit": "^2.70.4",
    "@sveltejs/vite-plugin-svelte": "^6.2.4",
    "@tailwindcss/vite": "^4.3.5",
    "@testing-library/jest-dom": "6.9.1",
    "@testing-library/svelte": "^5.4.2",
    "jsdom": "^26.1.0",
    "svelte": "^5.57.3",
    "svelte-check": "^4.7.8",
    "tailwindcss": "^4.3.5",
    "typescript": "^5.9.3",
    "vite": "^7.3.7",
    "vitest": "^3.2.7"
  }
}
```

`app/frontend/svelte.config.js`:

```js
import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	preprocess: vitePreprocess(),
	kit: {
		// SPA: FastAPI serves build/ and falls back to index.html for client-side routes.
		adapter: adapter({ fallback: 'index.html' })
	}
};

export default config;
```

`app/frontend/vite.config.ts`:

```ts
import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';
import { svelteTesting } from '@testing-library/svelte/vite';
import { defineConfig } from 'vitest/config';

export default defineConfig({
	plugins: [tailwindcss(), sveltekit(), svelteTesting()],
	server: {
		// Dev: the backend runs on 8097 in dev mode (see app/README.md).
		proxy: { '/api': 'http://127.0.0.1:8097' }
	},
	test: {
		environment: 'jsdom',
		include: ['src/**/*.test.ts'],
		setupFiles: ['./vitest-setup.ts']
	}
});
```

`app/frontend/vitest-setup.ts`:

```ts
import '@testing-library/jest-dom/vitest';
```

`app/frontend/tsconfig.json`:

```json
{
	"extends": "./.svelte-kit/tsconfig.json",
	"compilerOptions": {
		"allowJs": true,
		"checkJs": true,
		"esModuleInterop": true,
		"forceConsistentCasingInFileNames": true,
		"resolveJsonModule": true,
		"skipLibCheck": true,
		"sourceMap": true,
		"strict": true,
		"moduleResolution": "bundler"
	}
}
```

`app/frontend/static/robots.txt`:

```
User-agent: *
Disallow: /
```

`app/frontend/src/app.html`:

```html
<!doctype html>
<html lang="th">
	<head>
		<meta charset="utf-8" />
		<meta name="viewport" content="width=device-width, initial-scale=1" />
		<meta name="theme-color" content="#EFE6D2" />
		%sveltekit.head%
	</head>
	<body data-sveltekit-preload-data="hover">
		<div style="display: contents">%sveltekit.body%</div>
	</body>
</html>
```

`app/frontend/src/app.d.ts`:

```ts
/// <reference types="@testing-library/jest-dom/vitest" />
// See https://svelte.dev/docs/kit/types#app.d.ts
declare global {
	namespace App {}
}

export {};
```

`app/frontend/src/app.css`:

```css
@import 'tailwindcss';
@import '@fontsource/bai-jamjuree/400.css';
@import '@fontsource/bai-jamjuree/600.css';
@import '@fontsource/bai-jamjuree/700.css';
@import '@fontsource/space-mono/400.css';
@import '@fontsource/space-mono/700.css';

/* Design tokens from canvas C (Cassette), spec §7. */
@theme {
	--color-ground: #efe6d2;
	--color-card: #fbf6ea;
	--color-ink: #1e1b16;
	--color-orange: #d9541e;
	--color-teal: #1f6f78;
	--color-yellow: #e8c86a;
	--color-muted: #5c5345;
	--font-sans: 'Bai Jamjuree', system-ui, sans-serif;
	--font-mono: 'Space Mono', ui-monospace, monospace;
	--shadow-hard: 5px 5px 0 var(--color-ink);
	--shadow-hard-sm: 3px 3px 0 var(--color-ink);
}

@layer base {
	body {
		@apply bg-ground font-sans text-ink antialiased;
	}
}

@layer components {
	.card {
		@apply rounded-[10px] border-2 border-ink bg-card shadow-hard;
	}
	.btn {
		@apply inline-flex min-h-11 items-center justify-center gap-2 rounded-md border-2 border-ink bg-card px-4 font-semibold shadow-hard-sm transition-transform;
	}
	.btn:active:not(:disabled) {
		@apply translate-x-[2px] translate-y-[2px] shadow-none;
	}
	.btn:disabled {
		@apply cursor-not-allowed opacity-50;
	}
	.btn-primary {
		@apply bg-orange text-card;
	}
	.btn-teal {
		@apply bg-teal text-card;
	}
	.input {
		@apply min-h-11 w-full rounded-md border-2 border-ink bg-card px-3 focus:ring-2 focus:ring-teal focus:outline-none;
	}
	.label {
		@apply font-mono text-xs tracking-wide text-muted uppercase;
	}
}
```

`app/frontend/src/routes/+layout.ts`:

```ts
// SPA only: no server rendering, no prerendering. FastAPI serves build/index.html.
export const ssr = false;
export const prerender = false;
```

`app/frontend/src/routes/+layout.svelte` (temporary; Task 3 replaces it):

```svelte
<script lang="ts">
	import '../app.css';

	let { children } = $props();
</script>

{@render children()}
```

`app/frontend/src/routes/+page.svelte` (temporary; Task 4 replaces it):

```svelte
<h1 class="card m-4 p-4 text-2xl font-bold">WYC-music-streaming</h1>
```

Append to the repo root `.gitignore`, inside the `# WYC-music-streaming app` block (append only; never rewrite the file):

```
app/frontend/.svelte-kit/
```

- [ ] **Step 2: Install dependencies (network)**

Run: `cd app/frontend && npm install --no-audit --no-fund`
Expected: `added ... packages`, and a new `package-lock.json`. A deprecation warning for `whatwg-encoding` is fine.

- [ ] **Step 3: Write the failing tests**

`app/frontend/src/lib/api.test.ts`:

```ts
import { describe, expect, it, vi } from 'vitest';
import { ApiError, createApi } from './api';

function fakeFetch(status: number, body: unknown) {
	const calls: { url: string; init?: RequestInit }[] = [];
	const fn = async (url: string, init?: RequestInit) => {
		calls.push({ url, init });
		return new Response(status === 204 ? null : JSON.stringify(body), {
			status,
			headers: { 'Content-Type': 'application/json' }
		});
	};
	return { fn, calls };
}

describe('createApi', () => {
	it('encodes the search query', async () => {
		const { fn, calls } = fakeFetch(200, { kind: 'search', playlist_title: null, results: [] });
		const out = await createApi(fn).search('numb linkin park');
		expect(calls[0].url).toBe('/api/search?q=numb%20linkin%20park');
		expect(out.kind).toBe('search');
	});

	it('posts jobs as JSON', async () => {
		const { fn, calls } = fakeFetch(201, { created: [], skipped: [] });
		const item = { video_id: 'kXYiU_JCYtU', title: 'Numb', artist: 'Linkin Park', album: 'Singles' };
		await createApi(fn).createJobs([item]);
		expect(calls[0].init?.method).toBe('POST');
		expect(calls[0].init?.headers).toEqual({ 'Content-Type': 'application/json' });
		expect(JSON.parse(String(calls[0].init?.body))).toEqual({ items: [item] });
	});

	it('returns undefined for 204', async () => {
		const { fn, calls } = fakeFetch(204, null);
		await expect(createApi(fn).deleteTrack('A/B/c.m4a')).resolves.toBeUndefined();
		expect(calls[0].init?.method).toBe('DELETE');
		expect(JSON.parse(String(calls[0].init?.body))).toEqual({ path: 'A/B/c.m4a' });
	});

	it('reports 403 with the login and throws ApiError', async () => {
		const { fn } = fakeFetch(403, { detail: { error: 'denied', login: 'x@gmail.com' } });
		const onDenied = vi.fn();
		const err = await createApi(fn, onDenied).me().catch((e) => e);
		expect(err).toBeInstanceOf(ApiError);
		expect(err.status).toBe(403);
		expect(onDenied).toHaveBeenCalledWith({ login: 'x@gmail.com' });
	});

	it('keeps a string detail as the message', async () => {
		const { fn } = fakeFetch(409, { detail: 'only a failed job can be retried' });
		const err = await createApi(fn).retryJob(1).catch((e) => e);
		expect(err.message).toBe('only a failed job can be retried');
	});
});
```

`app/frontend/src/lib/format.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { ApiError } from './api';
import { errorText, formatDuration, percent } from './format';

describe('formatDuration', () => {
	it.each([
		[187, '3:07'],
		[59.6, '1:00'],
		[3725, '1:02:05'],
		[0, '0:00'],
		[null, '–:––'],
		[-1, '–:––']
	])('%s → %s', (input, expected) => {
		expect(formatDuration(input)).toBe(expected);
	});
});

describe('percent', () => {
	it('rounds and clamps', () => {
		expect(percent(0.4237)).toBe('42%');
		expect(percent(1.2)).toBe('100%');
		expect(percent(-0.1)).toBe('0%');
	});
});

describe('errorText', () => {
	it('explains a search timeout', () => {
		expect(errorText(new ApiError(504, 'search took too long'))).toBe('ค้นหานานเกินไป ลองใหม่อีกครั้ง');
	});
	it('uses a string detail', () => {
		expect(errorText(new ApiError(400, 'invalid path'))).toBe('invalid path');
	});
	it('falls back to the status for other details', () => {
		expect(errorText(new ApiError(422, [{ msg: 'x' }]))).toBe('เกิดข้อผิดพลาด (HTTP 422)');
	});
	it('handles network errors', () => {
		expect(errorText(new TypeError('Failed to fetch'))).toBe('ติดต่อเซิร์ฟเวอร์ไม่ได้');
	});
});
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `npm test`
Expected: FAIL, `Failed to resolve import "./api"` and `"./format"`.

- [ ] **Step 5: Write the implementation**

`app/frontend/src/lib/types.ts`:

```ts
// Shapes returned by the backend API (app/backend/wyc_music_streaming/api.py).

export type Me = { name: string; login: string; jellyfin_user: string | null };

export type Suggested = { title: string; artist: string; album: string };

export type SearchResult = {
	video_id: string;
	title: string;
	channel: string;
	duration: number | null;
	thumbnail_url: string;
	suggested: Suggested;
	in_library: boolean;
};

export type SearchResponse = {
	kind: 'search' | 'url' | 'playlist';
	playlist_title: string | null;
	results: SearchResult[];
};

export type JobStatus = 'queued' | 'downloading' | 'done' | 'failed' | 'cancelled';

export type Job = {
	id: number;
	user: string;
	video_id: string;
	title: string;
	artist: string;
	album: string;
	track_no: number | null;
	year: string | null;
	cover_url: string | null;
	box_id: string | null;
	status: JobStatus;
	progress: number;
	error: string | null;
	final_path: string | null;
	created_at: string;
	updated_at: string;
};

export type JobItem = {
	video_id: string;
	title: string;
	artist: string;
	album: string;
	track_no?: number | null;
	year?: string | null;
	cover_url?: string | null;
};

export type SkipReason = 'duplicate' | 'in_library' | 'active';

export type CreateJobsResponse = {
	created: Job[];
	skipped: { video_id: string; reason: SkipReason }[];
};

export type LibraryTrack = {
	path: string;
	title: string;
	artist: string;
	album: string;
	duration: number | null;
	video_id: string | null;
	track_no: number | null;
};

export type LibraryAlbum = { album: string; tracks: LibraryTrack[] };

export type LibraryArtist = { artist: string; albums: LibraryAlbum[] };
```

`app/frontend/src/lib/api.ts`:

```ts
import type {
	CreateJobsResponse,
	Job,
	JobItem,
	LibraryArtist,
	Me,
	SearchResponse
} from './types';

export class ApiError extends Error {
	constructor(
		readonly status: number,
		readonly detail: unknown
	) {
		super(typeof detail === 'string' ? detail : `HTTP ${status}`);
		this.name = 'ApiError';
	}
}

export type DeniedInfo = { login: string | null };

type FetchFn = (input: string, init?: RequestInit) => Promise<Response>;

/** Typed client for /api. A 403 also calls onDenied, so the app can show /denied. */
export function createApi(
	fetchFn: FetchFn = (input, init) => fetch(input, init),
	onDenied: (info: DeniedInfo) => void = () => {}
) {
	async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
		const init: RequestInit = { method };
		if (body !== undefined) {
			init.headers = { 'Content-Type': 'application/json' };
			init.body = JSON.stringify(body);
		}
		const res = await fetchFn(`/api${path}`, init);
		if (res.status === 204) return undefined as T;
		const data: unknown = await res.json().catch(() => null);
		if (!res.ok) {
			const detail = data && typeof data === 'object' && 'detail' in data ? data.detail : null;
			if (res.status === 403) {
				const login =
					detail && typeof detail === 'object' && 'login' in detail && typeof detail.login === 'string'
						? detail.login
						: null;
				onDenied({ login });
			}
			throw new ApiError(res.status, detail);
		}
		return data as T;
	}

	return {
		me: () => request<Me>('GET', '/me'),
		search: (q: string) => request<SearchResponse>('GET', `/search?q=${encodeURIComponent(q)}`),
		createJobs: (items: JobItem[]) => request<CreateJobsResponse>('POST', '/jobs', { items }),
		listJobs: () => request<{ jobs: Job[] }>('GET', '/jobs'),
		cancelJob: (id: number) => request<void>('DELETE', `/jobs/${id}`),
		retryJob: (id: number) => request<Job>('POST', `/jobs/${id}/retry`),
		library: () => request<{ artists: LibraryArtist[] }>('GET', '/library'),
		rescanLibrary: () => request<{ tracks: number }>('POST', '/library/rescan'),
		deleteTrack: (path: string) => request<void>('DELETE', '/library/track', { path }),
		refreshJellyfin: () => request<{ ok: boolean }>('POST', '/jellyfin/refresh')
	};
}

export type Api = ReturnType<typeof createApi>;
```

`app/frontend/src/lib/format.ts`:

```ts
import { ApiError } from './api';
import type { JobStatus } from './types';

/** 187 → "3:07", 3725 → "1:02:05", null → "–:––". */
export function formatDuration(seconds: number | null | undefined): string {
	if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return '–:––';
	const s = Math.round(seconds);
	const h = Math.floor(s / 3600);
	const m = Math.floor((s % 3600) / 60);
	const sec = String(s % 60).padStart(2, '0');
	return h ? `${h}:${String(m).padStart(2, '0')}:${sec}` : `${m}:${sec}`;
}

/** 0.4237 → "42%", clamped to 0–100. */
export function percent(fraction: number): string {
	return `${Math.round(Math.min(Math.max(fraction, 0), 1) * 100)}%`;
}

export const STATUS_LABEL: Record<JobStatus, string> = {
	queued: 'รอคิว',
	downloading: 'กำลังอัด',
	done: 'เสร็จแล้ว',
	failed: 'ล้มเหลว',
	cancelled: 'ยกเลิกแล้ว'
};

/** One line of text for the UI from any error thrown by the API client. */
export function errorText(error: unknown): string {
	if (error instanceof ApiError) {
		if (error.status === 504) return 'ค้นหานานเกินไป ลองใหม่อีกครั้ง';
		if (typeof error.detail === 'string') return error.detail;
		return `เกิดข้อผิดพลาด (HTTP ${error.status})`;
	}
	return 'ติดต่อเซิร์ฟเวอร์ไม่ได้';
}
```

- [ ] **Step 6: Run tests, check and build**

Run: `npm test && npm run check && npm run build`
Expected: `Tests  16 passed (16)`; `0 ERRORS 0 WARNINGS`; `Wrote site to "build"` and `build/index.html` exists.

- [ ] **Step 7: Document the frontend dev loop**

In `app/README.md`, after the paragraph "Never use dev mode on the NAS." in the "Dev machine" section, add:

````markdown
Frontend (Node 24 through nvm). Run the backend in dev mode on port 8097 first; Vite proxies `/api` to it:

```
cd app/frontend
npm install
npm run dev          # http://localhost:5173
npm test             # unit and component tests
npm run check        # svelte-check, must show 0 errors and 0 warnings
npm run build        # writes build/, which the backend serves at /
```
````

- [ ] **Step 8: Commit**

```bash
git add .gitignore app/README.md app/frontend/package.json app/frontend/package-lock.json \
  app/frontend/svelte.config.js app/frontend/vite.config.ts app/frontend/vitest-setup.ts \
  app/frontend/tsconfig.json app/frontend/static app/frontend/src
git commit -m "feat(frontend): scaffold SvelteKit SPA with design tokens and API client"
```

---

### Task 2: Pure UI logic (drafts, job list, library filter)

**Files:**
- Create: `app/frontend/src/lib/selection.ts`, `src/lib/jobList.ts`, `src/lib/libraryFilter.ts`, `src/lib/testData.ts`
- Test: `app/frontend/src/lib/selection.test.ts`, `src/lib/jobList.test.ts`, `src/lib/libraryFilter.test.ts`

**Interfaces:**
- Consumes: types from Task 1 (`Job`, `JobItem`, `SearchResult`, `CreateJobsResponse`, `LibraryArtist`).
- Produces (`selection.ts`): `type Draft = { video_id; title; artist; album }`, `type CardState = 'new' | 'active' | 'in_library'`, `draftFrom(result): Draft`, `validateDraft(draft): string | null`, `toJobItem(draft, albumOverride?): JobItem`, `cardState(videoId, libraryIds: ReadonlySet<string>, jobs: Job[]): CardState`, `defaultSelection(results, libraryIds): string[]`, `summarizeCreate(res): string`.
- Produces (`jobList.ts`): `isActive(job): boolean`, `sortJobs(list): Job[]`, `upsertJob(list, job): Job[]`.
- Produces (`libraryFilter.ts`): `filterLibrary(artists, q): LibraryArtist[]`, `libraryVideoIds(artists): Set<string>`, `trackCount(artists): number`.
- Produces (`testData.ts`, tests only): `makeJob(overrides?)`, `makeResult(overrides?)`, `makeTrack(overrides?)`, `LIBRARY`.

- [ ] **Step 1: Write the test data and the failing tests**

`app/frontend/src/lib/testData.ts`:

```ts
// Small factories shared by the unit tests.
import type { Job, LibraryArtist, LibraryTrack, SearchResult } from './types';

export function makeJob(overrides: Partial<Job> = {}): Job {
	return {
		id: 1,
		user: 'wick',
		video_id: 'kXYiU_JCYtU',
		title: 'Numb',
		artist: 'Linkin Park',
		album: 'Singles',
		track_no: null,
		year: null,
		cover_url: null,
		box_id: null,
		status: 'queued',
		progress: 0,
		error: null,
		final_path: null,
		created_at: '2026-11-06T15:00:00Z',
		updated_at: '2026-11-06T15:00:00Z',
		...overrides
	};
}

export function makeResult(overrides: Partial<SearchResult> = {}): SearchResult {
	return {
		video_id: 'kXYiU_JCYtU',
		title: 'Numb (Official Music Video) [4K UPGRADE] – Linkin Park',
		channel: 'Linkin Park',
		duration: 188,
		thumbnail_url: 'https://i.ytimg.com/vi/kXYiU_JCYtU/mqdefault.jpg',
		suggested: { title: 'Numb', artist: 'Linkin Park', album: 'Singles' },
		in_library: false,
		...overrides
	};
}

export function makeTrack(overrides: Partial<LibraryTrack> = {}): LibraryTrack {
	return {
		path: 'Linkin_Park/Singles/Numb.m4a',
		title: 'Numb',
		artist: 'Linkin Park',
		album: 'Singles',
		duration: 188,
		video_id: 'kXYiU_JCYtU',
		track_no: null,
		...overrides
	};
}

export const LIBRARY: LibraryArtist[] = [
	{
		artist: 'Linkin Park',
		albums: [
			{
				album: 'Meteora',
				tracks: [
					makeTrack({ path: 'Linkin_Park/Meteora/07_Faint.m4a', title: 'Faint', album: 'Meteora', video_id: 'aaaaaaaaaaa', track_no: 7 }),
					makeTrack({ path: 'Linkin_Park/Meteora/13_Numb.m4a', title: 'Numb', album: 'Meteora', video_id: null, track_no: 13 })
				]
			},
			{ album: 'Singles', tracks: [makeTrack()] }
		]
	},
	{
		artist: 'Sade',
		albums: [
			{
				album: 'Diamond Life',
				tracks: [makeTrack({ path: 'Sade/Diamond_Life/Smooth_Operator.m4a', title: 'Smooth Operator', artist: 'Sade', album: 'Diamond Life', video_id: '4TYv2PhG89A' })]
			}
		]
	}
];
```

`app/frontend/src/lib/selection.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import {
	cardState,
	defaultSelection,
	draftFrom,
	summarizeCreate,
	toJobItem,
	validateDraft
} from './selection';
import { makeJob, makeResult } from './testData';

const draft = { video_id: 'kXYiU_JCYtU', title: 'Numb', artist: 'Linkin Park', album: 'Singles' };

describe('selection', () => {
	it('builds a draft from the suggested tags', () => {
		expect(draftFrom(makeResult())).toEqual(draft);
	});

	it('validates blank and long fields', () => {
		expect(validateDraft(draft)).toBeNull();
		expect(validateDraft({ ...draft, title: ' ' })).toBe('กรอกชื่อเพลงก่อน');
		expect(validateDraft({ ...draft, album: 'x'.repeat(301) })).toBe('อัลบั้มยาวเกิน 300 ตัวอักษร');
	});

	it('trims fields and applies a non-blank album override', () => {
		const padded = { ...draft, title: ' Numb ', artist: ' Linkin Park ' };
		expect(toJobItem(padded)).toEqual(draft);
		expect(toJobItem(draft, ' Phonk Mix ').album).toBe('Phonk Mix');
		expect(toJobItem(draft, '  ').album).toBe('Singles');
	});

	it('gives each card a state', () => {
		const ids = new Set(['inlib000000']);
		const jobs = [makeJob({ video_id: 'queued00000', status: 'queued' }), makeJob({ id: 2, video_id: 'failed00000', status: 'failed' })];
		expect(cardState('inlib000000', ids, jobs)).toBe('in_library');
		expect(cardState('queued00000', ids, jobs)).toBe('active');
		expect(cardState('failed00000', ids, jobs)).toBe('new');
		expect(cardState('other000000', ids, jobs)).toBe('new');
	});

	it('selects every playlist entry that is not in the library', () => {
		const results = [makeResult({ video_id: 'a0000000000' }), makeResult({ video_id: 'b0000000000' })];
		expect(defaultSelection(results, new Set(['b0000000000']))).toEqual(['a0000000000']);
	});

	it('summarizes created and skipped jobs', () => {
		expect(summarizeCreate({ created: [makeJob(), makeJob({ id: 2 })], skipped: [{ video_id: 'x', reason: 'in_library' }] }))
			.toBe('เพิ่ม 2 เพลงเข้าคิวแล้ว · ข้าม 1 เพลงที่มีในคลังหรืออยู่ในคิวแล้ว');
		expect(summarizeCreate({ created: [], skipped: [] })).toBe('ไม่มีเพลงที่ต้องโหลด');
	});
});
```

`app/frontend/src/lib/jobList.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { isActive, sortJobs, upsertJob } from './jobList';
import { makeJob } from './testData';

describe('jobList', () => {
	it('knows active statuses', () => {
		expect(isActive(makeJob({ status: 'queued' }))).toBe(true);
		expect(isActive(makeJob({ status: 'downloading' }))).toBe(true);
		expect(isActive(makeJob({ status: 'done' }))).toBe(false);
	});

	it('sorts active oldest first, then finished newest first', () => {
		const list = [
			makeJob({ id: 1, status: 'done', updated_at: '2026-11-06T15:01:00Z' }),
			makeJob({ id: 4, status: 'queued' }),
			makeJob({ id: 2, status: 'failed', updated_at: '2026-11-06T15:05:00Z' }),
			makeJob({ id: 3, status: 'downloading' })
		];
		expect(sortJobs(list).map((j) => j.id)).toEqual([3, 4, 2, 1]);
	});

	it('replaces a job by id and re-sorts', () => {
		const list = [makeJob({ id: 1, status: 'queued' }), makeJob({ id: 2, status: 'queued' })];
		const out = upsertJob(list, makeJob({ id: 1, status: 'done', updated_at: '2026-11-06T15:09:00Z' }));
		expect(out.map((j) => [j.id, j.status])).toEqual([
			[2, 'queued'],
			[1, 'done']
		]);
	});

	it('adds an unknown job', () => {
		expect(upsertJob([], makeJob({ id: 7 })).map((j) => j.id)).toEqual([7]);
	});
});
```

`app/frontend/src/lib/libraryFilter.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { filterLibrary, libraryVideoIds, trackCount } from './libraryFilter';
import { LIBRARY } from './testData';

describe('filterLibrary', () => {
	it('returns everything for a blank query', () => {
		expect(filterLibrary(LIBRARY, '  ')).toBe(LIBRARY);
	});

	it('keeps a whole artist when the artist matches', () => {
		const out = filterLibrary(LIBRARY, 'sade');
		expect(out.map((a) => a.artist)).toEqual(['Sade']);
		expect(out[0].albums[0].tracks).toHaveLength(1);
	});

	it('keeps a whole album when the album matches', () => {
		const out = filterLibrary(LIBRARY, 'METEORA');
		expect(out[0].albums.map((a) => a.album)).toEqual(['Meteora']);
		expect(out[0].albums[0].tracks).toHaveLength(2);
	});

	it('keeps only matching tracks otherwise', () => {
		const out = filterLibrary(LIBRARY, 'faint');
		expect(out[0].albums).toHaveLength(1);
		expect(out[0].albums[0].tracks.map((t) => t.title)).toEqual(['Faint']);
	});

	it('drops artists with nothing left', () => {
		expect(filterLibrary(LIBRARY, 'no such song')).toEqual([]);
	});
});

describe('library helpers', () => {
	it('collects video ids and counts tracks', () => {
		expect(libraryVideoIds(LIBRARY)).toEqual(new Set(['aaaaaaaaaaa', 'kXYiU_JCYtU', '4TYv2PhG89A']));
		expect(trackCount(LIBRARY)).toBe(4);
	});
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npm test`
Expected: FAIL, `Failed to resolve import "./selection"`, `"./jobList"`, `"./libraryFilter"`.

- [ ] **Step 3: Write the implementation**

`app/frontend/src/lib/jobList.ts`:

```ts
import type { Job } from './types';

export function isActive(job: Job): boolean {
	return job.status === 'queued' || job.status === 'downloading';
}

/** Active jobs first (oldest first, the worker order), then finished jobs (newest first). */
export function sortJobs(list: Job[]): Job[] {
	const active = list.filter(isActive).sort((a, b) => a.id - b.id);
	const finished = list
		.filter((j) => !isActive(j))
		.sort((a, b) => b.updated_at.localeCompare(a.updated_at) || b.id - a.id);
	return [...active, ...finished];
}

/** Insert or replace a job by id (from an SSE "job" event or an API response). */
export function upsertJob(list: Job[], job: Job): Job[] {
	return sortJobs([...list.filter((j) => j.id !== job.id), job]);
}
```

`app/frontend/src/lib/selection.ts`:

```ts
import { isActive } from './jobList';
import type { CreateJobsResponse, Job, JobItem, SearchResult } from './types';

/** The editable "tape label" for one track. */
export type Draft = { video_id: string; title: string; artist: string; album: string };

/** What a search result card can offer. */
export type CardState = 'new' | 'active' | 'in_library';

const FIELDS = [
	['title', 'ชื่อเพลง'],
	['artist', 'ศิลปิน'],
	['album', 'อัลบั้ม']
] as const;

export function draftFrom(result: SearchResult): Draft {
	return { video_id: result.video_id, ...result.suggested };
}

/** null when the draft is valid, else one message for the user. Limits match the backend (300). */
export function validateDraft(draft: Draft): string | null {
	for (const [key, label] of FIELDS) {
		const value = draft[key].trim();
		if (!value) return `กรอก${label}ก่อน`;
		if (value.length > 300) return `${label}ยาวเกิน 300 ตัวอักษร`;
	}
	return null;
}

/** A non-blank albumOverride replaces the album (one album field for a whole playlist). */
export function toJobItem(draft: Draft, albumOverride?: string): JobItem {
	return {
		video_id: draft.video_id,
		title: draft.title.trim(),
		artist: draft.artist.trim(),
		album: albumOverride?.trim() || draft.album.trim()
	};
}

export function cardState(videoId: string, libraryIds: ReadonlySet<string>, jobs: Job[]): CardState {
	if (libraryIds.has(videoId)) return 'in_library';
	if (jobs.some((j) => j.video_id === videoId && isActive(j))) return 'active';
	return 'new';
}

/** Playlist mode: tick every entry that is not in the library yet. */
export function defaultSelection(results: SearchResult[], libraryIds: ReadonlySet<string>): string[] {
	return results.filter((r) => !libraryIds.has(r.video_id)).map((r) => r.video_id);
}

export function summarizeCreate(res: CreateJobsResponse): string {
	const parts: string[] = [];
	if (res.created.length) parts.push(`เพิ่ม ${res.created.length} เพลงเข้าคิวแล้ว`);
	if (res.skipped.length) parts.push(`ข้าม ${res.skipped.length} เพลงที่มีในคลังหรืออยู่ในคิวแล้ว`);
	return parts.join(' · ') || 'ไม่มีเพลงที่ต้องโหลด';
}
```

`app/frontend/src/lib/libraryFilter.ts`:

```ts
import type { LibraryArtist } from './types';

/**
 * Keep what matches q (case-insensitive): a matching artist keeps all its albums,
 * a matching album keeps all its tracks, otherwise only matching track titles stay.
 */
export function filterLibrary(artists: LibraryArtist[], q: string): LibraryArtist[] {
	const needle = q.trim().toLowerCase();
	if (!needle) return artists;
	const hit = (s: string) => s.toLowerCase().includes(needle);
	const out: LibraryArtist[] = [];
	for (const artist of artists) {
		if (hit(artist.artist)) {
			out.push(artist);
			continue;
		}
		const albums = artist.albums
			.map((album) =>
				hit(album.album) ? album : { ...album, tracks: album.tracks.filter((t) => hit(t.title)) }
			)
			.filter((album) => album.tracks.length > 0);
		if (albums.length) out.push({ ...artist, albums });
	}
	return out;
}

export function libraryVideoIds(artists: LibraryArtist[]): Set<string> {
	const ids = new Set<string>();
	for (const artist of artists)
		for (const album of artist.albums)
			for (const track of album.tracks) if (track.video_id) ids.add(track.video_id);
	return ids;
}

export function trackCount(artists: LibraryArtist[]): number {
	return artists.reduce((n, a) => n + a.albums.reduce((m, al) => m + al.tracks.length, 0), 0);
}
```

- [ ] **Step 4: Run tests and check**

Run: `npm test && npm run check`
Expected: `Tests  32 passed (32)`; `0 ERRORS 0 WARNINGS`.

- [ ] **Step 5: Commit**

```bash
git add app/frontend/src/lib
git commit -m "feat(frontend): add pure logic for tape labels, job list and library filter"
```

---

### Task 3: App shell (state, live events, layout, nav, denied page)

**Files:**
- Create: `app/frontend/src/lib/events.ts`, `src/lib/session.svelte.ts`, `src/lib/client.ts`, `src/lib/jobs.svelte.ts`, `src/lib/library.svelte.ts`
- Create: `app/frontend/src/lib/components/Nav.svelte`, `src/routes/denied/+page.svelte`
- Modify: `app/frontend/src/routes/+layout.svelte` (replace the temporary one)
- Test: `app/frontend/src/lib/events.test.ts`

**Interfaces:**
- Consumes: `createApi`, `ApiError` (Task 1); `isActive`, `sortJobs`, `upsertJob`, `libraryVideoIds`, `trackCount` (Task 2).
- Produces: `interface EventSourceLike`, `type EventHandlers = { job(job: Job); library(); open() }`, `connectEvents(handlers, makeSource?): () => void`.
- Produces: `session` (`me: Me | null`, `deniedLogin: string | null`); `api` (app-wide client); `jobs` (`list`, `active`, `current`, `queued`, `load()`, `apply(job)`); `library` (`artists`, `loaded`, `videoIds`, `trackCount`, `load()`).
- Produces: `<Nav activeCount={number} />`.

- [ ] **Step 1: Write the failing test**

`app/frontend/src/lib/events.test.ts`:

```ts
import { describe, expect, it, vi } from 'vitest';
import { connectEvents, type EventSourceLike } from './events';
import { makeJob } from './testData';

class FakeSource implements EventSourceLike {
	url = '';
	closed = false;
	listeners = new Map<string, (event: MessageEvent) => void>();
	addEventListener(type: string, listener: (event: MessageEvent) => void) {
		this.listeners.set(type, listener);
	}
	emit(type: string, data = '') {
		this.listeners.get(type)?.(new MessageEvent(type, { data }));
	}
	close() {
		this.closed = true;
	}
}

function setup() {
	const source = new FakeSource();
	const handlers = { job: vi.fn(), library: vi.fn(), open: vi.fn() };
	const close = connectEvents(handlers, (url) => {
		source.url = url;
		return source;
	});
	return { source, handlers, close };
}

describe('connectEvents', () => {
	it('subscribes to /api/events and dispatches events', () => {
		const { source, handlers } = setup();
		expect(source.url).toBe('/api/events');
		const job = makeJob({ status: 'downloading', progress: 0.5 });
		source.emit('job', JSON.stringify(job));
		source.emit('library', '{"added":["a.m4a"]}');
		source.emit('open');
		expect(handlers.job).toHaveBeenCalledWith(job);
		expect(handlers.library).toHaveBeenCalledOnce();
		expect(handlers.open).toHaveBeenCalledOnce();
	});

	it('ignores a malformed job event', () => {
		const { source, handlers } = setup();
		source.emit('job', 'not json');
		expect(handlers.job).not.toHaveBeenCalled();
	});

	it('closes the source', () => {
		const { source, close } = setup();
		close();
		expect(source.closed).toBe(true);
	});
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npx vitest run src/lib/events.test.ts`
Expected: FAIL, `Failed to resolve import "./events"`.

- [ ] **Step 3: Write events and state**

`app/frontend/src/lib/events.ts`:

```ts
import type { Job } from './types';

/** The part of EventSource we use, so tests can pass a fake. */
export interface EventSourceLike {
	addEventListener(type: string, listener: (event: MessageEvent) => void): void;
	close(): void;
}

export type EventHandlers = {
	job: (job: Job) => void;
	library: () => void;
	/** Called on every (re)connect. Reload state here: events sent while offline are lost. */
	open: () => void;
};

/** Listen to /api/events (SSE). EventSource reconnects by itself. Returns a close function. */
export function connectEvents(
	handlers: EventHandlers,
	makeSource: (url: string) => EventSourceLike = (url) => new EventSource(url)
): () => void {
	const source = makeSource('/api/events');
	source.addEventListener('open', () => handlers.open());
	source.addEventListener('job', (event) => {
		try {
			handlers.job(JSON.parse(event.data) as Job);
		} catch {
			// ignore a malformed event; the next reconnect reloads the jobs
		}
	});
	source.addEventListener('library', () => handlers.library());
	return () => source.close();
}
```

`app/frontend/src/lib/session.svelte.ts`:

```ts
import type { Me } from './types';

class Session {
	/** The current user, from GET /api/me. null until it loads or when access is denied. */
	me = $state<Me | null>(null);
	/** The Tailscale login from a 403, shown on /denied. */
	deniedLogin = $state<string | null>(null);
}

export const session = new Session();
```

`app/frontend/src/lib/client.ts`:

```ts
import { goto } from '$app/navigation';
import { createApi } from './api';
import { session } from './session.svelte';

/** The app-wide API client. Any 403 sends the user to /denied. */
export const api = createApi(undefined, ({ login }) => {
	session.deniedLogin = login;
	if (location.pathname !== '/denied') void goto('/denied');
});
```

`app/frontend/src/lib/jobs.svelte.ts`:

```ts
import { api } from './client';
import { isActive, sortJobs, upsertJob } from './jobList';
import type { Job } from './types';

class JobsState {
	list = $state<Job[]>([]);
	active = $derived(this.list.filter(isActive));
	current = $derived(this.list.find((j) => j.status === 'downloading') ?? null);
	queued = $derived(this.list.filter((j) => j.status === 'queued'));

	async load() {
		this.list = sortJobs((await api.listJobs()).jobs);
	}

	apply(job: Job) {
		this.list = upsertJob(this.list, job);
	}
}

export const jobs = new JobsState();
```

`app/frontend/src/lib/library.svelte.ts`:

```ts
import { api } from './client';
import { libraryVideoIds, trackCount } from './libraryFilter';
import type { LibraryArtist } from './types';

class LibraryState {
	artists = $state<LibraryArtist[]>([]);
	loaded = $state(false);
	videoIds = $derived(libraryVideoIds(this.artists));
	trackCount = $derived(trackCount(this.artists));

	async load() {
		this.artists = (await api.library()).artists;
		this.loaded = true;
	}
}

export const library = new LibraryState();
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `npx vitest run src/lib/events.test.ts`
Expected: `Tests  3 passed (3)`.

- [ ] **Step 5: Write the nav, layout and denied page**

`app/frontend/src/lib/components/Nav.svelte`:

```svelte
<script lang="ts">
	import { page } from '$app/state';

	let { activeCount = 0 }: { activeCount?: number } = $props();

	const links = [
		{ href: '/', label: 'ค้นหา' },
		{ href: '/library', label: 'คลังเพลง' },
		{ href: '/queue', label: 'คิว' }
	];
</script>

<nav class="flex gap-2 overflow-x-auto" aria-label="เมนูหลัก">
	{#each links as link (link.href)}
		{@const current = page.url.pathname === link.href}
		<a href={link.href} class={['btn', current && 'btn-teal']} aria-current={current ? 'page' : undefined}>
			{link.label}
			{#if link.href === '/queue' && activeCount > 0}
				<span class="rounded border-2 border-ink bg-yellow px-1 font-mono text-xs text-ink">{activeCount}</span>
			{/if}
		</a>
	{/each}
</nav>
```

`app/frontend/src/routes/+layout.svelte` (replace the whole file):

```svelte
<script lang="ts">
	import '../app.css';
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { ApiError } from '$lib/api';
	import { api } from '$lib/client';
	import Nav from '$lib/components/Nav.svelte';
	import { connectEvents } from '$lib/events';
	import { errorText } from '$lib/format';
	import { jobs } from '$lib/jobs.svelte';
	import { library } from '$lib/library.svelte';
	import { session } from '$lib/session.svelte';

	let { children } = $props();
	let bootError = $state<string | null>(null);
	const denied = $derived(page.url.pathname === '/denied');

	onMount(() => {
		let close: (() => void) | undefined;
		let stopped = false;
		(async () => {
			try {
				session.me = await api.me();
			} catch (e) {
				// 403 is handled by the client (redirect to /denied).
				if (!(e instanceof ApiError && e.status === 403)) bootError = errorText(e);
				return;
			}
			try {
				await Promise.all([jobs.load(), library.load()]);
			} catch (e) {
				bootError = errorText(e);
			}
			if (stopped) return;
			close = connectEvents({
				job: (job) => jobs.apply(job),
				library: () => void library.load().catch(() => {}),
				open: () => void jobs.load().catch(() => {})
			});
		})();
		return () => {
			stopped = true;
			close?.();
		};
	});
</script>

<svelte:head>
	<title>WYC-music-streaming</title>
</svelte:head>

<div class="min-h-dvh">
	<header class="border-b-2 border-ink bg-card">
		<div class="mx-auto flex max-w-6xl flex-wrap items-center gap-3 px-4 py-3">
			<a href="/" class="flex min-h-11 items-center gap-2 text-lg font-bold">
				<span aria-hidden="true" class="flex h-7 w-11 items-center justify-around rounded border-2 border-ink bg-yellow">
					<span class="h-3 w-3 rounded-full border-2 border-ink bg-card"></span>
					<span class="h-3 w-3 rounded-full border-2 border-ink bg-card"></span>
				</span>
				WYC
			</a>
			{#if session.me && !denied}
				<Nav activeCount={jobs.active.length} />
				<span class="ml-auto font-mono text-xs text-muted">{session.me.name}</span>
			{/if}
		</div>
	</header>
	<main class="mx-auto max-w-6xl px-4 py-6">
		{#if bootError}
			<p role="alert" class="card mb-4 p-4 text-orange">{bootError}</p>
		{/if}
		{#if session.me || denied}
			{@render children()}
		{:else if !bootError}
			<p class="text-muted">กำลังโหลด…</p>
		{/if}
	</main>
</div>
```

`app/frontend/src/routes/denied/+page.svelte`:

```svelte
<script lang="ts">
	import { session } from '$lib/session.svelte';

	const login = $derived(session.deniedLogin);
	const snippet = $derived(
		[
			'[users.<name>]',
			`tailscale_login = "${login ?? '<tailscale login>'}"`,
			'music_dir = "/home/wick/share/<name>/music"',
			'jellyfin_user = "<name>"'
		].join('\n')
	);
</script>

<section class="card max-w-xl space-y-4 p-6">
	<h1 class="text-2xl font-bold">ไม่มีสิทธิ์เข้าใช้</h1>
	{#if login}
		<p>บัญชี Tailscale <span class="font-mono break-all">{login}</span> ยังไม่อยู่ในรายชื่อผู้ใช้</p>
	{:else}
		<p>ไม่พบตัวตนจาก Tailscale ต้องเปิดแอปผ่านลิงก์ <span class="font-mono">https://&lt;nas&gt;.ts.net</span> เท่านั้น</p>
	{/if}
	<p class="text-sm text-muted">
		ให้แอดมินเพิ่มส่วนนี้ใน <span class="font-mono">/etc/wyc-music-streaming/config.toml</span> แล้ว restart service
	</p>
	<pre class="overflow-x-auto rounded bg-ink p-3 font-mono text-xs text-card">{snippet}</pre>
</section>
```

- [ ] **Step 6: Run all tests, check and build**

Run: `npm test && npm run check && npm run build`
Expected: `Tests  35 passed (35)`; `0 ERRORS 0 WARNINGS`; build OK.

- [ ] **Step 7: Manual check against the dev backend**

1. Make a dev config outside the repo, for example `/tmp/wyc-dev/config.toml` (create `/tmp/wyc-dev/music` and put any text in `/tmp/wyc-dev/jellyfin.key`):

   ```toml
   [server]
   host = "127.0.0.1"
   port = 8097
   data_dir = "/tmp/wyc-dev/data"
   dev = true
   dev_user = "me"

   [jellyfin]
   url = "http://127.0.0.1:8096"
   api_key_file = "/tmp/wyc-dev/jellyfin.key"

   [download]
   concurrency = 2

   [users.me]
   tailscale_login = "me@example.com"
   music_dir = "/tmp/wyc-dev/music"
   ```

2. Terminal 1: `cd app/backend && WYC_MUSIC_STREAMING_CONFIG=/tmp/wyc-dev/config.toml uv run python -m wyc_music_streaming`
3. Terminal 2: `cd app/frontend && npm run dev`
4. Open `http://localhost:5173`. Expected: the header shows the cassette logo, "WYC", the nav (ค้นหา, คลังเพลง, คิว) and the user name `me`.
5. Stop the backend and reload. Expected: the red alert "ติดต่อเซิร์ฟเวอร์ไม่ได้".
6. Change `dev = false` in the dev config, restart the backend and reload. Expected: the app goes to `/denied` and shows "ไม่พบตัวตนจาก Tailscale". Set `dev = true` again.

- [ ] **Step 8: Commit**

```bash
git add app/frontend/src
git commit -m "feat(frontend): add app shell with live job and library state"
```

---

### Task 4: Search page (result cards, tape label editor, cassette deck)

**Files:**
- Create: `app/frontend/src/lib/components/ResultCard.svelte`, `EditPanel.svelte`, `CassetteDeck.svelte`
- Modify: `app/frontend/src/routes/+page.svelte` (replace the temporary one)
- Test: `app/frontend/src/lib/components/ResultCard.test.ts`, `EditPanel.test.ts`

**Interfaces:**
- Consumes: `api`, `jobs`, `library` (Task 3); `cardState`, `defaultSelection`, `draftFrom`, `summarizeCreate`, `toJobItem`, `validateDraft`, `Draft`, `CardState` (Task 2); `errorText`, `formatDuration`, `percent` (Task 1).
- Produces: `<ResultCard result state mode="single|pick" selected? ontoggle? ondownload? />`, `<EditPanel draft busy? error? onsubmit(draft) oncancel() />`, `<CassetteDeck job={Job | null} />`.

Behavior (spec §7, §6.1):
- Tabs "เพลง" (keyword) and "ลิงก์" (URL; must start with `http(s)://`). Both call `GET /api/search`.
- `kind = "search"`: one card per result with "โหลด". Clicking it opens the "เขียนฉลากเทป" editor with the suggested tags.
- `kind = "url"` with one new result: open the editor at once.
- `kind = "playlist"`: checkboxes, all entries not in the library ticked; one album field (default: playlist title) for the whole batch; button "โหลด N เพลง".
- Cards of tracks in the library or in the queue show a badge instead of the button.
- Right column: cassette deck (current download, live progress), next 3 queued jobs, tape shelf summary.

- [ ] **Step 1: Write the failing tests**

`app/frontend/src/lib/components/ResultCard.test.ts`:

```ts
import { fireEvent, render, screen } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import { makeResult } from '$lib/testData';
import ResultCard from './ResultCard.svelte';

describe('ResultCard', () => {
	it('offers a download for a new track', async () => {
		const ondownload = vi.fn();
		render(ResultCard, { result: makeResult(), state: 'new', mode: 'single', ondownload });
		expect(screen.getByText('→ Linkin Park / Singles / Numb')).toBeInTheDocument();
		await fireEvent.click(screen.getByRole('button', { name: 'โหลด' }));
		expect(ondownload).toHaveBeenCalledOnce();
	});

	it('shows a badge instead of the button for a track in the library', () => {
		render(ResultCard, { result: makeResult(), state: 'in_library', mode: 'single' });
		expect(screen.queryByRole('button')).toBeNull();
		expect(screen.getByText('มีในคลังแล้ว')).toBeInTheDocument();
	});

	it('toggles in pick mode and disables queued tracks', async () => {
		const ontoggle = vi.fn();
		const { unmount } = render(ResultCard, { result: makeResult(), state: 'new', mode: 'pick', selected: true, ontoggle });
		const box = screen.getByRole('checkbox');
		expect(box).toBeChecked();
		await fireEvent.click(box);
		expect(ontoggle).toHaveBeenCalledOnce();
		unmount();
		render(ResultCard, { result: makeResult(), state: 'active', mode: 'pick' });
		expect(screen.getByRole('checkbox')).toBeDisabled();
		expect(screen.getByText('อยู่ในคิว')).toBeInTheDocument();
	});
});
```

`app/frontend/src/lib/components/EditPanel.test.ts`:

```ts
import { fireEvent, render, screen } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import EditPanel from './EditPanel.svelte';

const draft = { video_id: 'kXYiU_JCYtU', title: 'Numb', artist: 'Linkin Park', album: 'Singles' };

describe('EditPanel', () => {
	it('prefills the label and submits the edited values', async () => {
		const onsubmit = vi.fn();
		render(EditPanel, { draft, onsubmit, oncancel: vi.fn() });
		const title = screen.getByLabelText('ชื่อเพลง') as HTMLInputElement;
		expect(title.value).toBe('Numb');
		await fireEvent.input(title, { target: { value: 'Numb (Live)' } });
		await fireEvent.click(screen.getByRole('button', { name: 'โหลดลงเทป' }));
		expect(onsubmit).toHaveBeenCalledWith({ ...draft, title: 'Numb (Live)' });
	});

	it('blocks submit while a field is blank', async () => {
		const onsubmit = vi.fn();
		render(EditPanel, { draft, onsubmit, oncancel: vi.fn() });
		await fireEvent.input(screen.getByLabelText('ศิลปิน'), { target: { value: '   ' } });
		expect(screen.getByRole('button', { name: 'โหลดลงเทป' })).toBeDisabled();
		expect(screen.getByRole('alert')).toHaveTextContent('กรอกศิลปินก่อน');
	});

	it('calls oncancel', async () => {
		const oncancel = vi.fn();
		render(EditPanel, { draft, onsubmit: vi.fn(), oncancel });
		await fireEvent.click(screen.getByRole('button', { name: 'ยกเลิก' }));
		expect(oncancel).toHaveBeenCalledOnce();
	});
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npx vitest run src/lib/components`
Expected: FAIL, `Failed to resolve import "./ResultCard.svelte"` and `"./EditPanel.svelte"`.

- [ ] **Step 3: Write the components**

`app/frontend/src/lib/components/ResultCard.svelte`:

```svelte
<script lang="ts">
	import { formatDuration } from '$lib/format';
	import type { CardState } from '$lib/selection';
	import type { SearchResult } from '$lib/types';

	type Props = {
		result: SearchResult;
		state: CardState;
		/** "pick" shows a checkbox (playlist mode); "single" shows a download button. */
		mode: 'single' | 'pick';
		selected?: boolean;
		ontoggle?: () => void;
		ondownload?: () => void;
	};
	let { result, state, mode, selected = false, ontoggle, ondownload }: Props = $props();

	const badge = $derived(
		state === 'in_library' ? 'มีในคลังแล้ว' : state === 'active' ? 'อยู่ในคิว' : null
	);
</script>

<li class="card flex items-center gap-3 p-3">
	{#if mode === 'pick'}
		<input
			type="checkbox"
			class="h-6 w-6 shrink-0 accent-teal"
			checked={selected}
			disabled={state !== 'new'}
			onchange={() => ontoggle?.()}
			aria-label={`เลือก ${result.title}`}
		/>
	{/if}
	<img
		src={result.thumbnail_url}
		alt=""
		loading="lazy"
		referrerpolicy="no-referrer"
		class="h-14 w-24 shrink-0 rounded border-2 border-ink object-cover"
	/>
	<div class="min-w-0 flex-1">
		<p class="truncate font-semibold" title={result.title}>{result.title}</p>
		<p class="truncate text-sm text-muted">
			{result.channel} · <span class="font-mono">{formatDuration(result.duration)}</span>
		</p>
		<p class="truncate text-xs text-teal">
			→ {result.suggested.artist} / {result.suggested.album} / {result.suggested.title}
		</p>
	</div>
	{#if mode === 'single'}
		{#if badge}
			<span class="label shrink-0">{badge}</span>
		{:else}
			<button class="btn btn-primary shrink-0" onclick={() => ondownload?.()}>โหลด</button>
		{/if}
	{:else if badge}
		<span class="label shrink-0">{badge}</span>
	{/if}
</li>
```

`app/frontend/src/lib/components/EditPanel.svelte`:

```svelte
<script lang="ts">
	import { validateDraft, type Draft } from '$lib/selection';

	type Props = {
		draft: Draft;
		busy?: boolean;
		error?: string | null;
		onsubmit: (draft: Draft) => void;
		oncancel: () => void;
	};
	let { draft, busy = false, error = null, onsubmit, oncancel }: Props = $props();

	// Writable deriveds: they reset when the parent passes a new draft.
	let title = $derived(draft.title);
	let artist = $derived(draft.artist);
	let album = $derived(draft.album);

	const current = $derived({ video_id: draft.video_id, title, artist, album });
	const problem = $derived(validateDraft(current));

	function submit(event: SubmitEvent) {
		event.preventDefault();
		if (!problem && !busy) onsubmit(current);
	}
</script>

<form class="card space-y-3 p-4" onsubmit={submit}>
	<h2 class="text-lg font-bold">เขียนฉลากเทป</h2>
	<label class="block space-y-1">
		<span class="label">ชื่อเพลง</span>
		<input class="input" bind:value={title} maxlength="300" />
	</label>
	<label class="block space-y-1">
		<span class="label">ศิลปิน</span>
		<input class="input" bind:value={artist} maxlength="300" />
	</label>
	<label class="block space-y-1">
		<span class="label">อัลบั้ม</span>
		<input class="input" bind:value={album} maxlength="300" />
	</label>
	{#if problem}
		<p role="alert" class="text-sm text-orange">{problem}</p>
	{/if}
	{#if error}
		<p role="alert" class="text-sm text-orange">{error}</p>
	{/if}
	<div class="flex flex-wrap gap-2">
		<button class="btn btn-primary" type="submit" disabled={!!problem || busy}>
			{busy ? 'กำลังส่ง…' : 'โหลดลงเทป'}
		</button>
		<button class="btn" type="button" onclick={oncancel}>ยกเลิก</button>
	</div>
</form>
```

`app/frontend/src/lib/components/CassetteDeck.svelte`:

```svelte
<script lang="ts">
	import { percent } from '$lib/format';
	import type { Job } from '$lib/types';

	let { job }: { job: Job | null } = $props();
</script>

<section class="card space-y-3 p-4" aria-label="เครื่องอัดเทป">
	<p class="label">กำลังอัดเทป</p>
	<div class="flex items-center justify-center gap-6 rounded-md border-2 border-ink bg-ink py-4">
		{#each [0, 1] as reel (reel)}
			<span
				aria-hidden="true"
				class={[
					'h-12 w-12 rounded-full border-4 border-dashed border-card bg-orange',
					job && 'motion-safe:animate-[spin_3s_linear_infinite]'
				]}
			></span>
		{/each}
	</div>
	{#if job}
		<div class="min-w-0">
			<p class="truncate font-semibold">{job.title}</p>
			<p class="truncate text-sm text-muted">{job.artist}</p>
		</div>
		<div class="h-3 overflow-hidden rounded border-2 border-ink bg-ground">
			<div class="h-full bg-teal transition-[width]" style:width={percent(job.progress)}></div>
		</div>
		<p class="text-right font-mono text-xs">{percent(job.progress)}</p>
	{:else}
		<p class="text-sm text-muted">เครื่องว่าง เลือกเพลงเพื่อเริ่มอัด</p>
	{/if}
</section>
```

- [ ] **Step 4: Run the component tests to verify they pass**

Run: `npx vitest run src/lib/components`
Expected: `Tests  6 passed (6)`.

- [ ] **Step 5: Write the search page**

`app/frontend/src/routes/+page.svelte` (replace the whole file):

```svelte
<script lang="ts">
	import { api } from '$lib/client';
	import CassetteDeck from '$lib/components/CassetteDeck.svelte';
	import EditPanel from '$lib/components/EditPanel.svelte';
	import ResultCard from '$lib/components/ResultCard.svelte';
	import { errorText } from '$lib/format';
	import { jobs } from '$lib/jobs.svelte';
	import { library } from '$lib/library.svelte';
	import {
		cardState,
		defaultSelection,
		draftFrom,
		summarizeCreate,
		toJobItem,
		type Draft
	} from '$lib/selection';
	import type { JobItem, SearchResponse } from '$lib/types';

	type Tab = 'song' | 'link';
	const TABS: { id: Tab; label: string; placeholder: string }[] = [
		{ id: 'song', label: 'เพลง', placeholder: 'ชื่อเพลง หรือ ศิลปิน' },
		{ id: 'link', label: 'ลิงก์', placeholder: 'วางลิงก์ YouTube (เพลง หรือ playlist)' }
	];

	let tab = $state<Tab>('song');
	let q = $state('');
	let searching = $state(false);
	let searchError = $state<string | null>(null);
	let response = $state<SearchResponse | null>(null);
	let editing = $state<Draft | null>(null);
	let sending = $state(false);
	let sendError = $state<string | null>(null);
	let notice = $state<string | null>(null);
	let picked = $state<string[]>([]);
	let batchAlbum = $state('');

	const placeholder = $derived(TABS.find((t) => t.id === tab)!.placeholder);
	const isPlaylist = $derived(response?.kind === 'playlist');

	function stateOf(videoId: string) {
		return cardState(videoId, library.videoIds, jobs.list);
	}

	function switchTab(next: Tab) {
		tab = next;
		searchError = null;
	}

	async function runSearch(event: SubmitEvent) {
		event.preventDefault();
		const query = q.trim();
		if (!query || searching) return;
		if (tab === 'link' && !/^https?:\/\//i.test(query)) {
			searchError = 'วางลิงก์ที่ขึ้นต้นด้วย https://';
			return;
		}
		searching = true;
		searchError = null;
		notice = null;
		sendError = null;
		editing = null;
		response = null;
		try {
			const res = await api.search(query);
			response = res;
			if (res.kind === 'playlist') {
				picked = defaultSelection(res.results, library.videoIds);
				batchAlbum = res.playlist_title ?? '';
			} else if (res.kind === 'url' && res.results.length === 1 && stateOf(res.results[0].video_id) === 'new') {
				editing = draftFrom(res.results[0]);
			}
		} catch (e) {
			searchError = errorText(e);
		} finally {
			searching = false;
		}
	}

	async function send(items: JobItem[]) {
		sending = true;
		sendError = null;
		try {
			const res = await api.createJobs(items);
			for (const job of res.created) jobs.apply(job);
			notice = summarizeCreate(res);
			editing = null;
		} catch (e) {
			sendError = errorText(e);
		} finally {
			sending = false;
		}
	}

	function togglePick(videoId: string) {
		picked = picked.includes(videoId) ? picked.filter((id) => id !== videoId) : [...picked, videoId];
	}

	function sendPlaylist() {
		if (!response) return;
		const items = response.results
			.filter((r) => picked.includes(r.video_id))
			.map((r) => toJobItem(draftFrom(r), batchAlbum));
		if (items.length) void send(items);
	}
</script>

<div class="grid gap-6 lg:grid-cols-[1fr_320px]">
	<section class="min-w-0 space-y-4">
		<div class="flex gap-2" role="tablist" aria-label="ประเภทการค้นหา">
			{#each TABS as t (t.id)}
				<button
					role="tab"
					aria-selected={tab === t.id}
					class={['btn', tab === t.id && 'btn-teal']}
					onclick={() => switchTab(t.id)}
				>
					{t.label}
				</button>
			{/each}
		</div>

		<form class="flex gap-2" onsubmit={runSearch}>
			<input class="input" bind:value={q} {placeholder} aria-label={placeholder} maxlength="500" />
			<button class="btn btn-primary shrink-0" type="submit" disabled={searching || !q.trim()}>
				{searching ? 'กำลังหา…' : 'ค้นหา'}
			</button>
		</form>

		{#if searchError}
			<p role="alert" class="card p-3 text-orange">{searchError}</p>
		{/if}
		{#if notice}
			<p role="status" class="card bg-yellow p-3">{notice}</p>
		{/if}

		{#if editing}
			<EditPanel
				draft={editing}
				busy={sending}
				error={sendError}
				onsubmit={(d) => void send([toJobItem(d)])}
				oncancel={() => (editing = null)}
			/>
		{/if}

		{#if response && isPlaylist}
			<div class="card space-y-3 p-4">
				<p class="font-bold">Playlist: {response.playlist_title}</p>
				<label class="block space-y-1">
					<span class="label">อัลบั้ม (ใช้กับทุกเพลงที่เลือก)</span>
					<input class="input" bind:value={batchAlbum} maxlength="300" />
				</label>
				{#if sendError}
					<p role="alert" class="text-sm text-orange">{sendError}</p>
				{/if}
				<button
					class="btn btn-primary"
					onclick={sendPlaylist}
					disabled={sending || picked.length === 0 || !batchAlbum.trim()}
				>
					{sending ? 'กำลังส่ง…' : `โหลด ${picked.length} เพลง`}
				</button>
			</div>
		{/if}

		{#if response}
			{#if response.results.length === 0}
				<p class="text-muted">ไม่พบเพลง</p>
			{:else}
				<ul class="space-y-3">
					{#each response.results as result (result.video_id)}
						<ResultCard
							{result}
							state={stateOf(result.video_id)}
							mode={isPlaylist ? 'pick' : 'single'}
							selected={picked.includes(result.video_id)}
							ontoggle={() => togglePick(result.video_id)}
							ondownload={() => {
								notice = null;
								sendError = null;
								editing = draftFrom(result);
							}}
						/>
					{/each}
				</ul>
			{/if}
		{/if}
	</section>

	<aside class="space-y-4">
		<CassetteDeck job={jobs.current} />
		<section class="card space-y-2 p-4">
			<p class="label">คิวถัดไป</p>
			{#if jobs.queued.length === 0}
				<p class="text-sm text-muted">ไม่มีเพลงรอคิว</p>
			{:else}
				<ol class="space-y-1 text-sm">
					{#each jobs.queued.slice(0, 3) as job (job.id)}
						<li class="truncate">{job.title} <span class="text-muted">· {job.artist}</span></li>
					{/each}
				</ol>
				{#if jobs.queued.length > 3}
					<p class="text-xs text-muted">และอีก {jobs.queued.length - 3} เพลง</p>
				{/if}
			{/if}
			<a href="/queue" class="text-sm text-teal underline">ดูคิวทั้งหมด</a>
		</section>
		<section class="card space-y-1 p-4">
			<p class="label">ชั้นเทป</p>
			<p><span class="font-mono text-2xl">{library.trackCount}</span> เพลง จาก {library.artists.length} ศิลปิน</p>
			<a href="/library" class="text-sm text-teal underline">เปิดคลังเพลง</a>
		</section>
	</aside>
</div>
```

- [ ] **Step 6: Run all tests, check and build**

Run: `npm test && npm run check && npm run build`
Expected: `Tests  41 passed (41)`; `0 ERRORS 0 WARNINGS`; build OK.

- [ ] **Step 7: Manual check against the dev backend** (backend and `npm run dev` as in Task 3 Step 7)

1. Search "numb linkin park". Expected: 10 cards, each with a thumbnail and a `→ artist / album / title` line.
2. Click "โหลด" on the first card, change the title, click "โหลดลงเทป". Expected: the notice "เพิ่ม 1 เพลงเข้าคิวแล้ว"; the cassette deck shows the job, the reels spin and the progress moves; the card badge becomes "อยู่ในคิว", then "มีในคลังแล้ว".
3. Tab "ลิงก์", paste a playlist URL. Expected: checkboxes, the album field holds the playlist title, the button says "โหลด N เพลง".
4. Narrow the window to 375px. Expected: the right column moves under the results; no horizontal scroll.

- [ ] **Step 8: Commit**

```bash
git add app/frontend/src
git commit -m "feat(frontend): add search page with tape label editor and cassette deck"
```

---

### Task 5: Queue page

**Files:**
- Create: `app/frontend/src/lib/components/JobRow.svelte`, `src/routes/queue/+page.svelte`
- Test: `app/frontend/src/lib/components/JobRow.test.ts`

**Interfaces:**
- Consumes: `api`, `jobs` (Task 3); `isActive` (Task 2); `percent`, `STATUS_LABEL`, `errorText` (Task 1).
- Produces: `<JobRow job onretry(id) oncancel(id) />`.

Behavior (spec §7, §6.3, §8): active jobs first, then the last 50 finished jobs. A failed job shows its error and "ลองใหม่" (`POST /api/jobs/{id}/retry`). A queued job shows "ยกเลิก" (`DELETE /api/jobs/{id}`). A downloading job shows a progress bar. A done job shows its file path.

- [ ] **Step 1: Write the failing test**

`app/frontend/src/lib/components/JobRow.test.ts`:

```ts
import { fireEvent, render, screen } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import { makeJob } from '$lib/testData';
import JobRow from './JobRow.svelte';

describe('JobRow', () => {
	it('shows the error and retries a failed job', async () => {
		const onretry = vi.fn();
		render(JobRow, { job: makeJob({ id: 5, status: 'failed', error: 'HTTP Error 403' }), onretry, oncancel: vi.fn() });
		expect(screen.getByText('HTTP Error 403')).toBeInTheDocument();
		expect(screen.queryByRole('button', { name: 'ยกเลิก' })).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: 'ลองใหม่' }));
		expect(onretry).toHaveBeenCalledWith(5);
	});

	it('cancels a queued job', async () => {
		const oncancel = vi.fn();
		render(JobRow, { job: makeJob({ id: 6, status: 'queued' }), onretry: vi.fn(), oncancel });
		await fireEvent.click(screen.getByRole('button', { name: 'ยกเลิก' }));
		expect(oncancel).toHaveBeenCalledWith(6);
	});

	it('shows progress while downloading', () => {
		render(JobRow, { job: makeJob({ status: 'downloading', progress: 0.42 }), onretry: vi.fn(), oncancel: vi.fn() });
		expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '42');
		expect(screen.queryByRole('button')).toBeNull();
	});

	it('shows the file path when done', () => {
		render(JobRow, { job: makeJob({ status: 'done', final_path: 'Linkin_Park/Singles/Numb.m4a' }), onretry: vi.fn(), oncancel: vi.fn() });
		expect(screen.getByText('Linkin_Park/Singles/Numb.m4a')).toBeInTheDocument();
		expect(screen.getByText('เสร็จแล้ว')).toBeInTheDocument();
	});
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npx vitest run src/lib/components/JobRow.test.ts`
Expected: FAIL, `Failed to resolve import "./JobRow.svelte"`.

- [ ] **Step 3: Write the component and the page**

`app/frontend/src/lib/components/JobRow.svelte`:

```svelte
<script lang="ts">
	import { percent, STATUS_LABEL } from '$lib/format';
	import type { Job } from '$lib/types';

	type Props = { job: Job; onretry: (id: number) => void; oncancel: (id: number) => void };
	let { job, onretry, oncancel }: Props = $props();

	const tone: Record<Job['status'], string> = {
		queued: 'bg-card',
		downloading: 'bg-yellow',
		done: 'bg-teal text-card',
		failed: 'bg-orange text-card',
		cancelled: 'bg-ground'
	};
</script>

<li class="card space-y-2 p-3">
	<div class="flex items-start gap-3">
		<div class="min-w-0 flex-1">
			<p class="truncate font-semibold">{job.title}</p>
			<p class="truncate text-sm text-muted">{job.artist} · {job.album}</p>
		</div>
		<span class={['shrink-0 rounded border-2 border-ink px-2 py-0.5 font-mono text-xs', tone[job.status]]}>
			{STATUS_LABEL[job.status]}
		</span>
	</div>
	{#if job.status === 'downloading'}
		<div
			class="h-3 overflow-hidden rounded border-2 border-ink bg-ground"
			role="progressbar"
			aria-label={`ความคืบหน้า ${job.title}`}
			aria-valuemin={0}
			aria-valuemax={100}
			aria-valuenow={Math.round(job.progress * 100)}
		>
			<div class="h-full bg-teal transition-[width]" style:width={percent(job.progress)}></div>
		</div>
	{/if}
	{#if job.status === 'failed' && job.error}
		<p class="text-sm break-words text-orange">{job.error}</p>
	{/if}
	{#if job.status === 'done' && job.final_path}
		<p class="font-mono text-xs break-all text-muted">{job.final_path}</p>
	{/if}
	{#if job.status === 'failed'}
		<button class="btn" onclick={() => onretry(job.id)}>ลองใหม่</button>
	{:else if job.status === 'queued'}
		<button class="btn" onclick={() => oncancel(job.id)}>ยกเลิก</button>
	{/if}
</li>
```

`app/frontend/src/routes/queue/+page.svelte`:

```svelte
<script lang="ts">
	import { api } from '$lib/client';
	import JobRow from '$lib/components/JobRow.svelte';
	import { errorText } from '$lib/format';
	import { isActive } from '$lib/jobList';
	import { jobs } from '$lib/jobs.svelte';

	let error = $state<string | null>(null);
	const finished = $derived(jobs.list.filter((j) => !isActive(j)));

	async function retry(id: number) {
		error = null;
		try {
			jobs.apply(await api.retryJob(id));
		} catch (e) {
			error = errorText(e);
		}
	}

	async function cancel(id: number) {
		error = null;
		try {
			await api.cancelJob(id);
			await jobs.load();
		} catch (e) {
			error = errorText(e);
		}
	}
</script>

<div class="space-y-6">
	<h1 class="text-2xl font-bold">คิวดาวน์โหลด</h1>
	{#if error}
		<p role="alert" class="card p-3 text-orange">{error}</p>
	{/if}

	<section class="space-y-3">
		<h2 class="label">กำลังทำ ({jobs.active.length})</h2>
		{#if jobs.active.length === 0}
			<p class="text-muted">ไม่มีงานค้าง</p>
		{:else}
			<ul class="space-y-3">
				{#each jobs.active as job (job.id)}
					<JobRow {job} onretry={retry} oncancel={cancel} />
				{/each}
			</ul>
		{/if}
	</section>

	<section class="space-y-3">
		<h2 class="label">ประวัติ (50 งานล่าสุด)</h2>
		{#if finished.length === 0}
			<p class="text-muted">ยังไม่มีประวัติ</p>
		{:else}
			<ul class="space-y-3">
				{#each finished as job (job.id)}
					<JobRow {job} onretry={retry} oncancel={cancel} />
				{/each}
			</ul>
		{/if}
	</section>
</div>
```

- [ ] **Step 4: Run all tests, check and build**

Run: `npm test && npm run check && npm run build`
Expected: `Tests  45 passed (45)`; `0 ERRORS 0 WARNINGS`; build OK.

- [ ] **Step 5: Manual check** (dev backend + `npm run dev`)

1. Queue 3 songs from the search page, open `/queue`. Expected: up to 2 rows "กำลังอัด" with moving bars (concurrency 2), the rest "รอคิว" with "ยกเลิก"; the nav badge shows the active count.
2. Cancel a queued job. Expected: it moves to the history as "ยกเลิกแล้ว".
3. Queue a video that cannot download (for example a private video URL from the link tab). Expected: "ล้มเหลว" with the yt-dlp error and "ลองใหม่".

- [ ] **Step 6: Commit**

```bash
git add app/frontend/src
git commit -m "feat(frontend): add queue page with retry and cancel"
```

---

### Task 6: Library page

**Files:**
- Create: `app/frontend/src/lib/components/TrackRow.svelte`, `src/routes/library/+page.svelte`
- Test: `app/frontend/src/lib/components/TrackRow.test.ts`

**Interfaces:**
- Consumes: `api`, `library` (Task 3); `filterLibrary` (Task 2); `errorText`, `formatDuration` (Task 1).
- Produces: `<TrackRow track ondelete(path) />`.

Behavior (spec §7, §6.5, §6.6): artist list (desktop sidebar), album cards with tracks, filter box, inline delete confirm (`DELETE /api/library/track`), "สแกนโฟลเดอร์" (`POST /api/library/rescan`, for files added through SMB) and "ให้ Jellyfin สแกน" (`POST /api/jellyfin/refresh`).

- [ ] **Step 1: Write the failing test**

`app/frontend/src/lib/components/TrackRow.test.ts`:

```ts
import { fireEvent, render, screen } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import { ApiError } from '$lib/api';
import { makeTrack } from '$lib/testData';
import TrackRow from './TrackRow.svelte';

describe('TrackRow', () => {
	it('asks before deleting', async () => {
		const ondelete = vi.fn().mockResolvedValue(undefined);
		render(TrackRow, { track: makeTrack(), ondelete });
		await fireEvent.click(screen.getByRole('button', { name: 'ลบ Numb' }));
		expect(ondelete).not.toHaveBeenCalled();
		await fireEvent.click(screen.getByRole('button', { name: 'ไม่ลบ' }));
		expect(screen.queryByText('ลบไฟล์นี้จริงไหม?')).toBeNull();

		await fireEvent.click(screen.getByRole('button', { name: 'ลบ Numb' }));
		await fireEvent.click(screen.getByRole('button', { name: 'ลบเลย' }));
		expect(ondelete).toHaveBeenCalledWith('Linkin_Park/Singles/Numb.m4a');
	});

	it('shows the error when the delete fails', async () => {
		const ondelete = vi.fn().mockRejectedValue(new ApiError(404, 'track not found'));
		render(TrackRow, { track: makeTrack(), ondelete });
		await fireEvent.click(screen.getByRole('button', { name: 'ลบ Numb' }));
		await fireEvent.click(screen.getByRole('button', { name: 'ลบเลย' }));
		expect(await screen.findByRole('alert')).toHaveTextContent('track not found');
		expect(screen.getByRole('button', { name: 'ลบเลย' })).toBeEnabled();
	});
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npx vitest run src/lib/components/TrackRow.test.ts`
Expected: FAIL, `Failed to resolve import "./TrackRow.svelte"`.

- [ ] **Step 3: Write the component and the page**

`app/frontend/src/lib/components/TrackRow.svelte`:

```svelte
<script lang="ts">
	import { errorText, formatDuration } from '$lib/format';
	import type { LibraryTrack } from '$lib/types';

	type Props = { track: LibraryTrack; ondelete: (path: string) => Promise<void> | void };
	let { track, ondelete }: Props = $props();

	let confirming = $state(false);
	let busy = $state(false);
	let error = $state<string | null>(null);

	async function confirmDelete() {
		busy = true;
		error = null;
		try {
			await ondelete(track.path);
			confirming = false;
		} catch (e) {
			error = errorText(e);
		} finally {
			busy = false;
		}
	}
</script>

<li class="flex flex-wrap items-center gap-2 border-b border-ink/20 py-2 last:border-b-0">
	<span class="w-6 shrink-0 font-mono text-xs text-muted">{track.track_no ?? '·'}</span>
	<span class="min-w-0 flex-1 truncate" title={track.path}>{track.title}</span>
	<span class="font-mono text-xs text-muted">{formatDuration(track.duration)}</span>
	{#if confirming}
		<span class="text-sm">ลบไฟล์นี้จริงไหม?</span>
		<button class="btn btn-primary" onclick={confirmDelete} disabled={busy}>ลบเลย</button>
		<button class="btn" onclick={() => (confirming = false)} disabled={busy}>ไม่ลบ</button>
	{:else}
		<button class="btn" aria-label={`ลบ ${track.title}`} onclick={() => (confirming = true)}>ลบ</button>
	{/if}
	{#if error}
		<p role="alert" class="w-full text-sm text-orange">{error}</p>
	{/if}
</li>
```

`app/frontend/src/routes/library/+page.svelte`:

```svelte
<script lang="ts">
	import { api } from '$lib/client';
	import TrackRow from '$lib/components/TrackRow.svelte';
	import { errorText } from '$lib/format';
	import { library } from '$lib/library.svelte';
	import { filterLibrary } from '$lib/libraryFilter';

	let filter = $state('');
	let busy = $state<'rescan' | 'jellyfin' | null>(null);
	let notice = $state<string | null>(null);
	let error = $state<string | null>(null);

	const shown = $derived(filterLibrary(library.artists, filter));

	async function remove(path: string) {
		await api.deleteTrack(path);
		await library.load();
	}

	async function run(kind: 'rescan' | 'jellyfin') {
		busy = kind;
		notice = null;
		error = null;
		try {
			if (kind === 'rescan') {
				const { tracks } = await api.rescanLibrary();
				await library.load();
				notice = `สแกนโฟลเดอร์แล้ว พบ ${tracks} เพลง`;
			} else {
				const { ok } = await api.refreshJellyfin();
				notice = ok ? 'สั่ง Jellyfin สแกนแล้ว' : 'ติดต่อ Jellyfin ไม่ได้';
			}
		} catch (e) {
			error = errorText(e);
		} finally {
			busy = null;
		}
	}
</script>

<div class="space-y-6">
	<div class="flex flex-wrap items-center gap-2">
		<h1 class="mr-auto text-2xl font-bold">คลังเพลง</h1>
		<button class="btn" onclick={() => run('rescan')} disabled={busy !== null}>
			{busy === 'rescan' ? 'กำลังสแกน…' : 'สแกนโฟลเดอร์'}
		</button>
		<button class="btn btn-teal" onclick={() => run('jellyfin')} disabled={busy !== null}>
			{busy === 'jellyfin' ? 'กำลังสั่ง…' : 'ให้ Jellyfin สแกน'}
		</button>
	</div>

	<input class="input" bind:value={filter} placeholder="กรองตามศิลปิน อัลบั้ม หรือชื่อเพลง" aria-label="กรองคลังเพลง" />

	{#if notice}
		<p role="status" class="card bg-yellow p-3">{notice}</p>
	{/if}
	{#if error}
		<p role="alert" class="card p-3 text-orange">{error}</p>
	{/if}

	{#if !library.loaded}
		<p class="text-muted">กำลังโหลด…</p>
	{:else if shown.length === 0}
		<p class="text-muted">{filter.trim() ? 'ไม่พบเพลงที่ตรงกับคำค้น' : 'คลังยังว่าง ลองโหลดเพลงจากหน้าค้นหา'}</p>
	{:else}
		<div class="grid gap-6 md:grid-cols-[200px_1fr]">
			<nav class="hidden md:block" aria-label="ศิลปิน">
				<ul class="sticky top-4 space-y-1">
					{#each shown as artist, i (artist.artist)}
						<li><a class="block truncate py-1 text-sm hover:text-teal" href={`#artist-${i}`}>{artist.artist}</a></li>
					{/each}
				</ul>
			</nav>
			<div class="min-w-0 space-y-8">
				{#each shown as artist, i (artist.artist)}
					<section id={`artist-${i}`} class="space-y-3">
						<h2 class="text-xl font-bold">{artist.artist}</h2>
						{#each artist.albums as album (album.album)}
							<article class="card p-4">
								<h3 class="font-semibold">
									{album.album}
									<span class="font-mono text-xs text-muted">· {album.tracks.length} เพลง</span>
								</h3>
								<ul>
									{#each album.tracks as track (track.path)}
										<TrackRow {track} ondelete={remove} />
									{/each}
								</ul>
							</article>
						{/each}
					</section>
				{/each}
			</div>
		</div>
	{/if}
</div>
```

- [ ] **Step 4: Run all tests, check and build**

Run: `npm test && npm run check && npm run build`
Expected: `Tests  47 passed (47)`; `0 ERRORS 0 WARNINGS`; build OK.

- [ ] **Step 5: Manual check** (dev backend + `npm run dev`)

1. Open `/library`. Expected: the downloaded tracks grouped by artist and album.
2. Type "numb" in the filter. Expected: only matching tracks stay.
3. Click "ลบ" on a track, then "ไม่ลบ". Expected: nothing is deleted. Click "ลบ", then "ลบเลย". Expected: the track disappears and the file is gone from `/tmp/wyc-dev/music`.
4. Click "สแกนโฟลเดอร์". Expected: "สแกนโฟลเดอร์แล้ว พบ N เพลง". Click "ให้ Jellyfin สแกน". Expected (no Jellyfin on the dev machine): "ติดต่อ Jellyfin ไม่ได้".

- [ ] **Step 6: Commit**

```bash
git add app/frontend/src
git commit -m "feat(frontend): add library page with filter and inline delete confirm"
```

---

### Task 7: Deploy the frontend on the NAS

**Files:**
- Modify: `app/deploy/nas-setup.sh` (install nvm + Node LTS for `wick`)
- Modify: `app/README.md` (NAS step 2: Node)
- Modify: `docs/superpowers/specs/2026-11-05-wyc-music-streaming-design.md` §11 item 4

- [ ] **Step 1: Add Node to `nas-setup.sh`**

In `app/deploy/nas-setup.sh`, after the line `/usr/local/bin/deno --version | head -1` (end of step 2), add:

```bash

step "2b. Node for the frontend build (nvm, as $USER)"
export NVM_DIR="$HOME/.nvm"
if [[ ! -s $NVM_DIR/nvm.sh ]]; then
  curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.8/install.sh | PROFILE=/dev/null bash
fi
# shellcheck source=/dev/null
source "$NVM_DIR/nvm.sh"
nvm install --lts
node --version
```

Run: `bash -n app/deploy/nas-setup.sh`
Expected: no output (syntax OK).

- [ ] **Step 2: Document Node in `app/README.md`**

In "NAS: one-time setup", step 2, add after the `deno --version` line inside the code block:

```
curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.8/install.sh | bash   # as wick, no sudo
source ~/.nvm/nvm.sh && nvm install --lts && node --version
```

- [ ] **Step 3: Commit and push**

```bash
git add app/deploy/nas-setup.sh app/README.md
git commit -m "feat(deploy): install Node through nvm for the frontend build"
git push origin main
```

- [ ] **Step 4: Deploy on the NAS (with the user)**

On the NAS as `wick`:

```bash
curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.8/install.sh | bash
source ~/.nvm/nvm.sh && nvm install --lts && node --version
sudo /opt/wyc-music-streaming/repo/app/deploy/update.sh
ls /opt/wyc-music-streaming/repo/app/frontend/build/index.html
bash /opt/wyc-music-streaming/repo/app/deploy/check-nas.sh
```

Expected: `node --version` prints `v24.x`; `update.sh` prints `== frontend` and the Vite build output, then `active (running)`; `build/index.html` exists; `check-nas.sh` shows `OK` for nvm and no FAIL.

- [ ] **Step 5: Smoke test from a tailnet device (with the user)**

Open `https://<nas>.<tailnet>.ts.net/` on a phone and on a laptop:

1. The search page loads with the Cassette style and self-hosted fonts.
2. Search, download one new track. The deck shows live progress; the track appears in `/library` and in Jellyfin.
3. `/queue` shows the job as "เสร็จแล้ว" with its path.
4. Delete the test track in `/library` (confirm). The file is gone on the NAS.
5. Reload `/library` directly (deep link). The page loads (SPA fallback).
6. From a device whose Tailscale login is not in config: `/denied` shows that login.

- [ ] **Step 6: Record the results and commit**

In spec §11, replace item 4 with:

```markdown
4. ~~Node on 20.04~~: **verified <date>**. nvm 0.40.8, Node <version> (glibc 2.31). `npm ci && npm run build` works on the NAS; the frontend smoke test passed (search, download with live progress, queue, library delete, deep link, `/denied`).
```

```bash
git add docs/superpowers/specs/2026-11-05-wyc-music-streaming-design.md
git commit -m "docs(spec): record frontend deploy on the NAS"
git push origin main
```
