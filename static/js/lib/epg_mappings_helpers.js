/**
 * Pure helpers for channel EPG mappings UI.
 */

/**
 * Bootstrap text class for mapping confidence percentage.
 * @param {number} confidence 0–1
 * @returns {'text-success' | 'text-warning' | 'text-danger'}
 */
export function getMappingConfidenceClass(confidence) {
    if (confidence >= 0.9) {
        return 'text-success';
    }
    if (confidence >= 0.7) {
        return 'text-warning';
    }
    return 'text-danger';
}

/**
 * @param {number} confidence 0–1
 * @returns {number}
 */
export function formatMappingConfidencePercent(confidence) {
    return Math.round(confidence * 100);
}
