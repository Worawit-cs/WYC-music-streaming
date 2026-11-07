import { fireEvent, render, screen } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import { ApiError } from '../api';
import RenameForm from './RenameForm.svelte';

const existing = [
	{ name: 'The Weeknd', tracks: 26 },
	{ name: 'MJ', tracks: 43 }
];

function setup(onsubmit = vi.fn().mockResolvedValue(undefined)) {
	const oncancel = vi.fn();
	render(RenameForm, { kind: 'artist', oldName: 'The Weeknd, JENNIE & Lily Rose Depp', existing, onsubmit, oncancel });
	return { onsubmit, oncancel, input: screen.getByLabelText('ชื่อศิลปินใหม่') as HTMLInputElement };
}

describe('RenameForm', () => {
	it('starts with the old name and blocks saving it unchanged', () => {
		const { input } = setup();
		expect(input.value).toBe('The Weeknd, JENNIE & Lily Rose Depp');
		expect(screen.getByRole('button', { name: 'บันทึก' })).toBeDisabled();
	});

	it('saves a new name', async () => {
		const { input, onsubmit } = setup();
		await fireEvent.input(input, { target: { value: '  The Weeknd & Friends ' } });
		await fireEvent.click(screen.getByRole('button', { name: 'บันทึก' }));
		expect(onsubmit).toHaveBeenCalledWith('The Weeknd & Friends');
	});

	it('warns before a merge and sends the existing spelling', async () => {
		const { input, onsubmit } = setup();
		await fireEvent.input(input, { target: { value: 'the weeknd' } });
		expect(screen.getByText('จะรวมกับ The Weeknd ที่มีอยู่แล้ว (26 เพลง)')).toBeInTheDocument();
		await fireEvent.click(screen.getByRole('button', { name: 'รวม' }));
		expect(onsubmit).toHaveBeenCalledWith('The Weeknd');
	});

	it('shows the server error and stays open', async () => {
		const onsubmit = vi.fn().mockRejectedValue(new ApiError(409, 'มีเพลงกำลังโหลดเข้าศิลปินนี้ รอคิวหมดก่อน'));
		const { input } = setup(onsubmit);
		await fireEvent.input(input, { target: { value: 'X' } });
		await fireEvent.click(screen.getByRole('button', { name: 'บันทึก' }));
		expect(await screen.findByRole('alert')).toHaveTextContent('มีเพลงกำลังโหลดเข้าศิลปินนี้ รอคิวหมดก่อน');
		expect(screen.getByRole('button', { name: 'บันทึก' })).toBeEnabled();
	});

	it('cancels', async () => {
		const { oncancel } = setup();
		await fireEvent.click(screen.getByRole('button', { name: 'ยกเลิก' }));
		expect(oncancel).toHaveBeenCalledOnce();
	});
});
