import { render, screen } from '@testing-library/svelte';
import { describe, expect, it } from 'vitest';
import { makeJob } from '../testData';
import CassetteDeck from './CassetteDeck.svelte';

function bar() {
	return screen.getByRole('progressbar');
}

describe('CassetteDeck', () => {
	it('is idle without a job', () => {
		render(CassetteDeck, { job: null });
		expect(screen.getByText('เครื่องว่าง เลือกเพลงเพื่อเริ่มอัด')).toBeInTheDocument();
		expect(screen.queryByRole('progressbar')).toBeNull();
	});

	it('shows a moving bar without a number while it looks for the file', () => {
		render(CassetteDeck, { job: makeJob({ status: 'downloading', stage: 'finding' }) });
		expect(screen.getByText('กำลังหาไฟล์…')).toBeInTheDocument();
		expect(bar()).not.toHaveAttribute('aria-valuenow');
		expect(bar().firstElementChild).toHaveClass('bar-stripes');
	});

	it('shows the percent while it downloads', () => {
		render(CassetteDeck, { job: makeJob({ status: 'downloading', stage: 'downloading', progress: 0.42 }) });
		expect(screen.getByText('กำลังโหลด 42%')).toBeInTheDocument();
		expect(bar()).toHaveAttribute('aria-valuenow', '42');
		expect(bar().firstElementChild).toHaveStyle({ width: '42%' });
		expect(bar().firstElementChild).not.toHaveClass('bar-stripes');
	});

	it('shows a full striped bar while it processes the file', () => {
		render(CassetteDeck, { job: makeJob({ status: 'downloading', stage: 'processing', progress: 1 }) });
		expect(screen.getByText('กำลังแปลงไฟล์…')).toBeInTheDocument();
		expect(bar().firstElementChild).toHaveClass('bar-stripes');
		expect(bar().firstElementChild).toHaveStyle({ width: '100%' });
	});
});
