import { describe, expect, it, vi } from 'vitest';
import {
    formatLocalDateTime,
    formatProgramTimeRange,
    formatRelativeTime,
    parseUTCDateTime,
} from '../lib/epg_datetime.js';

describe('parseUTCDateTime', () => {
    it('returns null for empty input', () => {
        expect(parseUTCDateTime('')).toBeNull();
        expect(parseUTCDateTime(null)).toBeNull();
    });

    it('appends Z for timezone-less ISO strings', () => {
        const date = parseUTCDateTime('2026-05-22T15:30:00');
        expect(date?.toISOString()).toBe('2026-05-22T15:30:00.000Z');
    });

    it('preserves explicit UTC suffix', () => {
        const date = parseUTCDateTime('2026-05-22T15:30:00Z');
        expect(date?.toISOString()).toBe('2026-05-22T15:30:00.000Z');
    });

    it('preserves explicit numeric offsets', () => {
        const date = parseUTCDateTime('2026-05-22T11:30:00-04:00');
        expect(date?.toISOString()).toBe('2026-05-22T15:30:00.000Z');
    });
});

describe('formatLocalDateTime', () => {
    it('returns empty string for invalid input', () => {
        expect(formatLocalDateTime('not-a-date')).toBe('');
    });

    it('formats valid UTC timestamps', () => {
        const formatted = formatLocalDateTime('2026-05-22T15:30:00Z', {
            timeZone: 'UTC',
            hour: '2-digit',
            minute: '2-digit',
            hour12: false,
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
        });

        expect(formatted).toContain('05/22/2026');
        expect(formatted).toContain('15:30');
    });
});

describe('formatProgramTimeRange', () => {
    it('builds a start-stop range', () => {
        const range = formatProgramTimeRange('2026-05-22T15:00:00Z', '2026-05-22T16:30:00Z');
        expect(range).toMatch(/ - /);
        expect(range.length).toBeGreaterThan(3);
    });

    it('returns empty string when either time is invalid', () => {
        expect(formatProgramTimeRange('', '2026-05-22T16:30:00Z')).toBe('');
    });
});

describe('formatRelativeTime', () => {
    it('returns empty string for invalid input', () => {
        expect(formatRelativeTime('invalid', new Date('2026-05-22T12:00:00Z'))).toBe('');
    });

    it('uses fallback wording for near-future timestamps', () => {
        vi.spyOn(Intl, 'RelativeTimeFormat').mockImplementation(() => ({
            format: () => 'in 5 minutes',
        }));

        const result = formatRelativeTime(
            '2026-05-22T12:05:00Z',
            new Date('2026-05-22T12:00:00Z'),
        );

        expect(result).toBe('in 5 minutes');
        vi.restoreAllMocks();
    });
});
