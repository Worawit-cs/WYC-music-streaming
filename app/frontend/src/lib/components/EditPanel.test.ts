import { fireEvent, render, screen } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
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
});
