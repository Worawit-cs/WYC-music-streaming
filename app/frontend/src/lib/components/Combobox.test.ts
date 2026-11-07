import { fireEvent, render, screen } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import Combobox from './Combobox.svelte';

const options = [
	{ value: 'Linkin Park', label: 'Linkin Park', hint: '3 เพลง' },
	{ value: 'Sade', label: 'Sade' }
];

function setup(props: Record<string, unknown> = {}) {
	const onpick = vi.fn();
	render(Combobox, { value: '', options, label: 'ศิลปิน', onpick, ...props });
	return { onpick, input: screen.getByRole('combobox', { name: 'ศิลปิน' }) as HTMLInputElement };
}

describe('Combobox', () => {
	it('opens the list on focus and wires the ARIA attributes', async () => {
		const { input } = setup();
		expect(input).toHaveAttribute('aria-expanded', 'false');
		await fireEvent.focus(input);
		const list = screen.getByRole('listbox');
		expect(input).toHaveAttribute('aria-expanded', 'true');
		expect(input).toHaveAttribute('aria-controls', list.id);
		const text = screen.getAllByRole('option').map((o) => o.textContent?.replace(/\s+/g, ' ').trim());
		expect(text).toEqual(['Linkin Park 3 เพลง', 'Sade']);
	});

	it('moves with the arrow keys and picks with Enter', async () => {
		const { input, onpick } = setup();
		await fireEvent.focus(input);
		await fireEvent.keyDown(input, { key: 'ArrowDown' });
		await fireEvent.keyDown(input, { key: 'ArrowDown' });
		const active = screen.getAllByRole('option')[1];
		expect(active).toHaveAttribute('aria-selected', 'true');
		expect(input).toHaveAttribute('aria-activedescendant', active.id);
		await fireEvent.keyDown(input, { key: 'Enter' });
		expect(onpick).toHaveBeenCalledWith('Sade');
		expect(input.value).toBe('Sade');
		expect(screen.queryByRole('listbox')).toBeNull();
	});

	it('wraps from the top to the last row with ArrowUp', async () => {
		const { input } = setup();
		await fireEvent.focus(input);
		await fireEvent.keyDown(input, { key: 'ArrowUp' });
		expect(screen.getAllByRole('option')[1]).toHaveAttribute('aria-selected', 'true');
	});

	it('closes on Escape', async () => {
		const { input } = setup();
		await fireEvent.focus(input);
		await fireEvent.keyDown(input, { key: 'Escape' });
		expect(screen.queryByRole('listbox')).toBeNull();
	});

	it('picks a row with the mouse', async () => {
		const { input, onpick } = setup();
		await fireEvent.focus(input);
		await fireEvent.click(screen.getByRole('option', { name: /Linkin Park/ }));
		expect(onpick).toHaveBeenCalledWith('Linkin Park');
		expect(input.value).toBe('Linkin Park');
	});

	it('offers a create row only for new text', async () => {
		const { input, onpick } = setup({ createLabel: 'สร้างใหม่' });
		await fireEvent.input(input, { target: { value: 'The Weeknd' } });
		const create = screen.getByRole('option', { name: '+ สร้างใหม่ "The Weeknd"' });
		await fireEvent.click(create);
		expect(onpick).toHaveBeenCalledWith('The Weeknd');
		await fireEvent.input(input, { target: { value: 'sade' } });
		expect(screen.queryByRole('option', { name: /สร้างใหม่/ })).toBeNull();
	});

	it('leaves Enter alone when no row is active', async () => {
		const { input, onpick } = setup();
		await fireEvent.focus(input);
		const event = new KeyboardEvent('keydown', { key: 'Enter', cancelable: true, bubbles: true });
		input.dispatchEvent(event);
		expect(event.defaultPrevented).toBe(false);
		expect(onpick).not.toHaveBeenCalled();
	});
});
