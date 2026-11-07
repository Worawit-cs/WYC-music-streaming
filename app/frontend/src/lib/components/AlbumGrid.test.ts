import { fireEvent, render, screen } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import { albumList } from '../albumList';
import { LIBRARY } from '../testData';
import AlbumGrid from './AlbumGrid.svelte';

const cards = albumList(LIBRARY);

describe('AlbumGrid', () => {
	it('shows one closed card per album', () => {
		render(AlbumGrid, { cards, ondelete: vi.fn() });
		const buttons = screen.getAllByRole('button', { expanded: false });
		expect(buttons).toHaveLength(3);
		expect(buttons[1]).toHaveTextContent('Meteora');
		expect(buttons[1]).toHaveTextContent('Linkin Park');
		expect(buttons[1]).toHaveTextContent('2 เพลง');
		expect(screen.queryByText('Faint')).toBeNull();
	});

	it('opens one card at a time', async () => {
		render(AlbumGrid, { cards, ondelete: vi.fn() });
		await fireEvent.click(screen.getByRole('button', { name: /Meteora/ }));
		expect(screen.getByRole('button', { name: /Meteora/ })).toHaveAttribute('aria-expanded', 'true');
		expect(screen.getByText('Faint')).toBeInTheDocument();
		await fireEvent.click(screen.getByRole('button', { name: /Diamond Life/ }));
		expect(screen.queryByText('Faint')).toBeNull();
		expect(screen.getByText('Smooth Operator')).toBeInTheDocument();
		await fireEvent.click(screen.getByRole('button', { name: /Diamond Life/ }));
		expect(screen.queryByText('Smooth Operator')).toBeNull();
	});

	it('deletes through the track row', async () => {
		const ondelete = vi.fn();
		render(AlbumGrid, { cards, ondelete });
		await fireEvent.click(screen.getByRole('button', { name: /Diamond Life/ }));
		await fireEvent.click(screen.getByRole('button', { name: 'ลบ Smooth Operator' }));
		await fireEvent.click(screen.getByRole('button', { name: 'ลบเลย' }));
		expect(ondelete).toHaveBeenCalledWith('Sade/Diamond_Life/Smooth_Operator.m4a');
	});
});
