<script lang="ts">
	import { page } from '$app/state';
	import { albumList, type AlbumCard } from '$lib/albumList';
	import { api } from '$lib/client';
	import AlbumGrid from '$lib/components/AlbumGrid.svelte';
	import RenameForm from '$lib/components/RenameForm.svelte';
	import TrackRow from '$lib/components/TrackRow.svelte';
	import { errorText } from '$lib/format';
	import { library } from '$lib/library.svelte';
	import { filterLibrary } from '$lib/libraryFilter';
	import type { RenameBody } from '$lib/types';

	let filter = $state('');
	let busy = $state<'rescan' | 'jellyfin' | null>(null);
	let notice = $state<string | null>(null);
	let error = $state<string | null>(null);

	const VIEWS = [
		{ id: 'artists', label: 'ศิลปิน', href: '/library' },
		{ id: 'albums', label: 'อัลบั้ม', href: '/library?view=albums' }
	] as const;
	const view = $derived(page.url.searchParams.get('view') === 'albums' ? 'albums' : 'artists');

	const shown = $derived(filterLibrary(library.artists, filter));
	const cards = $derived(view === 'albums' ? albumList(shown) : []);
	const allCards = $derived(view === 'albums' ? albumList(library.artists) : []);

	let editingArtist = $state<string | null>(null);
	const artistCounts = $derived(
		library.artists.map((a) => ({ name: a.artist, tracks: a.albums.reduce((n, al) => n + al.tracks.length, 0) }))
	);

	/** Rename on the server, reload the library, and say what happened. Errors go back to the form. */
	async function rename(body: RenameBody) {
		const { moved, merged } = await api.rename(body);
		await library.load();
		error = null;
		notice = merged ? `รวมแล้ว ${moved} เพลง` : `เปลี่ยนชื่อแล้ว ${moved} เพลง`;
	}

	const renameAlbum = (card: AlbumCard, name: string) =>
		rename({ kind: 'album', artist: card.artist, album: card.album, new_name: name });

	async function remove(path: string) {
		await api.deleteTrack(path);
		await library.load();
	}

	async function run(kind: 'rescan' | 'jellyfin') {
		busy = kind;
		notice = null;
		error = null;
		try {
			if (kind === 'rescan') {
				const { tracks } = await api.rescanLibrary();
				await library.load();
				notice = `สแกนโฟลเดอร์แล้ว พบ ${tracks} เพลง`;
			} else {
				const { ok } = await api.refreshJellyfin();
				notice = ok ? 'สั่ง Jellyfin สแกนแล้ว' : 'ติดต่อ Jellyfin ไม่ได้';
			}
		} catch (e) {
			error = errorText(e);
		} finally {
			busy = null;
		}
	}
</script>

<div class="space-y-6">
	<div class="flex flex-wrap items-center gap-2">
		<h1 class="mr-auto text-2xl font-bold">คลังเพลง</h1>
		<button class="btn" onclick={() => run('rescan')} disabled={busy !== null}>
			{busy === 'rescan' ? 'กำลังสแกน…' : 'สแกนโฟลเดอร์'}
		</button>
		<button class="btn btn-teal" onclick={() => run('jellyfin')} disabled={busy !== null}>
			{busy === 'jellyfin' ? 'กำลังสั่ง…' : 'ให้ Jellyfin สแกน'}
		</button>
	</div>

	<nav class="flex gap-2" aria-label="มุมมองคลังเพลง">
		{#each VIEWS as v (v.id)}
			<a href={v.href} class={['btn', view === v.id && 'btn-teal']} aria-current={view === v.id ? 'page' : undefined}>
				{v.label}
			</a>
		{/each}
	</nav>

	<input class="input" bind:value={filter} placeholder="กรองตามศิลปิน อัลบั้ม หรือชื่อเพลง" aria-label="กรองคลังเพลง" />

	{#if notice}
		<p role="status" class="card bg-yellow p-3">{notice}</p>
	{/if}
	{#if error}
		<p role="alert" class="card p-3 text-orange">{error}</p>
	{/if}

	{#if !library.loaded}
		<p class="text-muted">กำลังโหลด…</p>
	{:else if shown.length === 0}
		<p class="text-muted">{filter.trim() ? 'ไม่พบเพลงที่ตรงกับคำค้น' : 'คลังยังว่าง ลองโหลดเพลงจากหน้าค้นหา'}</p>
	{:else if view === 'albums'}
		<AlbumGrid {cards} {allCards} ondelete={remove} onrename={renameAlbum} />
	{:else}
		<div class="grid gap-6 md:grid-cols-[200px_1fr]">
			<nav class="hidden md:block" aria-label="ศิลปิน">
				<ul class="sticky top-4 space-y-1">
					{#each shown as artist, i (artist.artist)}
						<li><a class="block truncate py-1 text-sm hover:text-teal" href={`#artist-${i}`}>{artist.artist}</a></li>
					{/each}
				</ul>
			</nav>
			<div class="min-w-0 space-y-8">
				{#each shown as artist, i (artist.artist)}
					<section id={`artist-${i}`} class="space-y-3">
						<div class="flex flex-wrap items-center gap-2">
							<h2 class="min-w-0 text-xl font-bold break-words">{artist.artist}</h2>
							{#if editingArtist !== artist.artist}
								<button
									class="btn"
									aria-label={`แก้ชื่อศิลปิน ${artist.artist}`}
									onclick={() => (editingArtist = artist.artist)}
								>
									แก้ชื่อ
								</button>
							{/if}
						</div>
						{#if editingArtist === artist.artist}
							<div class="card p-4">
								<RenameForm
									kind="artist"
									oldName={artist.artist}
									existing={artistCounts.filter((a) => a.name !== artist.artist)}
									onsubmit={async (name) => {
										await rename({ kind: 'artist', artist: artist.artist, new_name: name });
										editingArtist = null;
									}}
									oncancel={() => (editingArtist = null)}
								/>
							</div>
						{/if}
						{#each artist.albums as album (album.album)}
							<article class="card p-4">
								<h3 class="font-semibold">
									{album.album}
									<span class="font-mono text-xs text-muted">· {album.tracks.length} เพลง</span>
								</h3>
								<ul>
									{#each album.tracks as track (track.path)}
										<TrackRow {track} ondelete={remove} />
									{/each}
								</ul>
							</article>
						{/each}
					</section>
				{/each}
			</div>
		</div>
	{/if}
</div>
