/** After a library name, the rest of a YouTube artist guess must start with one of these. */
const SEPARATOR = /^(\s*[,&/]|\s+(x|feat\.?|ft\.?|with|and)\s)/i;

/**
 * Prefill the artist with a name already in the library when the YouTube guess is that
 * artist plus guests ("The Weeknd, JENNIE & Lily Rose Depp" -> "The Weeknd").
 * Exact match first (case-insensitive), then the longest library name followed by a separator.
 */
export function matchArtist(suggested: string, names: string[]): string {
	const guess = suggested.trim();
	const lower = guess.toLowerCase();
	const exact = names.find((n) => n.trim() && n.trim().toLowerCase() === lower);
	if (exact) return exact;
	let best = '';
	for (const name of names) {
		const n = name.trim().toLowerCase();
		if (!n || n.length <= best.trim().length) continue;
		if (lower.startsWith(n) && SEPARATOR.test(guess.slice(n.length))) best = name;
	}
	return best || suggested;
}
