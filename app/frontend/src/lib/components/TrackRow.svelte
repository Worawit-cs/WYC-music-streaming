<script lang="ts">
	import { errorText, formatDuration } from '$lib/format';
	import type { LibraryTrack } from '$lib/types';

	type Props = { track: LibraryTrack; ondelete: (path: string) => Promise<void> | void };
	let { track, ondelete }: Props = $props();

	let confirming = $state(false);
	let busy = $state(false);
	let error = $state<string | null>(null);

	async function confirmDelete() {
		busy = true;
		error = null;
		try {
			await ondelete(track.path);
			confirming = false;
		} catch (e) {
			error = errorText(e);
		} finally {
			busy = false;
		}
	}
</script>

<li class="flex flex-wrap items-center gap-2 border-b border-ink/20 py-2 last:border-b-0">
	<span class="w-6 shrink-0 font-mono text-xs text-muted">{track.track_no ?? '·'}</span>
	<span class="min-w-0 flex-1 truncate" title={track.path}>{track.title}</span>
	<span class="font-mono text-xs text-muted">{formatDuration(track.duration)}</span>
	{#if confirming}
		<span class="text-sm">ลบไฟล์นี้จริงไหม?</span>
		<button class="btn btn-primary" onclick={confirmDelete} disabled={busy}>ลบเลย</button>
		<button class="btn" onclick={() => (confirming = false)} disabled={busy}>ไม่ลบ</button>
	{:else}
		<button class="btn" aria-label={`ลบ ${track.title}`} onclick={() => (confirming = true)}>ลบ</button>
	{/if}
	{#if error}
		<p role="alert" class="w-full text-sm text-orange">{error}</p>
	{/if}
</li>
