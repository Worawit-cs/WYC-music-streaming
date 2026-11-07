<script lang="ts">
	import { errorText } from '$lib/format';
	import type { RenameTarget } from '$lib/types';
	import Combobox from './Combobox.svelte';

	type Props = {
		kind: 'album' | 'artist';
		oldName: string;
		/** Other artists (or other albums of the same artist) the new name may merge into. */
		existing: RenameTarget[];
		/** Resolves when the rename is done; a rejection shows its message. */
		onsubmit: (newName: string) => Promise<void>;
		oncancel: () => void;
	};
	let { kind, oldName, existing, onsubmit, oncancel }: Props = $props();

	// Writable derived: it resets when the parent passes another oldName.
	let name = $derived(oldName);
	let busy = $state(false);
	let error = $state<string | null>(null);

	const fold = (s: string) => s.trim().toLowerCase();
	const options = $derived(existing.map((e) => ({ value: e.name, label: e.name, hint: `${e.tracks} เพลง` })));
	const mergeInto = $derived(
		fold(name) === fold(oldName) ? undefined : existing.find((e) => fold(e.name) === fold(name))
	);
	const unchanged = $derived(!name.trim() || name.trim() === oldName);

	async function submit(event: SubmitEvent) {
		event.preventDefault();
		if (unchanged || busy) return;
		busy = true;
		error = null;
		try {
			await onsubmit(mergeInto ? mergeInto.name : name.trim());
		} catch (e) {
			error = errorText(e);
		} finally {
			busy = false;
		}
	}
</script>

<form class="space-y-2" onsubmit={submit}>
	<Combobox
		bind:value={name}
		{options}
		label={kind === 'album' ? 'ชื่ออัลบั้มใหม่' : 'ชื่อศิลปินใหม่'}
		maxlength={300}
		filter
	/>
	{#if mergeInto}
		<p class="text-sm">จะรวมกับ {mergeInto.name} ที่มีอยู่แล้ว ({mergeInto.tracks} เพลง)</p>
	{/if}
	{#if error}
		<p role="alert" class="text-sm text-orange">{error}</p>
	{/if}
	<div class="flex flex-wrap gap-2">
		<button class="btn btn-primary" type="submit" disabled={unchanged || busy}>
			{busy ? 'กำลังย้าย…' : mergeInto ? 'รวม' : 'บันทึก'}
		</button>
		<button class="btn" type="button" onclick={oncancel} disabled={busy}>ยกเลิก</button>
	</div>
</form>
