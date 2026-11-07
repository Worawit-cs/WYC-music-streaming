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
