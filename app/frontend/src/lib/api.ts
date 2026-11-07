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
	async function request<T>(method: string, path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
		const init: RequestInit = { method };
		if (signal) init.signal = signal;
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
		search: (q: string, page = 1) =>
			request<SearchResponse>('GET', `/search?q=${encodeURIComponent(q)}&page=${page}`),
		suggest: (q: string, signal?: AbortSignal) =>
			request<{ suggestions: string[] }>('GET', `/suggest?q=${encodeURIComponent(q)}`, undefined, signal),
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
