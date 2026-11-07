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

	it('renames an album from its card and offers the other albums of that artist', async () => {
		const onrename = vi.fn().mockResolvedValue(undefined);
		render(AlbumGrid, { cards, ondelete: vi.fn(), onrename });
		await fireEvent.click(screen.getByRole('button', { name: 'แก้ชื่ออัลบั้ม Meteora' }));
		const input = screen.getByLabelText('ชื่ออัลบั้มใหม่') as HTMLInputElement;
		expect(input.value).toBe('Meteora');
		await fireEvent.focus(input);
		expect(screen.getAllByRole('option').map((o) => o.textContent?.replace(/\s+/g, ' ').trim())).toEqual([
			'Singles 1 เพลง'
		]);
		await fireEvent.input(input, { target: { value: 'Meteora (Live)' } });
		await fireEvent.click(screen.getByRole('button', { name: 'บันทึก' }));
		expect(onrename).toHaveBeenCalledWith(cards[1], 'Meteora (Live)');
	});

	it('has no rename button without onrename', () => {
		render(AlbumGrid, { cards, ondelete: vi.fn() });
		expect(screen.queryByRole('button', { name: /แก้ชื่อ/ })).toBeNull();
	});
});
