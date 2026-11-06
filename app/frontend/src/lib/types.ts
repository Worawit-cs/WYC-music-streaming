// Shapes returned by the backend API (app/backend/wyc_music_streaming/api.py).

export type Me = { name: string; login: string; jellyfin_user: string | null };

export type Suggested = { title: string; artist: string; album: string };

export type SearchResult = {
	video_id: string;
	title: string;
	channel: string;
	duration: number | null;
	thumbnail_url: string;
	suggested: Suggested;
	in_library: boolean;
};

export type SearchResponse = {
	kind: 'search' | 'url' | 'playlist';
	playlist_title: string | null;
	results: SearchResult[];
};

export type JobStatus = 'queued' | 'downloading' | 'done' | 'failed' | 'cancelled';

export type Job = {
	id: number;
	user: string;
	video_id: string;
	title: string;
	artist: string;
	album: string;
	track_no: number | null;
	year: string | null;
	cover_url: string | null;
	box_id: string | null;
	status: JobStatus;
	progress: number;
	error: string | null;
	final_path: string | null;
	created_at: string;
	updated_at: string;
};

export type JobItem = {
	video_id: string;
	title: string;
	artist: string;
	album: string;
	track_no?: number | null;
	year?: string | null;
	cover_url?: string | null;
};

export type SkipReason = 'duplicate' | 'in_library' | 'active';

export type CreateJobsResponse = {
	created: Job[];
	skipped: { video_id: string; reason: SkipReason }[];
};

export type LibraryTrack = {
	path: string;
	title: string;
	artist: string;
	album: string;
	duration: number | null;
	video_id: string | null;
	track_no: number | null;
};

export type LibraryAlbum = { album: string; tracks: LibraryTrack[] };

export type LibraryArtist = { artist: string; albums: LibraryAlbum[] };
