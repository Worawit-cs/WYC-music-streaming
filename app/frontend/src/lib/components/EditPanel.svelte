<script lang="ts">
	import { validateDraft, type Draft } from '$lib/selection';

	type Props = {
		draft: Draft;
		busy?: boolean;
		error?: string | null;
		onsubmit: (draft: Draft) => void;
		oncancel: () => void;
	};
	let { draft, busy = false, error = null, onsubmit, oncancel }: Props = $props();

	// Writable deriveds: they reset when the parent passes a new draft.
	let title = $derived(draft.title);
	let artist = $derived(draft.artist);
	let album = $derived(draft.album);

	const current = $derived({ video_id: draft.video_id, title, artist, album });
	const problem = $derived(validateDraft(current));

	function submit(event: SubmitEvent) {
		event.preventDefault();
		if (!problem && !busy) onsubmit(current);
	}
</script>

<form class="card space-y-3 p-4" onsubmit={submit}>
	<h2 class="text-lg font-bold">เขียนฉลากเทป</h2>
	<label class="block space-y-1">
		<span class="label">ชื่อเพลง</span>
		<input class="input" bind:value={title} maxlength="300" />
	</label>
	<label class="block space-y-1">
		<span class="label">ศิลปิน</span>
		<input class="input" bind:value={artist} maxlength="300" />
	</label>
	<label class="block space-y-1">
		<span class="label">อัลบั้ม</span>
		<input class="input" bind:value={album} maxlength="300" />
	</label>
	{#if problem}
		<p role="alert" class="text-sm text-orange">{problem}</p>
	{/if}
	{#if error}
		<p role="alert" class="text-sm text-orange">{error}</p>
	{/if}
	<div class="flex flex-wrap gap-2">
		<button class="btn btn-primary" type="submit" disabled={!!problem || busy}>
			{busy ? 'กำลังส่ง…' : 'โหลดลงเทป'}
		</button>
		<button class="btn" type="button" onclick={oncancel}>ยกเลิก</button>
	</div>
</form>
