import { describe, expect, it } from 'vitest';
import {
    buildCollapseBadge,
    buildDataSourceBadge,
    buildPreviewUrl,
    buildTagRuleParams,
    formatChannelCount,
    getTagBadgeColorClass,
    normalizeTag,
} from '../preview_channels.js';

describe('buildPreviewUrl', () => {
    it('builds account-specific preview URLs', () => {
        expect(buildPreviewUrl(7, { offset: 100 })).toBe('/api/accounts/7/preview?limit=50&offset=100');
    });

    it('builds all-accounts preview URLs', () => {
        expect(buildPreviewUrl('all', { limit: 25, offset: 0 })).toBe('/api/channels/preview?limit=25&offset=0');
    });

    it('includes optional filters in the query string', () => {
        const url = buildPreviewUrl(2, {
            tags: ['sports', '4k'],
            category: 'News & Weather',
            collapseDuplicates: true,
            search: 'ESPN HD',
        });

        expect(url).toBe(
            '/api/accounts/2/preview?limit=50&offset=0&tags=sports,4k&category=News%20%26%20Weather&collapse_duplicates=true&search=ESPN%20HD',
        );
    });
});

describe('getTagBadgeColorClass', () => {
    it('maps known tag sources to badge classes', () => {
        expect(getTagBadgeColorClass('extraction')).toBe('bg-info');
        expect(getTagBadgeColorClass('enrichment')).toBe('bg-success');
        expect(getTagBadgeColorClass('manual')).toBe('bg-warning text-dark');
        expect(getTagBadgeColorClass('sync')).toBe('bg-secondary');
    });

    it('falls back to info styling for unknown sources', () => {
        expect(getTagBadgeColorClass('unknown')).toBe('bg-info');
    });
});

describe('normalizeTag', () => {
    it('normalizes string tags', () => {
        expect(normalizeTag('sports')).toEqual({ name: 'sports', source: 'extraction' });
    });

    it('normalizes object tags and defaults missing source', () => {
        expect(normalizeTag({ name: 'ppv', source: 'manual' })).toEqual({ name: 'ppv', source: 'manual' });
        expect(normalizeTag({ name: 'local' })).toEqual({ name: 'local', source: 'extraction' });
    });
});

describe('buildTagRuleParams', () => {
    it('builds regex rule params with escaped channel names', () => {
        const params = buildTagRuleParams(4, 'ESPN (HD)');

        expect(params.get('account_id')).toBe('4');
        expect(params.get('pattern')).toBe('^ESPN \\(HD\\)$');
        expect(params.get('from_preview_page')).toBe('true');
    });
});

describe('formatChannelCount', () => {
    it('formats loaded/total counts', () => {
        expect(formatChannelCount(50, 200)).toBe('Showing 50 of 200 channels');
    });

    it('formats loaded-only counts when total is unknown', () => {
        expect(formatChannelCount(75, 0)).toBe('Loaded 75 channels');
    });
});

describe('buildDataSourceBadge', () => {
    it('returns database and API badges', () => {
        expect(buildDataSourceBadge(true)).toContain('Database');
        expect(buildDataSourceBadge(false)).toContain('API');
    });
});

describe('buildCollapseBadge', () => {
    it('returns collapse badge only when duplicates were hidden', () => {
        expect(buildCollapseBadge(true, 3)).toContain('3 collapsed');
        expect(buildCollapseBadge(true, 0)).toBe('');
        expect(buildCollapseBadge(false, 5)).toBe('');
    });
});
