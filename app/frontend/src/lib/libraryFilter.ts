import type { LibraryArtist } from './types';

/**
 * Keep what matches q (case-insensitive): a matching artist keeps all its albums,
 * a matching album keeps all its tracks, otherwise only matching track titles stay.
 */
export function filterLibrary(artists: LibraryArtist[], q: string): LibraryArtist[] {
	const needle = q.trim().toLowerCase();
	if (!needle) return artists;
	const hit = (s: string) => s.toLowerCase().includes(needle);
	const out: LibraryArtist[] = [];
	for (const artist of artists) {
		if (hit(artist.artist)) {
			out.push(artist);
			continue;
		}
		const albums = artist.albums
			.map((album) =>
				hit(album.album) ? album : { ...album, tracks: album.tracks.filter((t) => hit(t.title)) }
			)
			.filter((album) => album.tracks.length > 0);
		if (albums.length) out.push({ ...artist, albums });
	}
	return out;
}

export function libraryVideoIds(artists: LibraryArtist[]): Set<string> {
	const ids = new Set<string>();
	for (const artist of artists)
		for (const album of artist.albums)
			for (const track of album.tracks) if (track.video_id) ids.add(track.video_id);
	return ids;
}

export function trackCount(artists: LibraryArtist[]): number {
	return artists.reduce((n, a) => n + a.albums.reduce((m, al) => m + al.tracks.length, 0), 0);
}
