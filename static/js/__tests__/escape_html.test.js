import { describe, expect, it } from 'vitest';
import { escapeHtml } from '../lib/escape_html.js';

describe('escapeHtml (lib)', () => {
    it('escapes HTML special characters including single quotes', () => {
        expect(escapeHtml('<script>alert("x")</script>')).toBe(
            '&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;',
        );
        expect(escapeHtml("it's")).toBe('it&#039;s');
    });

    it('returns empty string for nullish values', () => {
        expect(escapeHtml(null)).toBe('');
        expect(escapeHtml(undefined)).toBe('');
    });
});
