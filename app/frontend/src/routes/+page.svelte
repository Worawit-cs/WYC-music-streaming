<script lang="ts">
	import { SvelteMap } from 'svelte/reactivity';
	import { api } from '$lib/client';
	import CassetteDeck from '$lib/components/CassetteDeck.svelte';
	import Combobox from '$lib/components/Combobox.svelte';
	import EditPanel from '$lib/components/EditPanel.svelte';
	import Pager from '$lib/components/Pager.svelte';
	import ResultCard from '$lib/components/ResultCard.svelte';
	import { errorText } from '$lib/format';
	import { jobs } from '$lib/jobs.svelte';
	import { library } from '$lib/library.svelte';
	import { libraryMatches } from '$lib/libraryOptions';
	import { knownLastPage } from '$lib/searchPages';
	import {
		cardState,
		defaultSelection,
		draftFrom,
		summarizeCreate,
		toJobItem,
		type Draft
	} from '$lib/selection';
	import type { ComboOption, JobItem, SearchResponse } from '$lib/types';

	type Tab = 'song' | 'link';
	const TABS: { id: Tab; label: string; placeholder: string }[] = [
		{ id: 'song', label: 'เพลง', placeholder: 'ชื่อเพลง หรือ ศิลปิน' },
		{ id: 'link', label: 'ลิงก์', placeholder: 'วางลิงก์ YouTube (เพลง หรือ playlist)' }
	];

	let tab = $state<Tab>('song');
	let q = $state('');
	let searching = $state(false);
	let searchError = $state<string | null>(null);
	let response = $state<SearchResponse | null>(null);
	let editing = $state<Draft | null>(null);
	let sending = $state(false);
	let sendError = $state<string | null>(null);
	let notice = $state<string | null>(null);
	let picked = $state<string[]>([]);
	let batchAlbum = $state('');

	// Text search pages: one query at a time, fetched pages kept until the next query.
	let query = $state('');
	let page = $state(1);
	let paging = $state(false);
	const pages = new SvelteMap<number, SearchResponse>();
	const lastPage = $derived(knownLastPage(pages.values()));

	// Suggestions while typing (song tab only).
	let suggestions = $state<string[]>([]);
	let suggestCtrl: AbortController | null = null;

	let editorBox = $state<HTMLElement | null>(null);
	let resultsTop = $state<HTMLElement | null>(null);

	const placeholder = $derived(TABS.find((t) => t.id === tab)!.placeholder);
	const artistNames = $derived(library.artists.map((a) => a.artist));
	// The YouTube guess, only when the editor was prefilled with a different library name.
	const youtubeArtist = $derived.by(() => {
		if (!editing) return undefined;
		const guess = response?.results.find((r) => r.video_id === editing!.video_id)?.suggested.artist;
		return guess && guess !== editing.artist ? guess : undefined;
	});
	const isPlaylist = $derived(response?.kind === 'playlist');

	// The editor sits above the results: bring it into view when a card far down opens it.
	$effect(() => {
		if (!editing || !editorBox) return;
		const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
		editorBox.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' });
	});

	$effect(() => {
		const text = q.trim();
		suggestCtrl?.abort();
		if (tab !== 'song' || text.length < 2 || text === query) {
			suggestions = [];
			return;
		}
		const timer = setTimeout(async () => {
			const ctrl = new AbortController();
			suggestCtrl = ctrl;
			try {
				const res = await api.suggest(text, ctrl.signal);
				if (suggestCtrl === ctrl) suggestions = res.suggestions;
			} catch {
				// Suggestions are optional: ignore aborts and errors.
			}
		}, 250);
		return () => clearTimeout(timer);
	});

	const fold = (s: string) => s.trim().toLowerCase();
	const suggestRows = $derived.by((): ComboOption[] => {
		if (tab !== 'song' || q.trim() === query) return [];
		const fromYoutube = suggestions.map((s) => ({ value: s, label: s }));
		const owned = libraryMatches(library.artists, q)
			.filter((m) => !suggestions.some((s) => fold(s) === fold(m)))
			.map((m) => ({ value: m, label: m, hint: 'มีแล้ว' }));
		return [...fromYoutube, ...owned];
	});

	function stateOf(videoId: string) {
		return cardState(videoId, library.videoIds, jobs.list);
	}

	function switchTab(next: Tab) {
		tab = next;
		searchError = null;
	}

	function runSearch(event: SubmitEvent) {
		event.preventDefault();
		void startSearch(q);
	}

	async function startSearch(text: string) {
		const wanted = text.trim();
		if (!wanted || searching) return;
		if (tab === 'link' && !/^https?:\/\//i.test(wanted)) {
			searchError = 'วางลิงก์ที่ขึ้นต้นด้วย https://';
			return;
		}
		q = wanted;
		query = wanted;
		page = 1;
		pages.clear();
		searching = true;
		searchError = null;
		notice = null;
		sendError = null;
		editing = null;
		response = null;
		try {
			const res = await api.search(wanted);
			pages.set(1, res);
			response = res;
			if (res.kind === 'playlist') {
				picked = defaultSelection(res.results, library.videoIds);
				batchAlbum = res.playlist_title ?? '';
			} else if (res.kind === 'url' && res.results.length === 1 && stateOf(res.results[0].video_id) === 'new') {
				editing = draftFrom(res.results[0], artistNames);
			}
		} catch (e) {
			searchError = errorText(e);
		} finally {
			searching = false;
		}
	}

	async function goPage(n: number) {
		if (paging || n === page || n < 1 || n > lastPage) return;
		searchError = null;
		const cached = pages.get(n);
		if (cached) {
			showPage(n, cached);
			return;
		}
		paging = true;
		try {
			const res = await api.search(query, n);
			pages.set(n, res);
			showPage(n, res);
		} catch (e) {
			searchError = errorText(e);
		} finally {
			paging = false;
		}
	}

	function showPage(n: number, res: SearchResponse) {
		page = n;
		response = res;
		const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
		resultsTop?.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' });
	}

	async function send(items: JobItem[]) {
		sending = true;
		sendError = null;
		try {
			const res = await api.createJobs(items);
			for (const job of res.created) jobs.apply(job);
			notice = summarizeCreate(res);
			editing = null;
		} catch (e) {
			sendError = errorText(e);
		} finally {
			sending = false;
		}
	}

	function togglePick(videoId: string) {
		picked = picked.includes(videoId) ? picked.filter((id) => id !== videoId) : [...picked, videoId];
	}

	function sendPlaylist() {
		if (!response) return;
		const items = response.results
			.filter((r) => picked.includes(r.video_id))
			.map((r) => toJobItem(draftFrom(r, artistNames), batchAlbum));
		if (items.length) void send(items);
	}
