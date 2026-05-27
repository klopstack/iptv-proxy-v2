/**
 * Shared EPG sync progress rendering (settings + EPG sources page).
 */

export const PHASE_LABEL = {
    idle: 'Idle',
    queued: 'Queued',
    fetching: 'Fetching',
    channels: 'Channels',
    programs: 'Programmes',
    complete: 'Complete',
    error: 'Error',
    skipped: 'Skipped',
};

const ACTIVE_PHASES = new Set(['queued', 'fetching', 'channels', 'programs']);

export function escapeHtml(text) {
    if (text == null) return '';
    return String(text)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

/**
 * @param {object} src - Row from GET /api/sync/epg/status
 * @returns {string}
 */
export function formatProgressDetail(src) {
    const prog = src.progress || {};
    let detail = prog.message || src.last_sync_message || '';

    if (prog.programmes_parsed != null) {
        const total = prog.programmes_total_estimate ? ` / ~${prog.programmes_total_estimate}` : '';
        detail = `Parsed ${prog.programmes_parsed}${total} programmes`;
        if (prog.programs_added != null) {
            detail += ` · +${prog.programs_added} added`;
        }
    }

    if (src.due && !src.sync_in_progress && (src.sync_phase || 'idle') === 'idle') {
        detail = (detail ? `${detail} · ` : '') + 'Due';
    }

    return detail;
}

/**
 * @param {object} src
 * @returns {string} Bootstrap badge class suffix (bg-*)
 */
export function getPhaseBadgeClass(src) {
    const phase = src.sync_phase || 'idle';
    if (src.sync_in_progress || ACTIVE_PHASES.has(phase)) {
        return 'bg-primary';
    }
    if (phase === 'error') {
        return 'bg-danger';
    }
    if (phase === 'complete') {
        return 'bg-success';
    }
    if (phase === 'skipped') {
        return 'bg-secondary';
    }
    return 'bg-secondary';
}

/**
 * @param {object} src
 * @returns {boolean}
 */
export function isLiveSyncStatus(src) {
    if (!src) return false;
    const phase = src.sync_phase || 'idle';
    return Boolean(src.sync_in_progress) || ACTIVE_PHASES.has(phase);
}

/**
 * @param {Array<object>} sources
 * @returns {Record<number, object>}
 */
export function indexSourcesById(sources) {
    const map = {};
    for (const src of sources || []) {
        map[src.source_id] = src;
    }
    return map;
}

/**
 * HTML for inline status on the EPG sources table.
 * @param {object} live - Status snapshot from /api/sync/epg/status
 * @returns {string}
 */
export function renderSourceRowStatusHtml(live) {
    if (!live) return '';

    const phase = live.sync_phase || 'idle';
    const badgeClass = getPhaseBadgeClass(live);
    const label = PHASE_LABEL[phase] || phase;
    const detail = formatProgressDetail(live);
    const spinner = live.sync_in_progress
        ? '<span class="spinner-border spinner-border-sm ms-1" role="status" aria-hidden="true"></span>'
        : '';

    let html = `<span class="badge ${badgeClass}">${escapeHtml(label)}</span>${spinner}`;
    if (detail) {
        html += `<div class="small text-muted mt-1">${escapeHtml(detail)}</div>`;
    }
    return html;
}

/**
 * @param {HTMLElement} container
 * @param {Array<object>} sources
 * @param {(iso: string) => string} formatRelativeTime
 */
export function renderEpgSourcesProgressTable(container, sources, formatRelativeTime) {
    if (!container) return;

    if (!sources || !sources.length) {
        container.innerHTML = '<p class="text-muted small mb-0">No EPG sources configured.</p>';
        return;
    }

    let html = '<div class="table-responsive"><table class="table table-sm table-striped mb-0">';
    html += '<thead><tr><th>Source</th><th>Status</th><th>Progress</th><th>Last sync</th></tr></thead><tbody>';

    for (const src of sources) {
        const phase = src.sync_phase || 'idle';
        const badgeClass = getPhaseBadgeClass(src);
        const lastSync = src.last_sync ? formatRelativeTime(src.last_sync) : 'Never';
        let detail = formatProgressDetail(src);
        if (detail === 'Due') {
            detail = '<span class="text-warning">Due</span>';
        } else {
            detail = escapeHtml(detail) || '—';
        }

        html += `<tr>
            <td><strong>${escapeHtml(src.source_name)}</strong><br><span class="text-muted">${escapeHtml(src.source_type)}</span></td>
            <td><span class="badge ${badgeClass}">${PHASE_LABEL[phase] || phase}</span></td>
            <td class="small">${detail}</td>
            <td class="small">${escapeHtml(lastSync)}</td>
        </tr>`;
    }

    html += '</tbody></table></div>';
    container.innerHTML = html;
}
