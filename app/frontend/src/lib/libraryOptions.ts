import type { ComboOption, LibraryArtist } from './types';

const fold = (s: string) => s.trim().toLowerCase();
const count = (n: number) => `${n} เพลง`;

/** Show everything when the text is empty or already one of the names (so the list acts like a select). */
function needleFor(typed: string, names: string[]): string {
	const t = fold(typed);
	return names.some((n) => fold(n) === t) ? '' : t;
}

/** Artist combobox rows: library artists that contain the text, plus the YouTube guess on top. */
export function artistOptions(
	artists: LibraryArtist[],
	typed: string,
	youtubeGuess?: string,
	limit = 8
): ComboOption[] {
	const needle = needleFor(typed, artists.map((a) => a.artist));
	const rows: ComboOption[] = artists
		.filter((a) => fold(a.artist).includes(needle))
		.map((a) => ({
			value: a.artist,
			label: a.artist,
			hint: count(a.albums.reduce((n, al) => n + al.tracks.length, 0))
		}));
	const guess = youtubeGuess?.trim();
	const guessIsNew = guess && fold(guess) !== fold(typed) && !artists.some((a) => fold(a.artist) === fold(guess));
	if (guessIsNew) rows.unshift({ value: guess, label: guess, hint: 'ชื่อจาก YouTube' });
	return rows.slice(0, limit);
}

/** Album combobox rows: albums of the artist named in the artist field. */
export function albumOptions(artists: LibraryArtist[], artist: string, typed: string, limit = 8): ComboOption[] {
	const albums = artists.find((a) => fold(a.artist) === fold(artist))?.albums ?? [];
	const needle = needleFor(typed, albums.map((al) => al.album));
	return albums
		.filter((al) => fold(al.album).includes(needle))
		.map((al) => ({ value: al.album, label: al.album, hint: count(al.tracks.length) }))
		.slice(0, limit);
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
