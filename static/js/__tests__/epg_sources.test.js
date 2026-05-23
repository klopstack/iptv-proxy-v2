import { describe, expect, it } from 'vitest';
import {
    buildSourceInfoLabel,
    getSourceTypeFieldVisibility,
    isLegacyProviderSource,
    shouldShowProviderDeprecationWarning,
} from '../lib/epg_sources_helpers.js';

describe('getSourceTypeFieldVisibility', () => {
    it('shows provider fields and deprecation warning for provider type', () => {
        expect(getSourceTypeFieldVisibility('provider')).toEqual({
            providerFields: true,
            providerDeprecationWarning: true,
            xmltvUrlFields: false,
            sdFields: false,
            grabberFields: false,
            ppvFields: false,
        });
    });

    it('shows schedules direct fields only for SD type', () => {
        expect(getSourceTypeFieldVisibility('schedules_direct')).toEqual({
            providerFields: false,
            providerDeprecationWarning: false,
            xmltvUrlFields: false,
            sdFields: true,
            grabberFields: false,
            ppvFields: false,
        });
    });

    it('hides all type-specific fields for empty selection', () => {
        expect(getSourceTypeFieldVisibility('')).toEqual({
            providerFields: false,
            providerDeprecationWarning: false,
            xmltvUrlFields: false,
            sdFields: false,
            grabberFields: false,
            ppvFields: false,
        });
    });
});

describe('shouldShowProviderDeprecationWarning', () => {
    it('returns true only for provider source type', () => {
        expect(shouldShowProviderDeprecationWarning('provider')).toBe(true);
        expect(shouldShowProviderDeprecationWarning('xmltv_grabber')).toBe(false);
    });
});

describe('isLegacyProviderSource', () => {
    it('detects legacy provider sources by deprecated flag', () => {
        expect(isLegacyProviderSource({ source_type: 'xmltv_url', deprecated: true })).toBe(true);
    });

    it('detects legacy provider sources by source type', () => {
        expect(isLegacyProviderSource({ source_type: 'provider' })).toBe(true);
    });

    it('returns false for non-provider sources without deprecated flag', () => {
        expect(isLegacyProviderSource({ source_type: 'schedules_direct', deprecated: false })).toBe(false);
    });
});

describe('buildSourceInfoLabel', () => {
    it('labels provider sources with account name', () => {
        expect(buildSourceInfoLabel({
            source_type: 'provider',
            account_name: 'Main IPTV',
            account_id: 3,
        })).toBe('Main IPTV');
    });

    it('truncates long XMLTV URLs', () => {
        const longUrl = `http://example.com/${'a'.repeat(50)}.xml`;
        expect(buildSourceInfoLabel({ source_type: 'xmltv_url', url: longUrl })).toBe(`${longUrl.substring(0, 40)}...`);
    });

    it('returns grabber name for xmltv_grabber sources', () => {
        expect(buildSourceInfoLabel({
            source_type: 'xmltv_grabber',
            xmltv_grabber: 'tv_grab_zz_sdjson',
        })).toBe('tv_grab_zz_sdjson');
    });
});
