/**
 * Canonical HTML escaping for admin UI (legacy window bridge + ESM import).
 * @param {unknown} text
 * @returns {string}
 */
export function escapeHtml(text) {
    if (text === null || text === undefined) {
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
