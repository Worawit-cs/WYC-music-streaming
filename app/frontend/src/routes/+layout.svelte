<script lang="ts">
	import '../app.css';
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { ApiError } from '$lib/api';
	import { api } from '$lib/client';
	import DoneDialog from '$lib/components/DoneDialog.svelte';
	import Nav from '$lib/components/Nav.svelte';
	import { connectEvents } from '$lib/events';
	import { errorText } from '$lib/format';
	import { jobs } from '$lib/jobs.svelte';
	import { library } from '$lib/library.svelte';
	import { session } from '$lib/session.svelte';

	let { children } = $props();
	let bootError = $state<string | null>(null);
	const denied = $derived(page.url.pathname === '/denied');

	onMount(() => {
		let close: (() => void) | undefined;
		let stopped = false;
		(async () => {
			try {
				session.me = await api.me();
			} catch (e) {
				// 403 is handled by the client (redirect to /denied).
				if (!(e instanceof ApiError && e.status === 403)) bootError = errorText(e);
				return;
			}
			try {
				await Promise.all([jobs.load(), library.load()]);
			} catch (e) {
				bootError = errorText(e);
			}
			if (stopped) return;
			close = connectEvents({
				job: (job) => jobs.apply(job),
				library: () => void library.load().catch(() => {}),
				open: () => void jobs.load().catch(() => {})
			});
		})();
		return () => {
			stopped = true;
			close?.();
		};
	});
</script>

<svelte:head>
	<title>WYC-music-streaming</title>
</svelte:head>

<div class="min-h-dvh">
	<header class="border-b-2 border-ink bg-card">
		<div class="mx-auto flex max-w-6xl flex-wrap items-center gap-3 px-4 py-3">
			<a href="/" class="flex min-h-11 items-center gap-2 text-lg font-bold">
				<span aria-hidden="true" class="flex h-7 w-11 items-center justify-around rounded border-2 border-ink bg-yellow">
					<span class="h-3 w-3 rounded-full border-2 border-ink bg-card"></span>
					<span class="h-3 w-3 rounded-full border-2 border-ink bg-card"></span>
				</span>
				WYC
			</a>
			{#if session.me && !denied}
				<Nav activeCount={jobs.active.length} />
				<span class="ml-auto font-mono text-xs text-muted">{session.me.name}</span>
			{/if}
		</div>
	</header>
	<main class="mx-auto max-w-6xl px-4 py-6">
		{#if bootError}
			<p role="alert" class="card mb-4 p-4 text-orange">{bootError}</p>
		{/if}
		{#if session.me || denied}
			{@render children()}
		{:else if !bootError}
			<p class="text-muted">กำลังโหลด…</p>
		{/if}
	</main>
	{#if jobs.showDone && !denied}
		<DoneDialog finished={jobs.finished} onclose={() => jobs.dismissDone()} />
	{/if}
</div>
