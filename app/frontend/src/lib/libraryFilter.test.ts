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
