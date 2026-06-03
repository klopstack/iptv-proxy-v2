import { describe, expect, it } from 'vitest';
import {
    formatMappingConfidencePercent,
    getMappingConfidenceClass,
} from '../lib/epg_mappings_helpers.js';

describe('getMappingConfidenceClass', () => {
    it('maps high confidence to success', () => {
        expect(getMappingConfidenceClass(0.95)).toBe('text-success');
    });

    it('maps medium confidence to warning', () => {
        expect(getMappingConfidenceClass(0.8)).toBe('text-warning');
    });

    it('maps low confidence to danger', () => {
        expect(getMappingConfidenceClass(0.5)).toBe('text-danger');
    });
});

describe('formatMappingConfidencePercent', () => {
    it('rounds fractional confidence to percent', () => {
        expect(formatMappingConfidencePercent(0.876)).toBe(88);
    });
});
