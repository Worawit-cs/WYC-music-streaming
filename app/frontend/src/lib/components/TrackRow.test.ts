import { fireEvent, render, screen } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import { ApiError } from '$lib/api';
import { makeTrack } from '$lib/testData';
import TrackRow from './TrackRow.svelte';

describe('TrackRow', () => {
	it('asks before deleting', async () => {
		const ondelete = vi.fn().mockResolvedValue(undefined);
		render(TrackRow, { track: makeTrack(), ondelete });
		await fireEvent.click(screen.getByRole('button', { name: 'ลบ Numb' }));
		expect(ondelete).not.toHaveBeenCalled();
		await fireEvent.click(screen.getByRole('button', { name: 'ไม่ลบ' }));
		expect(screen.queryByText('ลบไฟล์นี้จริงไหม?')).toBeNull();

		await fireEvent.click(screen.getByRole('button', { name: 'ลบ Numb' }));
		await fireEvent.click(screen.getByRole('button', { name: 'ลบเลย' }));
		expect(ondelete).toHaveBeenCalledWith('Linkin_Park/Singles/Numb.m4a');
	});

	it('shows the error when the delete fails', async () => {
		const ondelete = vi.fn().mockRejectedValue(new ApiError(404, 'track not found'));
		render(TrackRow, { track: makeTrack(), ondelete });
		await fireEvent.click(screen.getByRole('button', { name: 'ลบ Numb' }));
		await fireEvent.click(screen.getByRole('button', { name: 'ลบเลย' }));
		expect(await screen.findByRole('alert')).toHaveTextContent('track not found');
		expect(screen.getByRole('button', { name: 'ลบเลย' })).toBeEnabled();
	});
});
