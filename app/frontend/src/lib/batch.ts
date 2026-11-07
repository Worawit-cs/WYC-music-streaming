import { isActive } from './jobList';
import type { Job } from './types';

/** 'done' or 'failed' when a job we saw active has just ended that way; otherwise null. */
export function noteTransition(prev: Job | undefined, next: Job): 'done' | 'failed' | null {
	if (!prev || !isActive(prev)) return null;
	return next.status === 'done' || next.status === 'failed' ? next.status : null;
}
