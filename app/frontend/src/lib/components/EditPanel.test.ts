import { fireEvent, render, screen } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import { LIBRARY } from '../testData';
import EditPanel from './EditPanel.svelte';

const draft = { video_id: 'kXYiU_JCYtU', title: 'Numb', artist: 'Linkin Park', album: 'Singles' };

describe('EditPanel', () => {
	it('prefills the label and submits the edited values', async () => {
		const onsubmit = vi.fn();
		render(EditPanel, { draft, onsubmit, oncancel: vi.fn() });
		const title = screen.getByLabelText('ชื่อเพลง') as HTMLInputElement;
		expect(title.value).toBe('Numb');
		await fireEvent.input(title, { target: { value: 'Numb (Live)' } });
		await fireEvent.click(screen.getByRole('button', { name: 'โหลดลงเทป' }));
		expect(onsubmit).toHaveBeenCalledWith({ ...draft, title: 'Numb (Live)' });
	});

	it('blocks submit while a field is blank', async () => {
		const onsubmit = vi.fn();
		render(EditPanel, { draft, onsubmit, oncancel: vi.fn() });
		await fireEvent.input(screen.getByLabelText('ศิลปิน'), { target: { value: '   ' } });
		expect(screen.getByRole('button', { name: 'โหลดลงเทป' })).toBeDisabled();
		expect(screen.getByRole('alert')).toHaveTextContent('กรอกศิลปินก่อน');
	});

	it('calls oncancel', async () => {
		const oncancel = vi.fn();
		render(EditPanel, { draft, onsubmit: vi.fn(), oncancel });
		await fireEvent.click(screen.getByRole('button', { name: 'ยกเลิก' }));
		expect(oncancel).toHaveBeenCalledOnce();
	});

	it('offers library artists and the albums of the chosen artist', async () => {
		render(EditPanel, { draft, artists: LIBRARY, onsubmit: vi.fn(), oncancel: vi.fn() });
		await fireEvent.focus(screen.getByLabelText('ศิลปิน'));
		expect(screen.getAllByRole('option').map((o) => o.textContent?.replace(/\s+/g, ' ').trim())).toEqual([
			'Linkin Park 3 เพลง',
			'Sade 1 เพลง'
		]);
		await fireEvent.click(screen.getByRole('option', { name: /Sade/ }));
		await fireEvent.focus(screen.getByLabelText('อัลบั้ม'));
		expect(screen.getAllByRole('option').map((o) => o.textContent?.replace(/\s+/g, ' ').trim())).toEqual([
			'Diamond Life 1 เพลง',
			'+ สร้างใหม่ "Singles"'
		]);
	});

	it('shows the YouTube guess when the prefill came from the library', async () => {
		render(EditPanel, {
			draft,
			artists: LIBRARY,
			youtubeArtist: 'Linkin Park, Jay-Z',
			onsubmit: vi.fn(),
			oncancel: vi.fn()
		});
		await fireEvent.focus(screen.getByLabelText('ศิลปิน'));
		expect(screen.getAllByRole('option')[0]).toHaveTextContent('Linkin Park, Jay-Z');
		expect(screen.getAllByRole('option')[0]).toHaveTextContent('ชื่อจาก YouTube');
	});
});
