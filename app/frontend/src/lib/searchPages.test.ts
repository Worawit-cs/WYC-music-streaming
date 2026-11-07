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
