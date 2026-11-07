import { describe, expect, it } from 'vitest';
import { matchArtist } from './artistMatch';

const NAMES = ['The Weeknd', 'Linkin Park', 'JENNIE', 'The Weeknd Tribute'];

describe('matchArtist', () => {
	it('returns the library spelling on an exact match, ignoring case and spaces', () => {
		expect(matchArtist('  the weeknd ', NAMES)).toBe('The Weeknd');
	});

	it.each([
		'The Weeknd, JENNIE & Lily Rose Depp',
		'The Weeknd & Ariana Grande',
		'The Weeknd x Playboi Carti',
		'The Weeknd X Playboi Carti',
		'The Weeknd feat. Daft Punk',
		'The Weeknd feat Daft Punk',
		'The Weeknd ft. Kendrick Lamar',
		'The Weeknd ft Kendrick Lamar',
		'The Weeknd with Madonna',
		'The Weeknd and Lana Del Rey',
		'The Weeknd / Daft Punk'
	])('picks the library artist at the start of %s', (guess) => {
		expect(matchArtist(guess, NAMES)).toBe('The Weeknd');
	});

	it('prefers the longest library name', () => {
		expect(matchArtist('The Weeknd Tribute, Someone', NAMES)).toBe('The Weeknd Tribute');
	});

	it('needs a separator after the name', () => {
		expect(matchArtist('The Weekndz', NAMES)).toBe('The Weekndz');
		expect(matchArtist('Linkin Parkway & Co', NAMES)).toBe('Linkin Parkway & Co');
		expect(matchArtist('JENNIEx Lisa', NAMES)).toBe('JENNIEx Lisa');
	});

	it('keeps the guess when nothing matches', () => {
		expect(matchArtist('Sade', NAMES)).toBe('Sade');
		expect(matchArtist('Sade', [])).toBe('Sade');
		expect(matchArtist('Sade', ['', '  '])).toBe('Sade');
	});
});
