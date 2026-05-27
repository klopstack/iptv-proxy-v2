import { describe, expect, it } from 'vitest';
import {
    buildSourceInfoLabel,
    getSourceTypeFieldVisibility,
    isLegacyProviderSource,
} from '../lib/epg_sources_helpers.js';

describe('getSourceTypeFieldVisibility', () => {
    it('shows schedules direct fields only for SD type', () => {
        expect(getSourceTypeFieldVisibility('schedules_direct')).toEqual({
            xmltvUrlFields: false,
            sdFields: true,
            grabberFields: false,
            ppvFields: false,
        });
    });

    it('shows xmltv url fields for xmltv_url type', () => {
        expect(getSourceTypeFieldVisibility('xmltv_url')).toEqual({
            xmltvUrlFields: true,
            sdFields: false,
            grabberFields: false,
            ppvFields: false,
        });
    });

    it('hides all type-specific fields for empty selection', () => {
        expect(getSourceTypeFieldVisibility('')).toEqual({
            xmltvUrlFields: false,
            sdFields: false,
            grabberFields: false,
            ppvFields: false,
        });
    });
});

describe('isLegacyProviderSource', () => {
    it('detects legacy provider sources in the database', () => {
        expect(isLegacyProviderSource({ source_type: 'provider' })).toBe(true);
    });

    it('returns false for supported source types', () => {
        expect(isLegacyProviderSource({ source_type: 'schedules_direct' })).toBe(false);
        expect(isLegacyProviderSource({ source_type: 'xmltv_url' })).toBe(false);
    });
});

describe('buildSourceInfoLabel', () => {
    it('labels provider sources with account name', () => {
        expect(buildSourceInfoLabel({ source_type: 'provider', account_name: 'Main' })).toBe('Main');
    });

    it('truncates long xmltv urls', () => {
        const longUrl = 'https://example.com/' + 'a'.repeat(50);
        expect(buildSourceInfoLabel({ source_type: 'xmltv_url', url: longUrl })).toMatch(/\.\.\.$/);
    });
});
