import { describe, expect, it } from 'vitest';
import { buildMatchRulesReferenceHtml } from '../lib/match_rules_reference_helpers.js';

describe('buildMatchRulesReferenceHtml', () => {
    it('renders match types, actions, sources, and exclusion types', () => {
        const html = buildMatchRulesReferenceHtml({
            match_types: [{ value: 'regex', description: 'Regular expression match' }],
            actions: [{ value: 'map_epg', description: 'Map to EPG channel' }],
            sources: [{ value: 'cleaned_name', description: 'Normalized channel name' }],
            exclusion_types: [{ value: 'name', description: 'Channel name pattern' }],
        });

        expect(html).toContain('<code>regex</code>');
        expect(html).toContain('Regular expression match');
        expect(html).toContain('<code>map_epg</code>');
        expect(html).toContain('<code>cleaned_name</code>');
        expect(html).toContain('Exclusion Pattern Types');
        expect(html).toContain('<code>name</code>');
    });
});
