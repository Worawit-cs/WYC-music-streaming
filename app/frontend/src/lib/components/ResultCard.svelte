<script lang="ts">
	import { formatDuration } from '$lib/format';
	import type { CardState } from '$lib/selection';
	import type { SearchResult } from '$lib/types';

	type Props = {
		result: SearchResult;
		state: CardState;
		/** "pick" shows a checkbox (playlist mode); "single" shows a download button. */
		mode: 'single' | 'pick';
		selected?: boolean;
		ontoggle?: () => void;
		ondownload?: () => void;
	};
	let { result, state, mode, selected = false, ontoggle, ondownload }: Props = $props();

	const badge = $derived(
		state === 'in_library' ? 'มีในคลังแล้ว' : state === 'active' ? 'อยู่ในคิว' : null
	);
</script>

<li class="card flex items-center gap-3 p-3">
	{#if mode === 'pick'}
		<input
			type="checkbox"
			class="h-6 w-6 shrink-0 accent-teal"
			checked={selected}
			disabled={state !== 'new'}
			onchange={() => ontoggle?.()}
			aria-label={`เลือก ${result.title}`}
		/>
	{/if}
	<img
		src={result.thumbnail_url}
		alt=""
		loading="lazy"
		referrerpolicy="no-referrer"
		class="h-14 w-24 shrink-0 rounded border-2 border-ink object-cover"
	/>
	<div class="min-w-0 flex-1">
		<p class="truncate font-semibold" title={result.title}>{result.title}</p>
		<p class="truncate text-sm text-muted">
			{result.channel} · <span class="font-mono">{formatDuration(result.duration)}</span>
		</p>
		<p class="truncate text-xs text-teal">
			→ {result.suggested.artist} / {result.suggested.album} / {result.suggested.title}
		</p>
	</div>
	{#if mode === 'single'}
		{#if badge}
			<span class="label shrink-0">{badge}</span>
		{:else}
			<button class="btn btn-primary shrink-0" onclick={() => ondownload?.()}>โหลด</button>
		{/if}
	{:else if badge}
		<span class="label shrink-0">{badge}</span>
	{/if}
</li>
