import { describe, expect, it, vi } from 'vitest';
import { debounce, escapeJsSingleQuoted } from '../lib/epg_dom_utils.js';

describe('escapeJsSingleQuoted', () => {
    it('escapes backslashes and single quotes', () => {
        expect(escapeJsSingleQuoted("O'Brien\\test")).toBe("O\\'Brien\\\\test");
    });

    it('coerces null to empty string', () => {
        expect(escapeJsSingleQuoted(null)).toBe('');
    });
});

describe('debounce', () => {
    it('delays invocation until wait elapses', async () => {
        vi.useFakeTimers();
        let count = 0;
        const fn = debounce(() => {
            count += 1;
        }, 100);

        fn();
        fn();
        expect(count).toBe(0);
        vi.advanceTimersByTime(100);
        expect(count).toBe(1);
        vi.useRealTimers();
    });
});
