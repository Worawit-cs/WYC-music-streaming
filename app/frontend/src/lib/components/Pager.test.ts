import { fireEvent, render, screen } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import Pager from './Pager.svelte';

describe('Pager', () => {
	it('shows each page and marks the current one', () => {
		render(Pager, { page: 2, last: 5, ongo: vi.fn() });
		const numbers = ['1', '2', '3', '4', '5'].map((n) => screen.getByRole('button', { name: n }));
		expect(numbers[1]).toHaveAttribute('aria-current', 'page');
		expect(numbers[0]).not.toHaveAttribute('aria-current');
	});

	it('goes to the clicked, previous and next page', async () => {
		const ongo = vi.fn();
		render(Pager, { page: 2, last: 5, ongo });
		await fireEvent.click(screen.getByRole('button', { name: '4' }));
		await fireEvent.click(screen.getByRole('button', { name: '« ก่อน' }));
		await fireEvent.click(screen.getByRole('button', { name: 'ถัดไป »' }));
		expect(ongo.mock.calls).toEqual([[4], [1], [3]]);
	});

	it('does nothing on the current page', async () => {
		const ongo = vi.fn();
		render(Pager, { page: 2, last: 5, ongo });
		await fireEvent.click(screen.getByRole('button', { name: '2' }));
		expect(ongo).not.toHaveBeenCalled();
	});

	it('disables previous on the first page and next on the last page', () => {
		render(Pager, { page: 1, last: 1, ongo: vi.fn() });
		expect(screen.getByRole('button', { name: '« ก่อน' })).toBeDisabled();
		expect(screen.getByRole('button', { name: 'ถัดไป »' })).toBeDisabled();
	});

	it('disables every button while a page loads', () => {
		render(Pager, { page: 2, last: 3, busy: true, ongo: vi.fn() });
		for (const button of screen.getAllByRole('button')) expect(button).toBeDisabled();
	});
});
