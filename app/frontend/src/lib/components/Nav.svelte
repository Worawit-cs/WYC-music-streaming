<script lang="ts">
	import { page } from '$app/state';

	let { activeCount = 0 }: { activeCount?: number } = $props();

	const links = [
		{ href: '/', label: 'ค้นหา' },
		{ href: '/library', label: 'คลังเพลง' },
		{ href: '/queue', label: 'คิว' }
	];
</script>

<nav class="flex gap-2 overflow-x-auto" aria-label="เมนูหลัก">
	{#each links as link (link.href)}
		{@const current = page.url.pathname === link.href}
		<a href={link.href} class={['btn', current && 'btn-teal']} aria-current={current ? 'page' : undefined}>
			{link.label}
			{#if link.href === '/queue' && activeCount > 0}
				<span class="rounded border-2 border-ink bg-yellow px-1 font-mono text-xs text-ink">{activeCount}</span>
			{/if}
		</a>
	{/each}
</nav>
