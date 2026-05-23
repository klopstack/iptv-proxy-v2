/**
 * Shared frontend utilities.
 */

/**
 * Escape HTML special characters for safe insertion into DOM strings.
 * @param {unknown} text
 * @returns {string}
 */
export function escapeHtml(text) {
    if (text == null) {
        return '';
    }

    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;',
    };

    return String(text).replace(/[&<>"']/g, (char) => map[char]);
}

/**
 * Parse common preview-page URL query parameters.
 * @param {string} [searchString]
 * @returns {{ account: string|null, tag: string|null, category: string|null }}
 */
export function parseUrlParams(searchString = '') {
    const normalized = searchString.startsWith('?') ? searchString.slice(1) : searchString;
    const params = new URLSearchParams(normalized);

    return {
        account: params.get('account'),
        tag: params.get('tag'),
        category: params.get('category'),
    };
}

/**
 * Escape special regex characters in a literal string.
 * @param {string} text
 * @returns {string}
 */
export function escapeRegex(text) {
    return String(text).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
