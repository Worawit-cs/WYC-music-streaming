import { fireEvent, render, screen } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import { makeResult } from '$lib/testData';
import ResultCard from './ResultCard.svelte';

describe('ResultCard', () => {
	it('offers a download for a new track', async () => {
		const ondownload = vi.fn();
		render(ResultCard, { result: makeResult(), state: 'new', mode: 'single', ondownload });
		expect(screen.getByText('→ Linkin Park / Singles / Numb')).toBeInTheDocument();
		await fireEvent.click(screen.getByRole('button', { name: 'โหลด' }));
		expect(ondownload).toHaveBeenCalledOnce();
	});

	it('shows a badge instead of the button for a track in the library', () => {
		render(ResultCard, { result: makeResult(), state: 'in_library', mode: 'single' });
		expect(screen.queryByRole('button')).toBeNull();
		expect(screen.getByText('มีในคลังแล้ว')).toBeInTheDocument();
	});

	it('toggles in pick mode and disables queued tracks', async () => {
		const ontoggle = vi.fn();
		const { unmount } = render(ResultCard, { result: makeResult(), state: 'new', mode: 'pick', selected: true, ontoggle });
		const box = screen.getByRole('checkbox');
		expect(box).toBeChecked();
		await fireEvent.click(box);
		expect(ontoggle).toHaveBeenCalledOnce();
		unmount();
		render(ResultCard, { result: makeResult(), state: 'active', mode: 'pick' });
		expect(screen.getByRole('checkbox')).toBeDisabled();
		expect(screen.getByText('อยู่ในคิว')).toBeInTheDocument();
	});
});
