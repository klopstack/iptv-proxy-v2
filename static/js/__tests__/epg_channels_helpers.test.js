import { describe, expect, it } from 'vitest';
import { renderEpgChannelRow } from '../lib/epg_channels_helpers.js';

describe('renderEpgChannelRow', () => {
    it('escapes channel metadata in table row HTML', () => {
        const html = renderEpgChannelRow({
            channel_id: 'ch<script>',
            display_name: 'News &amp; Sports',
            icon_url: 'https://example.com/icon.png',
            program_count: 3,
            mapping_count: 1,
        });

        expect(html).toContain('<code>ch&lt;script&gt;</code>');
        expect(html).toContain('News &amp;amp; Sports');
        expect(html).toContain('https://example.com/icon.png');
        expect(html).toContain('<td>3</td>');
        expect(html).toContain('<td>1</td>');
    });

    it('renders dash placeholders for missing optional fields', () => {
        const html = renderEpgChannelRow({ channel_id: 'abc' });
        expect(html).toContain('>-</td>');
        expect(html).not.toContain('<img');
    });
});
