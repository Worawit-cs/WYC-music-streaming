import type { LibraryArtist, LibraryTrack } from './types';

/** One album of one artist, for the library album view. */
export type AlbumCard = { key: string; album: string; artist: string; tracks: LibraryTrack[] };

const compare = (a: string, b: string) => a.localeCompare(b, 'th', { sensitivity: 'base' });

/** Flatten the artist tree into album cards, sorted by album name, then artist name. */
export function albumList(artists: LibraryArtist[]): AlbumCard[] {
	const cards = artists.flatMap((a) =>
		a.albums.map((al) => ({
			key: JSON.stringify([a.artist, al.album]),
			album: al.album,
			artist: a.artist,
			tracks: al.tracks
		}))
	);
	return cards.sort((x, y) => compare(x.album, y.album) || compare(x.artist, y.artist));
}
