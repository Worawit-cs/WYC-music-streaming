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
