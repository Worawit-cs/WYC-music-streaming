<script lang="ts">
	import { percent, STATUS_LABEL } from '$lib/format';
	import type { Job } from '$lib/types';

	type Props = { job: Job; onretry: (id: number) => void; oncancel: (id: number) => void };
	let { job, onretry, oncancel }: Props = $props();

	const tone: Record<Job['status'], string> = {
		queued: 'bg-card',
		downloading: 'bg-yellow',
		done: 'bg-teal text-card',
		failed: 'bg-orange text-card',
		cancelled: 'bg-ground'
	};
</script>

<li class="card space-y-2 p-3">
	<div class="flex items-start gap-3">
		<div class="min-w-0 flex-1">
			<p class="truncate font-semibold">{job.title}</p>
			<p class="truncate text-sm text-muted">{job.artist} · {job.album}</p>
		</div>
		<span class={['shrink-0 rounded border-2 border-ink px-2 py-0.5 font-mono text-xs', tone[job.status]]}>
			{STATUS_LABEL[job.status]}
		</span>
	</div>
	{#if job.status === 'downloading'}
		<div
			class="h-3 overflow-hidden rounded border-2 border-ink bg-ground"
			role="progressbar"
			aria-label={`ความคืบหน้า ${job.title}`}
			aria-valuemin={0}
			aria-valuemax={100}
			aria-valuenow={Math.round(job.progress * 100)}
		>
			<div class="h-full bg-teal transition-[width]" style:width={percent(job.progress)}></div>
		</div>
	{/if}
	{#if job.status === 'failed' && job.error}
		<p class="text-sm break-words text-orange">{job.error}</p>
	{/if}
	{#if job.status === 'done' && job.final_path}
		<p class="font-mono text-xs break-all text-muted">{job.final_path}</p>
	{/if}
	{#if job.status === 'failed'}
		<button class="btn" onclick={() => onretry(job.id)}>ลองใหม่</button>
	{:else if job.status === 'queued'}
		<button class="btn" onclick={() => oncancel(job.id)}>ยกเลิก</button>
	{/if}
</li>
