import { noteTransition } from './batch';
import { api } from './client';
import { isActive, sortJobs, upsertJob } from './jobList';
import type { Job } from './types';

class JobsState {
	list = $state<Job[]>([]);
	active = $derived(this.list.filter(isActive));
	current = $derived(this.list.find((j) => j.status === 'downloading') ?? null);
	queued = $derived(this.list.filter((j) => j.status === 'queued'));
	/** Jobs that ended (done or failed) while this page was open, since the last dialog. */
	finished = $state<Job[]>([]);
	/** Open the "done" dialog: something ended and nothing is left in the queue. */
	showDone = $derived(this.finished.length > 0 && this.active.length === 0);

	async load() {
		const before = new Map(this.list.map((j) => [j.id, j]));
		this.list = sortJobs((await api.listJobs()).jobs);
		for (const job of this.list) this.note(before.get(job.id), job);
	}

	apply(job: Job) {
		this.note(this.list.find((j) => j.id === job.id), job);
		this.list = upsertJob(this.list, job);
	}

	dismissDone() {
		this.finished = [];
	}

	private note(prev: Job | undefined, next: Job) {
		if (noteTransition(prev, next)) this.finished = [...this.finished.filter((j) => j.id !== next.id), next];
	}
}

export const jobs = new JobsState();
