/**
 * Pure date/time helpers for EPG admin UI.
 */

/**
 * Parse a datetime string and ensure it's treated as UTC.
 * @param {string} dateStr
 * @returns {Date|null}
 */
export function parseUTCDateTime(dateStr) {
    if (!dateStr) {
        return null;
    }

    let normalized = dateStr;
    if (!normalized.endsWith('Z') && !normalized.match(/[+-]\d{2}:\d{2}$/)) {
        normalized = `${normalized}Z`;
    }

    return new Date(normalized);
}

/**
 * @param {string} dateStr
 * @param {Object} [options]
 * @returns {string}
 */
export function formatLocalTime(dateStr, options = {}) {
    const date = parseUTCDateTime(dateStr);
    if (!date || Number.isNaN(date.getTime())) {
        return '';
    }

    return date.toLocaleTimeString(undefined, {
        hour: 'numeric',
        minute: '2-digit',
        ...options,
    });
}

/**
 * @param {string} dateStr
 * @param {Object} [options]
 * @returns {string}
 */
export function formatLocalDate(dateStr, options = {}) {
    const date = parseUTCDateTime(dateStr);
    if (!date || Number.isNaN(date.getTime())) {
        return '';
    }

    return date.toLocaleDateString(undefined, options);
}

/**
 * @param {string} dateStr
 * @param {Object} [options]
 * @returns {string}
 */
export function formatLocalDateTime(dateStr, options = {}) {
    const date = parseUTCDateTime(dateStr);
    if (!date || Number.isNaN(date.getTime())) {
        return '';
    }

    return date.toLocaleString(undefined, options);
}

/**
 * @param {string} startTime
 * @param {string} stopTime
 * @returns {string}
 */
export function formatProgramTimeRange(startTime, stopTime) {
    const start = formatLocalTime(startTime);
    const stop = formatLocalTime(stopTime);
    if (!start || !stop) {
        return '';
    }

    return `${start} - ${stop}`;
}

/**
 * @param {string} dateStr
 * @param {Date} [now]
 * @returns {string}
 */
export function formatRelativeTime(dateStr, now = new Date()) {
    const date = parseUTCDateTime(dateStr);
    if (!date || Number.isNaN(date.getTime())) {
        return '';
    }

    const diffMs = date - now;
    const diffSecs = Math.round(diffMs / 1000);
    const diffMins = Math.round(diffSecs / 60);
    const diffHours = Math.round(diffMins / 60);
    const diffDays = Math.round(diffHours / 24);

    if (typeof Intl !== 'undefined' && Intl.RelativeTimeFormat) {
        const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' });

        if (Math.abs(diffSecs) < 60) {
            return rtf.format(diffSecs, 'second');
        }
        if (Math.abs(diffMins) < 60) {
            return rtf.format(diffMins, 'minute');
        }
        if (Math.abs(diffHours) < 24) {
            return rtf.format(diffHours, 'hour');
        }

        return rtf.format(diffDays, 'day');
    }

    if (Math.abs(diffSecs) < 60) {
        return 'just now';
    }
    if (Math.abs(diffMins) < 60) {
        return diffMins > 0 ? `in ${diffMins} min` : `${-diffMins} min ago`;
    }
    if (Math.abs(diffHours) < 24) {
        return diffHours > 0 ? `in ${diffHours} hr` : `${-diffHours} hr ago`;
    }

    return diffDays > 0 ? `in ${diffDays} days` : `${-diffDays} days ago`;
}
