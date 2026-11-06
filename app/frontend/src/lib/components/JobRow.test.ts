import { fireEvent, render, screen } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import { makeJob } from '$lib/testData';
import JobRow from './JobRow.svelte';

describe('JobRow', () => {
	it('shows the error and retries a failed job', async () => {
		const onretry = vi.fn();
		render(JobRow, { job: makeJob({ id: 5, status: 'failed', error: 'HTTP Error 403' }), onretry, oncancel: vi.fn() });
		expect(screen.getByText('HTTP Error 403')).toBeInTheDocument();
		expect(screen.queryByRole('button', { name: 'ยกเลิก' })).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: 'ลองใหม่' }));
		expect(onretry).toHaveBeenCalledWith(5);
	});

	it('cancels a queued job', async () => {
		const oncancel = vi.fn();
		render(JobRow, { job: makeJob({ id: 6, status: 'queued' }), onretry: vi.fn(), oncancel });
		await fireEvent.click(screen.getByRole('button', { name: 'ยกเลิก' }));
		expect(oncancel).toHaveBeenCalledWith(6);
	});

	it('shows progress while downloading', () => {
		render(JobRow, { job: makeJob({ status: 'downloading', progress: 0.42 }), onretry: vi.fn(), oncancel: vi.fn() });
		expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '42');
		expect(screen.queryByRole('button')).toBeNull();
	});

	it('shows the file path when done', () => {
		render(JobRow, { job: makeJob({ status: 'done', final_path: 'Linkin_Park/Singles/Numb.m4a' }), onretry: vi.fn(), oncancel: vi.fn() });
		expect(screen.getByText('Linkin_Park/Singles/Numb.m4a')).toBeInTheDocument();
		expect(screen.getByText('เสร็จแล้ว')).toBeInTheDocument();
	});
});
