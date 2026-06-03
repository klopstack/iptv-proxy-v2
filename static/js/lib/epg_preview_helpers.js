/**
 * Pure helpers for EPG data preview UI.
 */

/**
 * @param {Date} start
 * @param {Date} stop
 * @returns {string}
 */
export function formatDuration(start, stop) {
    const diffMs = stop - start;
    const diffMins = Math.round(diffMs / 60000);

    if (diffMins < 60) {
        return `${diffMins}m`;
    }

    const hours = Math.floor(diffMins / 60);
    const mins = diffMins % 60;
    return mins > 0 ? `${hours}h ${mins}m` : `${hours}h`;
}
