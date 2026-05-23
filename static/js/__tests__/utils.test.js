import { describe, expect, it } from 'vitest';
import { escapeHtml, escapeRegex, parseUrlParams } from '../utils.js';

describe('escapeHtml', () => {
    it('escapes HTML special characters', () => {
        expect(escapeHtml('<script>alert("x")</script>')).toBe('&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;');
    });

    it('escapes ampersands', () => {
        expect(escapeHtml('Tom & Jerry')).toBe('Tom &amp; Jerry');
    });

    it('returns empty string for nullish values', () => {
        expect(escapeHtml(null)).toBe('');
        expect(escapeHtml(undefined)).toBe('');
    });

    it('coerces numbers to strings', () => {
        expect(escapeHtml(42)).toBe('42');
    });
});

describe('parseUrlParams', () => {
    it('parses preview page query parameters', () => {
        expect(parseUrlParams('?account=3&tag=sports&category=News')).toEqual({
            account: '3',
            tag: 'sports',
            category: 'News',
        });
    });

    it('returns null for missing parameters', () => {
        expect(parseUrlParams('account=5')).toEqual({
            account: '5',
            tag: null,
            category: null,
        });
    });
});

describe('escapeRegex', () => {
    it('escapes regex metacharacters', () => {
        expect(escapeRegex('ESPN (HD) [US]')).toBe('ESPN \\(HD\\) \\[US\\]');
    });
});
