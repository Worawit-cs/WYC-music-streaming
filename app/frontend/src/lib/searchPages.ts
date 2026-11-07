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
