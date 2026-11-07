import { describe, expect, it } from 'vitest';
import { albumOptions, artistOptions, libraryMatches } from './libraryOptions';
import { LIBRARY } from './testData';

describe('artistOptions', () => {
	it('lists artists that contain the typed text, with a track count hint', () => {
		expect(artistOptions(LIBRARY, 'park')).toEqual([
			{ value: 'Linkin Park', label: 'Linkin Park', hint: '3 เพลง' }
		]);
	});

	it('lists every artist when the text is empty or already an exact library name', () => {
		expect(artistOptions(LIBRARY, '').map((o) => o.value)).toEqual(['Linkin Park', 'Sade']);
		expect(artistOptions(LIBRARY, 'sade').map((o) => o.value)).toEqual(['Linkin Park', 'Sade']);
	});

	it('puts the YouTube guess first when it differs from the text', () => {
		const out = artistOptions(LIBRARY, 'Linkin Park', 'Linkin Park, Jay-Z');
		expect(out[0]).toEqual({ value: 'Linkin Park, Jay-Z', label: 'Linkin Park, Jay-Z', hint: 'ชื่อจาก YouTube' });
		expect(out.slice(1).map((o) => o.value)).toEqual(['Linkin Park', 'Sade']);
	});

	it('skips the guess when it is already a library artist', () => {
		expect(artistOptions(LIBRARY, 'Lin', 'Sade').map((o) => o.value)).toEqual(['Linkin Park']);
	});

	it('stops at the limit', () => {
		expect(artistOptions(LIBRARY, '', undefined, 1)).toHaveLength(1);
	});
});

describe('albumOptions', () => {
	it('lists the albums of the artist in the artist field', () => {
		expect(albumOptions(LIBRARY, 'linkin park', '')).toEqual([
			{ value: 'Meteora', label: 'Meteora', hint: '2 เพลง' },
			{ value: 'Singles', label: 'Singles', hint: '1 เพลง' }
		]);
	});

	it('filters by the typed text unless it is an exact album name', () => {
		expect(albumOptions(LIBRARY, 'Linkin Park', 'met').map((o) => o.value)).toEqual(['Meteora']);
		expect(albumOptions(LIBRARY, 'Linkin Park', 'singles').map((o) => o.value)).toEqual(['Meteora', 'Singles']);
	});

	it('is empty for a new artist', () => {
		expect(albumOptions(LIBRARY, 'Nobody', '')).toEqual([]);
	});
});

describe('libraryMatches', () => {
	it('finds artists first, then track titles, without duplicates', () => {
		expect(libraryMatches(LIBRARY, 'numb')).toEqual(['Numb']);
		expect(libraryMatches(LIBRARY, 'a')).toEqual(['Linkin Park', 'Sade', 'Faint']);
	});

	it('needs at least one non-space character', () => {
		expect(libraryMatches(LIBRARY, '  ')).toEqual([]);
	});
});
