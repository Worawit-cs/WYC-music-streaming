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
