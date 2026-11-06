<script lang="ts">
	import { session } from '$lib/session.svelte';

	const login = $derived(session.deniedLogin);
	const snippet = $derived(
		[
			'[users.<name>]',
			`tailscale_login = "${login ?? '<tailscale login>'}"`,
			'music_dir = "/home/wick/share/<name>/music"',
			'jellyfin_user = "<name>"'
		].join('\n')
	);
</script>

<section class="card max-w-xl space-y-4 p-6">
	<h1 class="text-2xl font-bold">ไม่มีสิทธิ์เข้าใช้</h1>
	{#if login}
		<p>บัญชี Tailscale <span class="font-mono break-all">{login}</span> ยังไม่อยู่ในรายชื่อผู้ใช้</p>
	{:else}
		<p>ไม่พบตัวตนจาก Tailscale ต้องเปิดแอปผ่านลิงก์ <span class="font-mono">https://&lt;nas&gt;.ts.net</span> เท่านั้น</p>
	{/if}
	<p class="text-sm text-muted">
		ให้แอดมินเพิ่มส่วนนี้ใน <span class="font-mono">/etc/wyc-music-streaming/config.toml</span> แล้ว restart service
	</p>
	<pre class="overflow-x-auto rounded bg-ink p-3 font-mono text-xs text-card">{snippet}</pre>
</section>
