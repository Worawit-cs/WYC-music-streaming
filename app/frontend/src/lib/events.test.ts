import { describe, expect, it, vi } from 'vitest';
import { connectEvents, type EventSourceLike } from './events';
import { makeJob } from './testData';

class FakeSource implements EventSourceLike {
	url = '';
	closed = false;
	listeners = new Map<string, (event: MessageEvent) => void>();
	addEventListener(type: string, listener: (event: MessageEvent) => void) {
		this.listeners.set(type, listener);
	}
	emit(type: string, data = '') {
		this.listeners.get(type)?.(new MessageEvent(type, { data }));
	}
	close() {
		this.closed = true;
	}
}

function setup() {
	const source = new FakeSource();
	const handlers = { job: vi.fn(), library: vi.fn(), open: vi.fn() };
	const close = connectEvents(handlers, (url) => {
		source.url = url;
		return source;
	});
	return { source, handlers, close };
}

describe('connectEvents', () => {
	it('subscribes to /api/events and dispatches events', () => {
		const { source, handlers } = setup();
		expect(source.url).toBe('/api/events');
		const job = makeJob({ status: 'downloading', progress: 0.5 });
		source.emit('job', JSON.stringify(job));
		source.emit('library', '{"added":["a.m4a"]}');
		source.emit('open');
		expect(handlers.job).toHaveBeenCalledWith(job);
		expect(handlers.library).toHaveBeenCalledOnce();
		expect(handlers.open).toHaveBeenCalledOnce();
	});

	it('ignores a malformed job event', () => {
		const { source, handlers } = setup();
		source.emit('job', 'not json');
		expect(handlers.job).not.toHaveBeenCalled();
	});

	it('closes the source', () => {
		const { source, close } = setup();
		close();
		expect(source.closed).toBe(true);
	});
});
