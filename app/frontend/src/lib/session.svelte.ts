import type { Me } from './types';

class Session {
	/** The current user, from GET /api/me. null until it loads or when access is denied. */
	me = $state<Me | null>(null);
	/** The Tailscale login from a 403, shown on /denied. */
	deniedLogin = $state<string | null>(null);
}

export const session = new Session();
