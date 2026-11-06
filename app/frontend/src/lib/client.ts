import { goto } from '$app/navigation';
import { createApi } from './api';
import { session } from './session.svelte';

/** The app-wide API client. Any 403 sends the user to /denied. */
export const api = createApi(undefined, ({ login }) => {
	session.deniedLogin = login;
	if (location.pathname !== '/denied') void goto('/denied');
});
