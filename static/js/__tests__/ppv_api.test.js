import { describe, expect, it } from 'vitest';
import {
    PPV_ENRICHMENT_CHANNELS_URL,
    PPV_ENRICHMENT_CONFIG_URL,
    PPV_ENRICHMENT_SETTINGS_URL,
    PPV_EPG_EVENTS_URL,
    PPV_PROVIDER_SETTINGS_URL,
    buildPpvQueryString,
} from '../lib/ppv_api.js';

describe('ppv_api URLs', () => {
    it('exposes config and read-only settings paths', () => {
        expect(PPV_ENRICHMENT_CONFIG_URL).toBe('/api/ppv-enrichment/config');
        expect(PPV_ENRICHMENT_SETTINGS_URL).toBe('/api/ppv-enrichment/settings');
        expect(PPV_PROVIDER_SETTINGS_URL).toBe('/api/ppv-enrichment/provider-settings');
    });

    it('exposes preview API paths', () => {
        expect(PPV_EPG_EVENTS_URL).toBe('/api/ppv-epg/events');
        expect(PPV_ENRICHMENT_CHANNELS_URL).toBe('/api/ppv-enrichment/channels');
    });
});

describe('buildPpvQueryString', () => {
    it('builds query strings and omits empty values', () => {
        expect(buildPpvQueryString({ mode: 'all', account_id: 1, search: '' })).toBe('?mode=all&account_id=1');
        expect(buildPpvQueryString()).toBe('');
    });
});
