<script lang="ts">
	import { pageNumbers } from '$lib/searchPages';

	type Props = { page: number; last: number; busy?: boolean; ongo: (page: number) => void };
	let { page, last, busy = false, ongo }: Props = $props();
</script>

<nav aria-label="หน้าผลค้นหา" class="flex flex-wrap items-center justify-center gap-2">
	<button class="btn" disabled={busy || page <= 1} onclick={() => ongo(page - 1)}>« ก่อน</button>
	{#each pageNumbers(last) as n (n)}
		<button
			class={['btn font-mono', n === page && 'btn-teal']}
			aria-current={n === page ? 'page' : undefined}
			disabled={busy}
			onclick={() => n !== page && ongo(n)}
		>
			{n}
		</button>
	{/each}
	<button class="btn" disabled={busy || page >= last} onclick={() => ongo(page + 1)}>ถัดไป »</button>
</nav>
