/**
 * DOM / inline-handler utilities for EPG management classic and ESM scripts.
 */

/**
 * Escape a string embedded in a single-quoted JS literal inside an HTML onclick attribute.
 * @param {string|null|undefined} text
 * @returns {string}
 */
export function escapeJsSingleQuoted(text) {
    return String(text ?? '').replace(/\\/g, '\\\\').replace(/'/g, "\\'");
}

/**
 * @param {(...args: unknown[]) => void} func
 * @param {number} wait
 * @returns {(...args: unknown[]) => void}
 */
export function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(this, args), wait);
    };
}
