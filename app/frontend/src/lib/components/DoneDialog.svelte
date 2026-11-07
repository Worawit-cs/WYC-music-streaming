<script lang="ts">
	import type { Job } from '$lib/types';

	type Props = { finished: Job[]; onclose: () => void };
	let { finished, onclose }: Props = $props();

	let dialog = $state<HTMLDialogElement | null>(null);
	let closeButton = $state<HTMLButtonElement | null>(null);

	const done = $derived(finished.filter((j) => j.status === 'done'));
	const failed = $derived(finished.filter((j) => j.status === 'failed'));
	const title = $derived(done.length ? `อัดเทปเสร็จแล้ว ${done.length} เพลง` : 'อัดเทปไม่สำเร็จ');

	$effect(() => {
		if (!dialog || dialog.open) return;
		dialog.showModal();
		closeButton?.focus();
	});

	const line = (j: Job) => `${j.title} · ${j.artist} / ${j.album}`;
</script>

<dialog
	bind:this={dialog}
	aria-labelledby="done-title"
	class="card m-auto w-[min(32rem,calc(100vw-2rem))] p-0 backdrop:bg-ink/50"
	oncancel={(e) => {
		e.preventDefault();
		onclose();
	}}
>
	<div class="space-y-4 p-5">
		<h2 id="done-title" class="text-xl font-bold">{title}</h2>
		{#if done.length}
			<ul class="max-h-[50vh] space-y-1 overflow-auto">
				{#each done as job (job.id)}
					<li class="flex gap-2">
						<span aria-hidden="true" class="text-teal">✓</span>
						<span class="min-w-0 break-words">{line(job)}</span>
					</li>
				{/each}
			</ul>
		{/if}
		{#if failed.length}
			<div class="space-y-1 rounded-md border-2 border-orange p-3">
				<p class="font-semibold text-orange">โหลดไม่ได้ {failed.length} เพลง</p>
				<ul class="space-y-1">
					{#each failed as job (job.id)}
						<li class="flex gap-2">
							<span aria-hidden="true" class="text-orange">✗</span>
							<span class="min-w-0 break-words">{line(job)}</span>
						</li>
					{/each}
				</ul>
				<a href="/queue" class="text-sm text-teal underline" onclick={onclose}>ดูคิว</a>
			</div>
		{/if}
		<div class="flex flex-wrap justify-end gap-2">
			<a href="/library" class="btn btn-teal" onclick={onclose}>เปิดคลังเพลง</a>
			<button bind:this={closeButton} class="btn" onclick={onclose}>ปิด</button>
		</div>
	</div>
</dialog>
