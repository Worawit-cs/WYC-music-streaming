import { describe, expect, it } from 'vitest';
import { ApiError } from './api';
import { errorText, formatDuration, percent, stageText } from './format';
import { makeJob } from './testData';

describe('formatDuration', () => {
	it.each([
		[187, '3:07'],
		[59.6, '1:00'],
		[3725, '1:02:05'],
		[0, '0:00'],
		[null, '–:––'],
		[-1, '–:––']
	])('%s → %s', (input, expected) => {
		expect(formatDuration(input)).toBe(expected);
	});
});

describe('percent', () => {
	it('rounds and clamps', () => {
		expect(percent(0.4237)).toBe('42%');
		expect(percent(1.2)).toBe('100%');
		expect(percent(-0.1)).toBe('0%');
	});
});

describe('errorText', () => {
	it('explains a search timeout', () => {
		expect(errorText(new ApiError(504, 'search took too long'))).toBe('ค้นหานานเกินไป ลองใหม่อีกครั้ง');
	});
	it('uses a string detail', () => {
		expect(errorText(new ApiError(400, 'invalid path'))).toBe('invalid path');
	});
	it('falls back to the status for other details', () => {
		expect(errorText(new ApiError(422, [{ msg: 'x' }]))).toBe('เกิดข้อผิดพลาด (HTTP 422)');
	});
	it('handles network errors', () => {
		expect(errorText(new TypeError('Failed to fetch'))).toBe('ติดต่อเซิร์ฟเวอร์ไม่ได้');
	});
});

describe('stageText', () => {
	it('names each stage of a downloading job', () => {
		const job = makeJob({ status: 'downloading', progress: 0.42 });
		expect(stageText({ ...job, stage: 'finding' })).toBe('กำลังหาไฟล์…');
		expect(stageText({ ...job, stage: null })).toBe('กำลังหาไฟล์…');
		expect(stageText({ ...job, stage: 'downloading' })).toBe('กำลังโหลด 42%');
		expect(stageText({ ...job, stage: 'processing' })).toBe('กำลังแปลงไฟล์…');
	});
});
