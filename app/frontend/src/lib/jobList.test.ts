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
