<script lang="ts">
	import { percent, stageText } from '$lib/format';
	import type { Job } from '$lib/types';

	let { job }: { job: Job | null } = $props();

	// A number only while bytes arrive; before and after that the bar shows moving stripes.
	const counting = $derived(job?.stage === 'downloading');
	const width = $derived(!job ? '0%' : job.stage === 'downloading' ? percent(job.progress) : '100%');
</script>

<section class="card space-y-3 p-4" aria-label="เครื่องอัดเทป">
	<p class="label">กำลังอัดเทป</p>
	<div class="flex items-center justify-center gap-6 rounded-md border-2 border-ink bg-ink py-4">
		{#each [0, 1] as reel (reel)}
			<span
				aria-hidden="true"
				class={[
					'h-12 w-12 rounded-full border-4 border-dashed border-card bg-orange',
					job && 'motion-safe:animate-[spin_3s_linear_infinite]'
				]}
			></span>
		{/each}
	</div>
	{#if job}
		<div class="min-w-0">
			<p class="truncate font-semibold">{job.title}</p>
			<p class="truncate text-sm text-muted">{job.artist}</p>
		</div>
		<div
			class="h-3 overflow-hidden rounded border-2 border-ink bg-ground"
			role="progressbar"
			aria-label="ความคืบหน้า"
			aria-valuemin={0}
			aria-valuemax={100}
			aria-valuenow={counting ? Math.round(job.progress * 100) : undefined}
			aria-valuetext={stageText(job)}
		>
			<div class={['h-full bg-teal transition-[width]', !counting && 'bar-stripes']} style:width={width}></div>
		</div>
		<p class="text-right font-mono text-xs">{stageText(job)}</p>
	{:else}
		<p class="text-sm text-muted">เครื่องว่าง เลือกเพลงเพื่อเริ่มอัด</p>
	{/if}
</section>
