import { fireEvent, render, screen } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import { makeJob } from '../testData';
import DoneDialog from './DoneDialog.svelte';

const done = [
	makeJob({ id: 1, status: 'done', title: 'Thriller', artist: 'MJ', album: 'Thriller' }),
	makeJob({ id: 2, status: 'done', title: 'Beat It', artist: 'MJ', album: 'Thriller' })
];
const failed = makeJob({ id: 3, status: 'failed', title: 'Bad', artist: 'MJ', album: 'Bad' });

describe('DoneDialog', () => {
	it('lists the finished tracks and focuses the close button', () => {
		render(DoneDialog, { finished: done, onclose: vi.fn() });
		const dialog = screen.getByRole('dialog', { name: 'อัดเทปเสร็จแล้ว 2 เพลง' });
		expect(dialog).toHaveAttribute('open');
		expect(screen.getByText('Thriller · MJ / Thriller')).toBeInTheDocument();
		expect(screen.getByText('Beat It · MJ / Thriller')).toBeInTheDocument();
		expect(screen.queryByText(/โหลดไม่ได้/)).toBeNull();
		expect(screen.getByRole('button', { name: 'ปิด' })).toHaveFocus();
	});

	it('lists failed tracks with a link to the queue', () => {
		render(DoneDialog, { finished: [...done, failed], onclose: vi.fn() });
		expect(screen.getByText('โหลดไม่ได้ 1 เพลง')).toBeInTheDocument();
		expect(screen.getByText('Bad · MJ / Bad')).toBeInTheDocument();
		expect(screen.getByRole('link', { name: 'ดูคิว' })).toHaveAttribute('href', '/queue');
	});

	it('names only failures when nothing finished well', () => {
		render(DoneDialog, { finished: [failed], onclose: vi.fn() });
		expect(screen.getByRole('dialog', { name: 'อัดเทปไม่สำเร็จ' })).toBeInTheDocument();
	});

	it('closes from the button, the library link and Escape', async () => {
		const onclose = vi.fn();
		render(DoneDialog, { finished: done, onclose });
		await fireEvent.click(screen.getByRole('button', { name: 'ปิด' }));
		await fireEvent.click(screen.getByRole('link', { name: 'เปิดคลังเพลง' }));
		await fireEvent(screen.getByRole('dialog'), new Event('cancel'));
		expect(onclose).toHaveBeenCalledTimes(3);
	});
});
