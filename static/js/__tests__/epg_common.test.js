import { describe, expect, it, vi } from 'vitest';
import {
    formatLocalDateTime,
    formatProgramTimeRange,
    formatRelativeTime,
    formatUtcTimestamp,
    parseUTCDateTime,
    parseUtcTimestamp,
} from '../lib/epg_datetime.js';

describe('parseUtcTimestamp (legacy bridge)', () => {
    it('matches parseUTCDateTime for naive ISO strings', () => {
        expect(parseUtcTimestamp('2026-05-22T15:30:00')?.toISOString()).toBe(
            parseUTCDateTime('2026-05-22T15:30:00')?.toISOString(),
        );
    });

    it('returns null for invalid timestamps', () => {
        expect(parseUtcTimestamp('not-a-date')).toBeNull();
    });
});

describe('formatUtcTimestamp', () => {
    it('returns fallback when input is empty', () => {
        expect(formatUtcTimestamp('', 'Unknown')).toBe('Unknown');
    });

    it('formats valid UTC timestamps', () => {
        const formatted = formatUtcTimestamp('2026-05-22T15:30:00Z');
        expect(formatted).not.toBe('-');
        expect(formatted.length).toBeGreaterThan(5);
    });
});

describe('parseUTCDateTime', () => {
    it('returns null for empty input', () => {
        expect(parseUTCDateTime('')).toBeNull();
        expect(parseUTCDateTime(null)).toBeNull();
    });

    it('returns null for invalid timestamps', () => {
        expect(parseUTCDateTime('not-a-date')).toBeNull();
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

    it('handles spring DST transition in America/New_York', () => {
        const beforeJump = formatLocalDateTime('2026-03-08T06:30:00Z', {
            timeZone: 'America/New_York',
            hour: '2-digit',
            minute: '2-digit',
            hour12: false,
        });
        const afterJump = formatLocalDateTime('2026-03-08T07:30:00Z', {
            timeZone: 'America/New_York',
            hour: '2-digit',
            minute: '2-digit',
            hour12: false,
        });

        expect(beforeJump).toContain('01:30');
        expect(afterJump).toContain('03:30');
    });

    it('handles fall DST transition in America/New_York', () => {
        const firstOneThirty = formatLocalDateTime('2026-11-01T05:30:00Z', {
            timeZone: 'America/New_York',
            hour: '2-digit',
            minute: '2-digit',
            hour12: false,
        });
        const secondOneThirty = formatLocalDateTime('2026-11-01T06:30:00Z', {
            timeZone: 'America/New_York',
            hour: '2-digit',
            minute: '2-digit',
            hour12: false,
        });

        expect(firstOneThirty).toContain('01:30');
        expect(secondOneThirty).toContain('01:30');
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

    it('correctly compares explicit-offset timestamps to UTC now', () => {
        vi.spyOn(Intl, 'RelativeTimeFormat').mockImplementation(() => ({
            format: (value, unit) => `${value} ${unit}`,
        }));

        const result = formatRelativeTime(
            '2026-05-22T11:30:00-04:00',
            new Date('2026-05-22T15:00:00Z'),
        );

        expect(result).toBe('30 minute');
        vi.restoreAllMocks();
    });
});
