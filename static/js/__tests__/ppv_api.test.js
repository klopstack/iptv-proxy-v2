import { describe, expect, it } from 'vitest';
import { PPV_ENRICHMENT_CONFIG_URL, PPV_ENRICHMENT_SETTINGS_URL } from '../lib/ppv_api.js';

describe('ppv_api URLs', () => {
    it('exposes config and read-only settings paths', () => {
        expect(PPV_ENRICHMENT_CONFIG_URL).toBe('/api/ppv-enrichment/config');
        expect(PPV_ENRICHMENT_SETTINGS_URL).toBe('/api/ppv-enrichment/settings');
    });
});
