/**
 * Site-wide legacy bridges: escapeHtml and UTC timestamp helpers for inline scripts.
 */
import { escapeHtml } from '../lib/escape_html.js';
import { formatUtcTimestamp, parseUtcTimestamp } from '../lib/epg_datetime.js';

Object.assign(window, {
    escapeHtml,
    parseUtcTimestamp,
    formatUtcTimestamp,
});
