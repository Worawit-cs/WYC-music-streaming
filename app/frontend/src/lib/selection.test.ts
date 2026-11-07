import { describe, expect, it } from 'vitest';
import {
	cardState,
	defaultSelection,
	draftFrom,
	summarizeCreate,
	toJobItem,
	validateDraft
} from './selection';
import { makeJob, makeResult } from './testData';

const draft = { video_id: 'kXYiU_JCYtU', title: 'Numb', artist: 'Linkin Park', album: 'Singles' };

describe('selection', () => {
	it('builds a draft from the suggested tags', () => {
		expect(draftFrom(makeResult())).toEqual(draft);
	});

	it('prefills the artist with a library name when the guess has guests', () => {
		const result = makeResult({ suggested: { title: 'Numb', artist: 'Linkin Park, Jay-Z', album: 'Singles' } });
		expect(draftFrom(result, ['Linkin Park']).artist).toBe('Linkin Park');
		expect(draftFrom(result).artist).toBe('Linkin Park, Jay-Z');
	});

	it('validates blank and long fields', () => {
		expect(validateDraft(draft)).toBeNull();
		expect(validateDraft({ ...draft, title: ' ' })).toBe('กรอกชื่อเพลงก่อน');
		expect(validateDraft({ ...draft, album: 'x'.repeat(301) })).toBe('อัลบั้มยาวเกิน 300 ตัวอักษร');
	});

	it('trims fields and applies a non-blank album override', () => {
		const padded = { ...draft, title: ' Numb ', artist: ' Linkin Park ' };
		expect(toJobItem(padded)).toEqual(draft);
		expect(toJobItem(draft, ' Phonk Mix ').album).toBe('Phonk Mix');
		expect(toJobItem(draft, '  ').album).toBe('Singles');
	});

	it('gives each card a state', () => {
		const ids = new Set(['inlib000000']);
		const jobs = [makeJob({ video_id: 'queued00000', status: 'queued' }), makeJob({ id: 2, video_id: 'failed00000', status: 'failed' })];
		expect(cardState('inlib000000', ids, jobs)).toBe('in_library');
		expect(cardState('queued00000', ids, jobs)).toBe('active');
		expect(cardState('failed00000', ids, jobs)).toBe('new');
		expect(cardState('other000000', ids, jobs)).toBe('new');
	});

	it('selects every playlist entry that is not in the library', () => {
		const results = [makeResult({ video_id: 'a0000000000' }), makeResult({ video_id: 'b0000000000' })];
		expect(defaultSelection(results, new Set(['b0000000000']))).toEqual(['a0000000000']);
	});

	it('summarizes created and skipped jobs', () => {
		expect(summarizeCreate({ created: [makeJob(), makeJob({ id: 2 })], skipped: [{ video_id: 'x', reason: 'in_library' }] }))
			.toBe('เพิ่ม 2 เพลงเข้าคิวแล้ว · ข้าม 1 เพลงที่มีในคลังหรืออยู่ในคิวแล้ว');
		expect(summarizeCreate({ created: [], skipped: [] })).toBe('ไม่มีเพลงที่ต้องโหลด');
	});
});
