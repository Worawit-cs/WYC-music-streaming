import { ApiError } from './api';
import type { JobStatus } from './types';

/** 187 → "3:07", 3725 → "1:02:05", null → "–:––". */
export function formatDuration(seconds: number | null | undefined): string {
	if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return '–:––';
	const s = Math.round(seconds);
	const h = Math.floor(s / 3600);
	const m = Math.floor((s % 3600) / 60);
	const sec = String(s % 60).padStart(2, '0');
	return h ? `${h}:${String(m).padStart(2, '0')}:${sec}` : `${m}:${sec}`;
}

/** 0.4237 → "42%", clamped to 0–100. */
export function percent(fraction: number): string {
	return `${Math.round(Math.min(Math.max(fraction, 0), 1) * 100)}%`;
}

export const STATUS_LABEL: Record<JobStatus, string> = {
	queued: 'รอคิว',
	downloading: 'กำลังอัด',
	done: 'เสร็จแล้ว',
	failed: 'ล้มเหลว',
	cancelled: 'ยกเลิกแล้ว'
};

/** One line of text for the UI from any error thrown by the API client. */
export function errorText(error: unknown): string {
	if (error instanceof ApiError) {
		if (error.status === 504) return 'ค้นหานานเกินไป ลองใหม่อีกครั้ง';
		if (typeof error.detail === 'string') return error.detail;
		return `เกิดข้อผิดพลาด (HTTP ${error.status})`;
	}
	return 'ติดต่อเซิร์ฟเวอร์ไม่ได้';
}
