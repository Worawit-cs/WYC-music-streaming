<script lang="ts">
	import type { AlbumCard } from '$lib/albumList';
	import RenameForm from './RenameForm.svelte';
	import TrackRow from './TrackRow.svelte';

	type Props = {
		cards: AlbumCard[];
		ondelete: (path: string) => Promise<void> | void;
		/** When set, each card gets a rename button. */
		onrename?: (card: AlbumCard, newName: string) => Promise<void>;
		/** Every album card (unfiltered), for the merge list. Defaults to cards. */
		allCards?: AlbumCard[];
	};
	let { cards, ondelete, onrename, allCards }: Props = $props();

	let open = $state<string | null>(null);
	let editing = $state<string | null>(null);

	function otherAlbums(card: AlbumCard) {
		return (allCards ?? cards)
			.filter((c) => c.artist === card.artist && c.key !== card.key)
			.map((c) => ({ name: c.album, tracks: c.tracks.length }));
	}
</script>

<ul class="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
	{#each cards as card, i (card.key)}
		{@const isOpen = open === card.key}
		{@const isEditing = editing === card.key}
		<li class={['card min-w-0', (isOpen || isEditing) && 'sm:col-span-2 xl:col-span-3']}>
			<div class="flex items-center gap-2 pr-3">
				<button
					class="flex min-w-0 flex-1 items-center gap-3 p-4 text-left"
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
				{#if onrename && !isEditing}
					<button class="btn shrink-0" aria-label={`แก้ชื่ออัลบั้ม ${card.album}`} onclick={() => (editing = card.key)}>
						แก้ชื่อ
					</button>
				{/if}
			</div>
			{#if onrename && isEditing}
				<div class="border-t-2 border-ink p-4">
					<RenameForm
						kind="album"
						oldName={card.album}
						existing={otherAlbums(card)}
						onsubmit={async (name) => {
							await onrename(card, name);
							editing = null;
						}}
						oncancel={() => (editing = null)}
					/>
				</div>
			{/if}
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
