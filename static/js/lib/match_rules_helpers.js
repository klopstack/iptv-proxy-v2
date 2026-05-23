/**
 * Pure helpers for EPG match rules admin UI.
 */

export const PATTERN_BASED_MATCH_TYPES = ['regex', 'exact_name', 'fuzzy_name', 'category_pattern'];

/**
 * @param {string} matchType
 * @returns {boolean}
 */
export function ruleNeedsPattern(matchType) {
    return PATTERN_BASED_MATCH_TYPES.includes(matchType);
}

/**
 * @param {string} matchType
 * @param {string} pattern
 * @param {string} categoryPattern
 * @returns {string|null}
 */
export function validateRulePreviewInput(matchType, pattern, categoryPattern) {
    if (ruleNeedsPattern(matchType) && !pattern && !categoryPattern) {
        return 'Please enter a pattern or category filter to preview';
    }

    return null;
}

/**
 * @param {string} matchType
 * @param {string} action
 * @returns {{ confidenceGroup: boolean, fallbackGroup: boolean }}
 */
export function getRuleFormFieldVisibility(matchType, action) {
    return {
        confidenceGroup: matchType === 'fuzzy_name',
        fallbackGroup: action === 'use_fallback',
    };
}

/**
 * @param {string|null|undefined} input
 * @returns {string[]|null}
 */
export function parseCountryCodes(input) {
    if (!input) {
        return null;
    }

    const codes = String(input)
        .split(',')
        .map((value) => value.trim().toUpperCase())
        .filter((value) => value.length > 0);

    return codes.length > 0 ? codes : null;
}

/**
 * @param {Array<{ priority?: number }>} items
 * @param {{ descending?: boolean }} [options]
 * @returns {Array<{ priority?: number }>}
 */
export function sortByPriority(items, { descending = false } = {}) {
    return [...items].sort((left, right) => {
        const delta = (left.priority ?? 0) - (right.priority ?? 0);
        return descending ? -delta : delta;
    });
}

/**
 * @param {string|null|undefined} name
 * @param {{ caseSensitive?: boolean }} [options]
 * @returns {string}
 */
export function normalizeNameMappingKey(name, { caseSensitive = false } = {}) {
    const trimmed = String(name ?? '').trim();
    return caseSensitive ? trimmed : trimmed.toLowerCase();
}

/**
 * @param {string|null|undefined} oldName
 * @returns {string|null}
 */
export function validateNameMappingPreviewInput(oldName) {
    if (!String(oldName ?? '').trim()) {
        return 'Please enter an old name pattern to preview';
    }

    return null;
}
