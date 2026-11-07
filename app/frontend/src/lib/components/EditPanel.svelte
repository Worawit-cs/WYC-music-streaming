<script lang="ts">
	import { albumOptions, artistOptions } from '$lib/libraryOptions';
	import { validateDraft, type Draft } from '$lib/selection';
	import type { LibraryArtist } from '$lib/types';
	import Combobox from './Combobox.svelte';

	type Props = {
		draft: Draft;
		/** The library tree, for the artist and album lists. */
		artists?: LibraryArtist[];
		/** The artist YouTube suggested, shown in the list when the prefill differs. */
		youtubeArtist?: string;
		busy?: boolean;
		error?: string | null;
		onsubmit: (draft: Draft) => void;
		oncancel: () => void;
	};
	let { draft, artists = [], youtubeArtist, busy = false, error = null, onsubmit, oncancel }: Props = $props();

	// Writable deriveds: they reset when the parent passes a new draft.
	let title = $derived(draft.title);
	let artist = $derived(draft.artist);
	let album = $derived(draft.album);

	const artistRows = $derived(artistOptions(artists, youtubeArtist));
	const albumRows = $derived(albumOptions(artists, artist));

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
	<Combobox bind:value={artist} options={artistRows} label="ศิลปิน" maxlength={300} createLabel="สร้างใหม่" filter />
	<Combobox bind:value={album} options={albumRows} label="อัลบั้ม" maxlength={300} createLabel="สร้างใหม่" filter />
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
