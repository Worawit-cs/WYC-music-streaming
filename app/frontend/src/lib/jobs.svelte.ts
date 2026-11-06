import { api } from './client';
import { isActive, sortJobs, upsertJob } from './jobList';
import type { Job } from './types';

class JobsState {
	list = $state<Job[]>([]);
	active = $derived(this.list.filter(isActive));
	current = $derived(this.list.find((j) => j.status === 'downloading') ?? null);
	queued = $derived(this.list.filter((j) => j.status === 'queued'));

	async load() {
		this.list = sortJobs((await api.listJobs()).jobs);
	}

	apply(job: Job) {
		this.list = upsertJob(this.list, job);
	}
}

export const jobs = new JobsState();
