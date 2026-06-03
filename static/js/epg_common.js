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
// Implemented in static/js/lib/epg_datetime.js and exposed on window
// via the EPG lib module shim in epg_management.html.

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

// escapeHtml: canonical implementation in static/js/lib/escape_html.js (window bridge)

/** Escape a string embedded in a single-quoted JS literal inside an HTML onclick attribute. */
function escapeJsSingleQuoted(text) {
    return String(text ?? '').replace(/\\/g, '\\\\').replace(/'/g, "\\'");
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
