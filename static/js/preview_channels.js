/**
 * Pure helpers for the preview channels page.
 */

import { escapeRegex } from './utils.js';

export const TAG_SOURCE_COLORS = {
    extraction: 'bg-info',
    enrichment: 'bg-success',
    manual: 'bg-warning text-dark',
    sync: 'bg-secondary',
};

/**
 * @param {string} source
 * @returns {string}
 */
export function getTagBadgeColorClass(source) {
    return TAG_SOURCE_COLORS[source] || 'bg-info';
}

/**
 * Normalize tag payloads from API (string or object).
 * @param {string|{ name: string, source?: string }} tag
 * @returns {{ name: string, source: string }}
 */
export function normalizeTag(tag) {
    if (typeof tag === 'string') {
        return { name: tag, source: 'extraction' };
    }

    return {
        name: tag.name,
        source: tag.source || 'extraction',
    };
}

/**
 * Build preview API URL for account or all-accounts views.
 * @param {string|number} accountId
 * @param {object} [options]
 * @param {number} [options.limit]
 * @param {number} [options.offset]
 * @param {string[]} [options.tags]
 * @param {string|null} [options.category]
 * @param {boolean} [options.collapseDuplicates]
 * @param {string} [options.search]
 * @returns {string}
 */
export function buildPreviewUrl(accountId, {
    limit = 50,
    offset = 0,
    tags = [],
    category = null,
    collapseDuplicates = false,
    search = '',
} = {}) {
    const tagParam = tags.length > 0 ? `&tags=${tags.join(',')}` : '';
    const categoryParam = category ? `&category=${encodeURIComponent(category)}` : '';
    const collapseParam = collapseDuplicates ? '&collapse_duplicates=true' : '';
    const searchParam = search ? `&search=${encodeURIComponent(search)}` : '';
    const query = `limit=${limit}&offset=${offset}${tagParam}${categoryParam}${collapseParam}${searchParam}`;

    if (accountId === 'all') {
        return `/api/channels/preview?${query}`;
    }

    return `/api/accounts/${accountId}/preview?${query}`;
}

/**
 * Build URLSearchParams for pre-filling a manual tag rule form.
 * @param {string|number} accountId
 * @param {string} channelName
 * @returns {URLSearchParams}
 */
export function buildTagRuleParams(accountId, channelName) {
    const pattern = `^${escapeRegex(channelName)}$`;

    return new URLSearchParams({
        account_id: String(accountId),
        rule_name: `Manual tag for ${channelName}`,
        pattern,
        pattern_type: 'regex',
        source: 'channel_name',
        remove_from_name: 'false',
        from_preview_page: 'true',
    });
}

/**
 * @param {number} loaded
 * @param {number} total
 * @returns {string}
 */
export function formatChannelCount(loaded, total) {
    if (total > 0) {
        return `Showing ${loaded.toLocaleString()} of ${total.toLocaleString()} channels`;
    }

    return `Loaded ${loaded.toLocaleString()} channels`;
}

/**
 * @param {boolean} usingDatabase
 * @returns {string}
 */
export function buildDataSourceBadge(usingDatabase) {
    if (usingDatabase) {
        return '<span class="badge bg-success ms-2" title="Using local database"><i class="bi bi-database-check"></i> Database</span>';
    }

    return '<span class="badge bg-warning text-dark ms-2" title="Using IPTV API"><i class="bi bi-cloud"></i> API</span>';
}

/**
 * @param {boolean} collapseDuplicates
 * @param {number} duplicatesCollapsed
 * @returns {string}
 */
export function buildCollapseBadge(collapseDuplicates, duplicatesCollapsed) {
    if (collapseDuplicates && duplicatesCollapsed > 0) {
        return `<span class="badge bg-info ms-2" title="${duplicatesCollapsed} duplicate(s) hidden"><i class="bi bi-layers"></i> ${duplicatesCollapsed} collapsed</span>`;
    }

    return '';
}
