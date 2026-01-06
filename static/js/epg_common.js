// ============================================================================
// EPG Common Utilities
// ============================================================================

// Global state shared across EPG modules
let accounts = [];
let sources = [];
let matchTypes = [];

// ============================================================================
// Time Formatting Utilities
// ============================================================================

/**
 * Parse a datetime string and ensure it's treated as UTC.
 * Handles both ISO strings with 'Z' suffix and those without.
 * @param {string} dateStr - ISO datetime string
 * @returns {Date} - JavaScript Date object
 */
function parseUTCDateTime(dateStr) {
    if (!dateStr) return null;
    // If it doesn't end with Z or timezone offset, treat as UTC
    if (!dateStr.endsWith('Z') && !dateStr.match(/[+-]\d{2}:\d{2}$/)) {
        dateStr = dateStr + 'Z';
    }
    return new Date(dateStr);
}

/**
 * Format a datetime string to local time display.
 * @param {string} dateStr - ISO datetime string (UTC)
 * @param {Object} options - Intl.DateTimeFormat options
 * @returns {string} - Formatted local time string
 */
function formatLocalTime(dateStr, options = {}) {
    const date = parseUTCDateTime(dateStr);
    if (!date || isNaN(date.getTime())) return '';
    
    const defaultOptions = {
        hour: 'numeric',
        minute: '2-digit',
    };
    return date.toLocaleTimeString(undefined, { ...defaultOptions, ...options });
}

/**
 * Format a datetime string to local date display.
 * @param {string} dateStr - ISO datetime string (UTC)
 * @param {Object} options - Intl.DateTimeFormat options
 * @returns {string} - Formatted local date string
 */
function formatLocalDate(dateStr, options = {}) {
    const date = parseUTCDateTime(dateStr);
    if (!date || isNaN(date.getTime())) return '';
    
    return date.toLocaleDateString(undefined, options);
}

/**
 * Format a datetime string to local date and time display.
 * @param {string} dateStr - ISO datetime string (UTC)
 * @param {Object} options - Intl.DateTimeFormat options
 * @returns {string} - Formatted local datetime string
 */
function formatLocalDateTime(dateStr, options = {}) {
    const date = parseUTCDateTime(dateStr);
    if (!date || isNaN(date.getTime())) return '';
    
    return date.toLocaleString(undefined, options);
}

/**
 * Format a program time range (start - stop) in local time.
 * @param {string} startTime - ISO datetime string for start (UTC)
 * @param {string} stopTime - ISO datetime string for stop (UTC)
 * @returns {string} - Formatted time range like "7:00 PM - 8:30 PM"
 */
function formatProgramTimeRange(startTime, stopTime) {
    const start = formatLocalTime(startTime);
    const stop = formatLocalTime(stopTime);
    if (!start || !stop) return '';
    return `${start} - ${stop}`;
}

/**
 * Format a relative time string (e.g., "2 hours ago", "in 5 minutes").
 * @param {string} dateStr - ISO datetime string (UTC)
 * @returns {string} - Relative time string
 */
function formatRelativeTime(dateStr) {
    const date = parseUTCDateTime(dateStr);
    if (!date || isNaN(date.getTime())) return '';
    
    const now = new Date();
    const diffMs = date - now;
    const diffSecs = Math.round(diffMs / 1000);
    const diffMins = Math.round(diffSecs / 60);
    const diffHours = Math.round(diffMins / 60);
    const diffDays = Math.round(diffHours / 24);
    
    // Use Intl.RelativeTimeFormat if available
    if (typeof Intl !== 'undefined' && Intl.RelativeTimeFormat) {
        const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' });
        
        if (Math.abs(diffSecs) < 60) {
            return rtf.format(diffSecs, 'second');
        } else if (Math.abs(diffMins) < 60) {
            return rtf.format(diffMins, 'minute');
        } else if (Math.abs(diffHours) < 24) {
            return rtf.format(diffHours, 'hour');
        } else {
            return rtf.format(diffDays, 'day');
        }
    }
    
    // Fallback for older browsers
    if (Math.abs(diffSecs) < 60) {
        return diffSecs >= 0 ? 'just now' : 'just now';
    } else if (Math.abs(diffMins) < 60) {
        return diffMins > 0 ? `in ${diffMins} min` : `${-diffMins} min ago`;
    } else if (Math.abs(diffHours) < 24) {
        return diffHours > 0 ? `in ${diffHours} hr` : `${-diffHours} hr ago`;
    } else {
        return diffDays > 0 ? `in ${diffDays} days` : `${-diffDays} days ago`;
    }
}

// Bootstrap modals (initialized on DOM ready)
let sourceModal;
let searchLineupModal;
let manualMappingModal;
let sdStationsModal;
let sourceMappingsModal;
let rulesetModal;
let ruleModal;
let exclusionModal;
let assignModal;
let nameMappingModal;

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(this, args), wait);
    };
}

function showToast(message, type = 'success') {
    // Create toast container if it doesn't exist
    let toastContainer = document.querySelector('.toast-container');
    if (!toastContainer) {
        toastContainer = document.createElement('div');
        toastContainer.className = 'toast-container position-fixed bottom-0 end-0 p-3';
        toastContainer.style.zIndex = '1050';
        document.body.appendChild(toastContainer);
    }
    
    const toastId = 'toast-' + Date.now();
    const bgClass = type === 'success' ? 'bg-success' : type === 'error' ? 'bg-danger' : 'bg-info';
    
    const toastHtml = `
        <div id="${toastId}" class="toast align-items-center text-white ${bgClass} border-0" role="alert">
            <div class="d-flex">
                <div class="toast-body">${message}</div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
            </div>
        </div>
    `;
    
    toastContainer.insertAdjacentHTML('beforeend', toastHtml);
    const toastElement = document.getElementById(toastId);
    const toast = new bootstrap.Toast(toastElement);
    toast.show();
    
    // Remove from DOM after hidden
    toastElement.addEventListener('hidden.bs.toast', () => toastElement.remove());
}

// Initialize Bootstrap modals after DOM is ready
function initializeBootstrapModals() {
    // Safely initialize each modal only if the element exists
    try {
        if (document.getElementById('sourceModal')) sourceModal = new bootstrap.Modal(document.getElementById('sourceModal'));
        if (document.getElementById('searchLineupModal')) searchLineupModal = new bootstrap.Modal(document.getElementById('searchLineupModal'));
        if (document.getElementById('manualMappingModal')) manualMappingModal = new bootstrap.Modal(document.getElementById('manualMappingModal'));
        if (document.getElementById('sdStationsModal')) sdStationsModal = new bootstrap.Modal(document.getElementById('sdStationsModal'));
        if (document.getElementById('sourceMappingsModal')) sourceMappingsModal = new bootstrap.Modal(document.getElementById('sourceMappingsModal'));
        if (document.getElementById('rulesetModal')) rulesetModal = new bootstrap.Modal(document.getElementById('rulesetModal'));
        if (document.getElementById('ruleModal')) ruleModal = new bootstrap.Modal(document.getElementById('ruleModal'));
        if (document.getElementById('exclusionModal')) exclusionModal = new bootstrap.Modal(document.getElementById('exclusionModal'));
        if (document.getElementById('assignModal')) assignModal = new bootstrap.Modal(document.getElementById('assignModal'));
        if (document.getElementById('nameMappingModal')) nameMappingModal = new bootstrap.Modal(document.getElementById('nameMappingModal'));
    } catch (error) {
        console.warn('Some modal elements were not found:', error.message);
    }
}
