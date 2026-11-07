<script lang="ts">
	import type { AlbumCard } from '$lib/albumList';
	import TrackRow from './TrackRow.svelte';

	type Props = { cards: AlbumCard[]; ondelete: (path: string) => Promise<void> | void };
	let { cards, ondelete }: Props = $props();

	let open = $state<string | null>(null);
</script>

<ul class="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
	{#each cards as card, i (card.key)}
		{@const isOpen = open === card.key}
		<li class={['card', isOpen && 'sm:col-span-2 xl:col-span-3']}>
			<button
				class="flex w-full items-center gap-3 p-4 text-left"
				aria-expanded={isOpen}
				aria-controls={`album-${i}`}
				onclick={() => (open = isOpen ? null : card.key)}
			>
				<span
					aria-hidden="true"
					class="grid size-12 shrink-0 place-items-center rounded border-2 border-ink bg-yellow font-mono text-lg"
				>
					{card.album.slice(0, 1).toUpperCase()}
				</span>
				<span class="min-w-0">
					<span class="block truncate font-semibold">{card.album}</span>
					<span class="block truncate text-sm text-muted">{card.artist}</span>
					<span class="font-mono text-xs text-muted">{card.tracks.length} เพลง</span>
				</span>
			</button>
			{#if isOpen}
				<ul id={`album-${i}`} class="border-t-2 border-ink px-4 pb-2">
					{#each card.tracks as track (track.path)}
						<TrackRow {track} {ondelete} />
					{/each}
				</ul>
			{/if}
		</li>
	{/each}
</ul>
