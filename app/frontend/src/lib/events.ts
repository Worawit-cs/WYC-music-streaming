import type { Job } from './types';

/** The part of EventSource we use, so tests can pass a fake. */
export interface EventSourceLike {
	addEventListener(type: string, listener: (event: MessageEvent) => void): void;
	close(): void;
}

export type EventHandlers = {
	job: (job: Job) => void;
	library: () => void;
	/** Called on every (re)connect. Reload state here: events sent while offline are lost. */
	open: () => void;
};

/** Listen to /api/events (SSE). EventSource reconnects by itself. Returns a close function. */
export function connectEvents(
	handlers: EventHandlers,
	makeSource: (url: string) => EventSourceLike = (url) => new EventSource(url)
): () => void {
	const source = makeSource('/api/events');
	source.addEventListener('open', () => handlers.open());
	source.addEventListener('job', (event) => {
		try {
			handlers.job(JSON.parse(event.data) as Job);
		} catch {
			// ignore a malformed event; the next reconnect reloads the jobs
		}
	});
	source.addEventListener('library', () => handlers.library());
	return () => source.close();
}
