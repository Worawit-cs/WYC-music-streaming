// Small factories shared by the unit tests.
import type { Job, LibraryArtist, LibraryTrack, SearchResult } from './types';

export function makeJob(overrides: Partial<Job> = {}): Job {
	return {
		id: 1,
		user: 'wick',
		video_id: 'kXYiU_JCYtU',
		title: 'Numb',
		artist: 'Linkin Park',
		album: 'Singles',
		track_no: null,
		year: null,
		cover_url: null,
		box_id: null,
		status: 'queued',
		progress: 0,
		error: null,
		final_path: null,
		created_at: '2026-11-06T15:00:00Z',
		updated_at: '2026-11-06T15:00:00Z',
		stage: null,
		...overrides
	};
}

export function makeResult(overrides: Partial<SearchResult> = {}): SearchResult {
	return {
		video_id: 'kXYiU_JCYtU',
		title: 'Numb (Official Music Video) [4K UPGRADE] – Linkin Park',
		channel: 'Linkin Park',
		duration: 188,
		thumbnail_url: 'https://i.ytimg.com/vi/kXYiU_JCYtU/mqdefault.jpg',
		suggested: { title: 'Numb', artist: 'Linkin Park', album: 'Singles' },
		in_library: false,
		...overrides
	};
}

export function makeTrack(overrides: Partial<LibraryTrack> = {}): LibraryTrack {
	return {
		path: 'Linkin_Park/Singles/Numb.m4a',
		title: 'Numb',
		artist: 'Linkin Park',
		album: 'Singles',
		duration: 188,
		video_id: 'kXYiU_JCYtU',
		track_no: null,
		...overrides
	};
}

export const LIBRARY: LibraryArtist[] = [
	{
		artist: 'Linkin Park',
		albums: [
			{
				album: 'Meteora',
				tracks: [
					makeTrack({ path: 'Linkin_Park/Meteora/07_Faint.m4a', title: 'Faint', album: 'Meteora', video_id: 'aaaaaaaaaaa', track_no: 7 }),
					makeTrack({ path: 'Linkin_Park/Meteora/13_Numb.m4a', title: 'Numb', album: 'Meteora', video_id: null, track_no: 13 })
				]
			},
			{ album: 'Singles', tracks: [makeTrack()] }
		]
	},
	{
		artist: 'Sade',
		albums: [
			{
				album: 'Diamond Life',
				tracks: [makeTrack({ path: 'Sade/Diamond_Life/Smooth_Operator.m4a', title: 'Smooth Operator', artist: 'Sade', album: 'Diamond Life', video_id: '4TYv2PhG89A' })]
			}
		]
	}
];
