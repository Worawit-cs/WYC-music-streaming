import type { Job } from './types';

export function isActive(job: Job): boolean {
	return job.status === 'queued' || job.status === 'downloading';
}

/** Active jobs first (oldest first, the worker order), then finished jobs (newest first). */
export function sortJobs(list: Job[]): Job[] {
	const active = list.filter(isActive).sort((a, b) => a.id - b.id);
	const finished = list
		.filter((j) => !isActive(j))
		.sort((a, b) => b.updated_at.localeCompare(a.updated_at) || b.id - a.id);
	return [...active, ...finished];
}

/** Insert or replace a job by id (from an SSE "job" event or an API response). */
export function upsertJob(list: Job[], job: Job): Job[] {
	return sortJobs([...list.filter((j) => j.id !== job.id), job]);
}
