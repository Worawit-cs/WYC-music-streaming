<script lang="ts">
	import { api } from '$lib/client';
	import JobRow from '$lib/components/JobRow.svelte';
	import { errorText } from '$lib/format';
	import { isActive } from '$lib/jobList';
	import { jobs } from '$lib/jobs.svelte';

	let error = $state<string | null>(null);
	const finished = $derived(jobs.list.filter((j) => !isActive(j)));

	async function retry(id: number) {
		error = null;
		try {
			jobs.apply(await api.retryJob(id));
		} catch (e) {
			error = errorText(e);
		}
	}

	async function cancel(id: number) {
		error = null;
		try {
			await api.cancelJob(id);
			await jobs.load();
		} catch (e) {
			error = errorText(e);
		}
	}
</script>

<div class="space-y-6">
	<h1 class="text-2xl font-bold">คิวดาวน์โหลด</h1>
	{#if error}
		<p role="alert" class="card p-3 text-orange">{error}</p>
	{/if}

	<section class="space-y-3">
		<h2 class="label">กำลังทำ ({jobs.active.length})</h2>
		{#if jobs.active.length === 0}
			<p class="text-muted">ไม่มีงานค้าง</p>
		{:else}
			<ul class="space-y-3">
				{#each jobs.active as job (job.id)}
					<JobRow {job} onretry={retry} oncancel={cancel} />
				{/each}
			</ul>
		{/if}
	</section>

	<section class="space-y-3">
		<h2 class="label">ประวัติ (50 งานล่าสุด)</h2>
		{#if finished.length === 0}
			<p class="text-muted">ยังไม่มีประวัติ</p>
		{:else}
			<ul class="space-y-3">
				{#each finished as job (job.id)}
					<JobRow {job} onretry={retry} oncancel={cancel} />
				{/each}
			</ul>
		{/if}
	</section>
</div>
