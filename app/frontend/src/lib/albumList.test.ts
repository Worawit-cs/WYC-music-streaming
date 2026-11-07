import { describe, expect, it } from 'vitest';
import { albumList } from './albumList';
import { LIBRARY, makeTrack } from './testData';
import type { LibraryArtist } from './types';

describe('albumList', () => {
	it('makes one card per artist and album, sorted by album then artist', () => {
		const cards = albumList(LIBRARY);
		expect(cards.map((c) => [c.album, c.artist, c.tracks.length])).toEqual([
			['Diamond Life', 'Sade', 1],
			['Meteora', 'Linkin Park', 2],
			['Singles', 'Linkin Park', 1]
		]);
	});

	it('keeps Singles of two artists as two cards with different keys', () => {
		const artists: LibraryArtist[] = [
			{ artist: 'The Weeknd', albums: [{ album: 'Singles', tracks: [makeTrack()] }] },
			{ artist: 'Linkin Park', albums: [{ album: 'Singles', tracks: [makeTrack()] }] }
		];
		const cards = albumList(artists);
		expect(cards.map((c) => c.artist)).toEqual(['Linkin Park', 'The Weeknd']);
		expect(new Set(cards.map((c) => c.key)).size).toBe(2);
	});

	it('sorts with the Thai locale (Thai before Latin) and ignores case', () => {
		const artists: LibraryArtist[] = [
			{
				artist: 'A',
				albums: [
					{ album: 'ไทย', tracks: [] },
					{ album: 'beta', tracks: [] },
					{ album: 'Alpha', tracks: [] }
				]
			}
		];
		expect(albumList(artists).map((c) => c.album)).toEqual(['ไทย', 'Alpha', 'beta']);
	});

	it('returns an empty list for an empty library', () => {
		expect(albumList([])).toEqual([]);
	});
});
