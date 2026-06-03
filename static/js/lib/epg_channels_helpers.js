/**
 * Pure helpers for EPG channels list UI.
 */
import { escapeHtml } from './escape_html.js';

/**
 * @param {{ channel_id: string, display_name?: string, icon_url?: string, program_count?: number, mapping_count?: number }} ch
 * @returns {string}
 */
export function renderEpgChannelRow(ch) {
    return `
        <tr>
            <td><code>${escapeHtml(ch.channel_id)}</code></td>
            <td>${escapeHtml(ch.display_name || '-')}</td>
            <td>${ch.icon_url ? `<img src="${escapeHtml(ch.icon_url)}" style="max-height: 24px;">` : '-'}</td>
            <td>${ch.program_count || 0}</td>
            <td>${ch.mapping_count || 0}</td>
        </tr>
    `;
}
