import { describe, expect, it } from 'vitest';
import { formatDuration } from '../lib/epg_preview_helpers.js';

describe('formatDuration', () => {
    it('formats sub-hour durations in minutes', () => {
        const start = new Date('2026-01-01T12:00:00Z');
        const stop = new Date('2026-01-01T12:45:00Z');
        expect(formatDuration(start, stop)).toBe('45m');
    });

    it('formats whole hours without minutes', () => {
        const start = new Date('2026-01-01T12:00:00Z');
        const stop = new Date('2026-01-01T14:00:00Z');
        expect(formatDuration(start, stop)).toBe('2h');
    });

    it('formats hours and minutes', () => {
        const start = new Date('2026-01-01T12:00:00Z');
        const stop = new Date('2026-01-01T13:30:00Z');
        expect(formatDuration(start, stop)).toBe('1h 30m');
    });
});
