import { isActive } from './jobList';
import type { CreateJobsResponse, Job, JobItem, SearchResult } from './types';

/** The editable "tape label" for one track. */
export type Draft = { video_id: string; title: string; artist: string; album: string };

/** What a search result card can offer. */
export type CardState = 'new' | 'active' | 'in_library';

const FIELDS = [
	['title', 'ชื่อเพลง'],
	['artist', 'ศิลปิน'],
	['album', 'อัลบั้ม']
] as const;

export function draftFrom(result: SearchResult): Draft {
	return { video_id: result.video_id, ...result.suggested };
}

/** null when the draft is valid, else one message for the user. Limits match the backend (300). */
export function validateDraft(draft: Draft): string | null {
	for (const [key, label] of FIELDS) {
		const value = draft[key].trim();
		if (!value) return `กรอก${label}ก่อน`;
		if (value.length > 300) return `${label}ยาวเกิน 300 ตัวอักษร`;
	}
	return null;
}

/** A non-blank albumOverride replaces the album (one album field for a whole playlist). */
export function toJobItem(draft: Draft, albumOverride?: string): JobItem {
	return {
		video_id: draft.video_id,
		title: draft.title.trim(),
		artist: draft.artist.trim(),
		album: albumOverride?.trim() || draft.album.trim()
	};
}

export function cardState(videoId: string, libraryIds: ReadonlySet<string>, jobs: Job[]): CardState {
	if (libraryIds.has(videoId)) return 'in_library';
	if (jobs.some((j) => j.video_id === videoId && isActive(j))) return 'active';
	return 'new';
}

/** Playlist mode: tick every entry that is not in the library yet. */
export function defaultSelection(results: SearchResult[], libraryIds: ReadonlySet<string>): string[] {
	return results.filter((r) => !libraryIds.has(r.video_id)).map((r) => r.video_id);
}

export function summarizeCreate(res: CreateJobsResponse): string {
	const parts: string[] = [];
	if (res.created.length) parts.push(`เพิ่ม ${res.created.length} เพลงเข้าคิวแล้ว`);
	if (res.skipped.length) parts.push(`ข้าม ${res.skipped.length} เพลงที่มีในคลังหรืออยู่ในคิวแล้ว`);
	return parts.join(' · ') || 'ไม่มีเพลงที่ต้องโหลด';
}