</script>

<div class="grid gap-6 lg:grid-cols-[1fr_320px]">
	<section class="min-w-0 space-y-4">
		<div class="flex gap-2" role="tablist" aria-label="ประเภทการค้นหา">
			{#each TABS as t (t.id)}
				<button
					role="tab"
					aria-selected={tab === t.id}
					class={['btn', tab === t.id && 'btn-teal']}
					onclick={() => switchTab(t.id)}
				>
					{t.label}
				</button>
			{/each}
		</div>

		<form class="flex items-start gap-2" onsubmit={runSearch}>
			<div class="min-w-0 flex-1">
				{#if tab === 'song'}
					<Combobox
						bind:value={q}
						options={suggestRows}
						label={placeholder}
						hideLabel
						{placeholder}
						maxlength={500}
						onpick={(text) => void startSearch(text)}
					/>
				{:else}
					<input class="input" bind:value={q} {placeholder} aria-label={placeholder} maxlength="500" />
				{/if}
			</div>
			<button class="btn btn-primary shrink-0" type="submit" disabled={searching || !q.trim()}>
				{searching ? 'กำลังหา…' : 'ค้นหา'}
			</button>
		</form>

		{#if searchError}
			<p role="alert" class="card p-3 text-orange">{searchError}</p>
		{/if}
		{#if notice}
			<p role="status" class="card bg-yellow p-3">{notice}</p>
		{/if}

		{#if editing}
			<div bind:this={editorBox} class="scroll-mt-4">
				<EditPanel
					draft={editing}
					artists={library.artists}
					{youtubeArtist}
					busy={sending}
					error={sendError}
					onsubmit={(d) => void send([toJobItem(d)])}
					oncancel={() => (editing = null)}
				/>
			</div>
		{/if}

		{#if response && isPlaylist}
			<div class="card space-y-3 p-4">
				<p class="font-bold">Playlist: {response.playlist_title}</p>
				<label class="block space-y-1">
					<span class="label">อัลบั้ม (ใช้กับทุกเพลงที่เลือก)</span>
					<input class="input" bind:value={batchAlbum} maxlength="300" />
				</label>
				{#if sendError}
					<p role="alert" class="text-sm text-orange">{sendError}</p>
				{/if}
				<button
					class="btn btn-primary"
					onclick={sendPlaylist}
					disabled={sending || picked.length === 0 || !batchAlbum.trim()}
				>
					{sending ? 'กำลังส่ง…' : `โหลด ${picked.length} เพลง`}
				</button>
			</div>
		{/if}

		<div bind:this={resultsTop} class="scroll-mt-4"></div>
		{#if response}
			{#if response.results.length === 0}
				<p class="text-muted">ไม่พบเพลง</p>
			{:else}
				<ul class="space-y-3">
					{#each response.results as result (result.video_id)}
						<ResultCard
							{result}
							state={stateOf(result.video_id)}
							mode={isPlaylist ? 'pick' : 'single'}
							selected={picked.includes(result.video_id)}
							ontoggle={() => togglePick(result.video_id)}
							ondownload={() => {
								notice = null;
								sendError = null;
								editing = draftFrom(result, artistNames);
							}}
						/>
					{/each}
				</ul>
			{/if}
			{#if response.kind === 'search' && lastPage > 1}
				<Pager {page} last={lastPage} busy={paging} ongo={(n) => void goPage(n)} />
			{/if}
		{/if}
	</section>

	<aside class="space-y-4">
		<CassetteDeck job={jobs.current} />
		<section class="card space-y-2 p-4">
			<p class="label">คิวถัดไป</p>
			{#if jobs.queued.length === 0}
				<p class="text-sm text-muted">ไม่มีเพลงรอคิว</p>
			{:else}
				<ol class="space-y-1 text-sm">
					{#each jobs.queued.slice(0, 3) as job (job.id)}
						<li class="truncate">{job.title} <span class="text-muted">· {job.artist}</span></li>
					{/each}
				</ol>
				{#if jobs.queued.length > 3}
					<p class="text-xs text-muted">และอีก {jobs.queued.length - 3} เพลง</p>
				{/if}
			{/if}
			<a href="/queue" class="text-sm text-teal underline">ดูคิวทั้งหมด</a>
		</section>
		<section class="card space-y-1 p-4">
			<p class="label">ชั้นเทป</p>
			<p><span class="font-mono text-2xl">{library.trackCount}</span> เพลง จาก {library.artists.length} ศิลปิน</p>
			<a href="/library" class="text-sm text-teal underline">เปิดคลังเพลง</a>
		</section>
	</aside>
</div>
