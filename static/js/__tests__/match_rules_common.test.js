import { describe, expect, it } from 'vitest';
import {
    getRuleFormFieldVisibility,
    normalizeNameMappingKey,
    parseCountryCodes,
    ruleNeedsPattern,
    sortByPriority,
    validateNameMappingPreviewInput,
    validateRulePreviewInput,
} from '../lib/match_rules_helpers.js';

describe('ruleNeedsPattern', () => {
    it('requires patterns for regex and fuzzy match types', () => {
        expect(ruleNeedsPattern('regex')).toBe(true);
        expect(ruleNeedsPattern('fuzzy_name')).toBe(true);
        expect(ruleNeedsPattern('provider_id')).toBe(false);
    });
});

describe('validateRulePreviewInput', () => {
    it('requires a pattern or category filter for pattern-based match types', () => {
        expect(validateRulePreviewInput('regex', '', '')).toBe(
            'Please enter a pattern or category filter to preview',
        );
    });

    it('accepts category-only filters', () => {
        expect(validateRulePreviewInput('regex', '', 'Sports')).toBeNull();
    });

    it('allows non-pattern match types without input', () => {
        expect(validateRulePreviewInput('provider_id', '', '')).toBeNull();
    });
});

describe('getRuleFormFieldVisibility', () => {
    it('shows confidence controls for fuzzy matching', () => {
        expect(getRuleFormFieldVisibility('fuzzy_name', 'map_epg')).toEqual({
            confidenceGroup: true,
            fallbackGroup: false,
        });
    });

    it('shows fallback controls for use_fallback action', () => {
        expect(getRuleFormFieldVisibility('regex', 'use_fallback')).toEqual({
            confidenceGroup: false,
            fallbackGroup: true,
        });
    });
});

describe('parseCountryCodes', () => {
    it('parses and normalizes comma-separated country codes', () => {
        expect(parseCountryCodes(' us, ca ,uk ')).toEqual(['US', 'CA', 'UK']);
    });

    it('returns null for empty input', () => {
        expect(parseCountryCodes('')).toBeNull();
        expect(parseCountryCodes(' , ')).toBeNull();
    });
});

describe('sortByPriority', () => {
    it('sorts items by ascending priority by default', () => {
        const sorted = sortByPriority([
            { name: 'b', priority: 200 },
            { name: 'a', priority: 50 },
            { name: 'c', priority: 100 },
        ]);

        expect(sorted.map((item) => item.name)).toEqual(['a', 'c', 'b']);
    });

    it('supports descending priority order', () => {
        const sorted = sortByPriority(
            [{ priority: 10 }, { priority: 30 }, { priority: 20 }],
            { descending: true },
        );

        expect(sorted.map((item) => item.priority)).toEqual([30, 20, 10]);
    });
});

describe('normalizeNameMappingKey', () => {
    it('lowercases keys by default', () => {
        expect(normalizeNameMappingKey(' Bally Sports ')).toBe('bally sports');
    });

    it('preserves case when requested', () => {
        expect(normalizeNameMappingKey('ESPN HD', { caseSensitive: true })).toBe('ESPN HD');
    });
});

describe('validateNameMappingPreviewInput', () => {
    it('requires an old name pattern', () => {
        expect(validateNameMappingPreviewInput('')).toBe(
            'Please enter an old name pattern to preview',
        );
        expect(validateNameMappingPreviewInput('  ')).toBe(
            'Please enter an old name pattern to preview',
        );
    });

    it('accepts non-empty old name values', () => {
        expect(validateNameMappingPreviewInput('Bally Sports')).toBeNull();
    });
});
