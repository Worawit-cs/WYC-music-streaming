import { describe, expect, it } from 'vitest';
import { albumOptions, artistOptions, libraryMatches } from './libraryOptions';
import { LIBRARY } from './testData';

describe('artistOptions', () => {
	it('lists every library artist with a track count hint', () => {
		expect(artistOptions(LIBRARY)).toEqual([
			{ value: 'Linkin Park', label: 'Linkin Park', hint: '3 เพลง' },
			{ value: 'Sade', label: 'Sade', hint: '1 เพลง' }
		]);
	});

	it('puts a new YouTube guess first', () => {
		const out = artistOptions(LIBRARY, 'Linkin Park, Jay-Z');
		expect(out[0]).toEqual({ value: 'Linkin Park, Jay-Z', label: 'Linkin Park, Jay-Z', hint: 'ชื่อจาก YouTube' });
		expect(out).toHaveLength(3);
	});

	it('skips the guess when it is already a library artist', () => {
		expect(artistOptions(LIBRARY, ' sade ').map((o) => o.value)).toEqual(['Linkin Park', 'Sade']);
	});
});

describe('albumOptions', () => {
	it('lists the albums of the artist, ignoring case', () => {
		expect(albumOptions(LIBRARY, 'linkin park')).toEqual([
			{ value: 'Meteora', label: 'Meteora', hint: '2 เพลง' },
			{ value: 'Singles', label: 'Singles', hint: '1 เพลง' }
		]);
	});

	it('is empty for a new artist', () => {
		expect(albumOptions(LIBRARY, 'Nobody')).toEqual([]);
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
