import type { ComboOption, LibraryArtist } from './types';

const fold = (s: string) => s.trim().toLowerCase();
const count = (n: number) => `${n} เพลง`;

/** Artist combobox rows: every library artist, plus the YouTube guess on top when it is not one of them. */
export function artistOptions(artists: LibraryArtist[], youtubeGuess?: string): ComboOption[] {
	const rows: ComboOption[] = artists.map((a) => ({
		value: a.artist,
		label: a.artist,
		hint: count(a.albums.reduce((n, al) => n + al.tracks.length, 0))
	}));
	const guess = youtubeGuess?.trim();
	if (guess && !artists.some((a) => fold(a.artist) === fold(guess))) {
		rows.unshift({ value: guess, label: guess, hint: 'ชื่อจาก YouTube' });
	}
	return rows;
}

/** Album combobox rows: the albums of the artist named in the artist field (empty for a new artist). */
export function albumOptions(artists: LibraryArtist[], artist: string): ComboOption[] {
	const albums = artists.find((a) => fold(a.artist) === fold(artist))?.albums ?? [];
	return albums.map((al) => ({ value: al.album, label: al.album, hint: count(al.tracks.length) }));
}

/** Search-box rows from the library: artist names first, then track titles. */
export function libraryMatches(artists: LibraryArtist[], typed: string, limit = 3): string[] {
	const needle = fold(typed);
	if (!needle) return [];
	const out: string[] = [];
	const add = (s: string) => {
		if (out.length < limit && fold(s).includes(needle) && !out.some((o) => fold(o) === fold(s))) out.push(s);
	};
	for (const a of artists) add(a.artist);
	for (const a of artists) for (const al of a.albums) for (const t of al.tracks) add(t.title);
	return out;
}
