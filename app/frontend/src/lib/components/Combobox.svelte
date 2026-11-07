<script lang="ts">
	import type { ComboOption } from '$lib/types';

	type Props = {
		value: string;
		options: ComboOption[];
		label: string;
		/** Show the label only to screen readers. */
		hideLabel?: boolean;
		placeholder?: string;
		maxlength?: number;
		/** When set, new text gets a last row "+ <createLabel> "<text>"". */
		createLabel?: string | null;
		onpick?: (value: string) => void;
	};
	let {
		value = $bindable(),
		options,
		label,
		hideLabel = false,
		placeholder,
		maxlength,
		createLabel = null,
		onpick
	}: Props = $props();

	const uid = $props.id();
	let open = $state(false);
	let active = $state(-1);

	const fold = (s: string) => s.trim().toLowerCase();
	const rows = $derived.by(() => {
		const typed = value.trim();
		const isNew = createLabel && typed && !options.some((o) => fold(o.value) === fold(typed));
		return isNew ? [...options, { value: typed, label: `+ ${createLabel} "${typed}"` }] : options;
	});
	const showList = $derived(open && rows.length > 0);

	function pick(next: string) {
		value = next;
		open = false;
		active = -1;
		onpick?.(next);
	}

	function onkeydown(event: KeyboardEvent) {
		if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
			event.preventDefault();
			if (!rows.length) return;
			open = true;
			const step = event.key === 'ArrowDown' ? 1 : -1;
			active = active < 0 && step < 0 ? rows.length - 1 : (active + step + rows.length) % rows.length;
		} else if (event.key === 'Enter' && showList && active >= 0) {
			event.preventDefault();
			pick(rows[active].value);
		} else if (event.key === 'Escape' && showList) {
			event.preventDefault();
			open = false;
			active = -1;
		}
	}
</script>

<div class="relative space-y-1">
	<label for={uid} class={hideLabel ? 'sr-only' : 'label block'}>{label}</label>
	<input
		id={uid}
		class="input"
		role="combobox"
		autocomplete="off"
		aria-autocomplete="list"
		aria-expanded={showList}
		aria-controls={`${uid}-list`}
		aria-activedescendant={showList && active >= 0 ? `${uid}-opt-${active}` : undefined}
		bind:value
		{placeholder}
		{maxlength}
		onfocus={() => (open = true)}
		onblur={() => {
			open = false;
			active = -1;
		}}
		oninput={() => {
			open = true;
			active = -1;
		}}
		{onkeydown}
	/>
	{#if showList}
		<ul id={`${uid}-list`} role="listbox" aria-label={label} class="card absolute inset-x-0 z-20 mt-1 max-h-64 overflow-auto p-1">
			{#each rows as row, i}
				<!-- Keys go through the input (aria-activedescendant), so the row needs no key handler.
				     preventDefault on mousedown keeps focus in the input. -->
				<!-- svelte-ignore a11y_click_events_have_key_events -->
				<li
					id={`${uid}-opt-${i}`}
					role="option"
					tabindex="-1"
					aria-selected={i === active}
					class={['flex cursor-pointer items-center justify-between gap-2 rounded px-2 py-1.5', i === active && 'bg-yellow']}
					onmousedown={(e) => e.preventDefault()}
					onclick={() => pick(row.value)}
				>
					<span class="truncate">{row.label}</span>
					{#if row.hint}<span class="shrink-0 font-mono text-xs text-muted">{row.hint}</span>{/if}
				</li>
			{/each}
		</ul>
	{/if}
</div>
