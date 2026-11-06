import { api } from './client';
import { libraryVideoIds, trackCount } from './libraryFilter';
import type { LibraryArtist } from './types';

class LibraryState {
	artists = $state<LibraryArtist[]>([]);
	loaded = $state(false);
	videoIds = $derived(libraryVideoIds(this.artists));
	trackCount = $derived(trackCount(this.artists));

	async load() {
		this.artists = (await api.library()).artists;
		this.loaded = true;
	}
}

export const library = new LibraryState();
