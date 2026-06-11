/**
 * URL builders and fetch helpers for account API sub-resources.
 * Use these instead of hand-built paths on PUT /api/accounts/{id} for fields
 * that have dedicated endpoints (ppv_visibility, credentials, xmltv EPG, etc.).
 */

/**
 * @param {number|string} accountId
 * @param {string} [suffix] Path after account id, e.g. "ppv-visibility" or "credentials/3"
 * @returns {string}
 */
export function accountPath(accountId, suffix = '') {
    const base = `/api/accounts/${accountId}`;
    if (!suffix) {
        return base;
    }
    return `${base}/${suffix.replace(/^\//, '')}`;
}

/** @returns {string} */
export function ppvVisibilityOptionsUrl() {
    return '/api/ppv-visibility-options';
}

/**
 * @param {number|string} accountId
 * @returns {string}
 */
export function accountPpvVisibilityUrl(accountId) {
    return accountPath(accountId, 'ppv-visibility');
}

/**
 * @param {number|string} accountId
 * @param {{ sync?: boolean }} [options]
 * @returns {string}
 */
export function accountXmltvEpgSourceUrl(accountId, { sync = false } = {}) {
    const url = accountPath(accountId, 'xmltv-epg-source');
    return sync ? `${url}?sync=true` : url;
}

/**
 * @param {number|string} accountId
 * @param {number|string|null} [credId]
 * @returns {string}
 */
export function accountCredentialsUrl(accountId, credId = null) {
    if (credId !== null && credId !== undefined && credId !== '') {
        return accountPath(accountId, `credentials/${credId}`);
    }
    return accountPath(accountId, 'credentials');
}

/**
 * @returns {Promise<Array<{ value: string, label: string, description?: string }>>}
 */
export async function fetchPpvVisibilityOptions() {
    const response = await fetch(ppvVisibilityOptionsUrl());
    if (!response.ok) {
        throw new Error('Failed to load PPV visibility options');
    }
    const data = await response.json();
    return Object.values(data);
}

/**
 * @param {number|string} accountId
 * @param {string} ppvVisibility
 * @param {{ ppv_show_replay?: boolean, ppv_show_historical?: boolean, ppv_show_unmatched_live?: boolean }} [options]
 * @returns {Promise<{ id: number, ppv_visibility: string, ppv_show_replay?: boolean, ppv_show_historical?: boolean, ppv_show_unmatched_live?: boolean }>}
 */
export async function updateAccountPpvVisibility(accountId, ppvVisibility, options = {}) {
    const body = { ppv_visibility: ppvVisibility, ...options };
    const response = await fetch(accountPpvVisibilityUrl(accountId), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });

    if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.error || 'Failed to update PPV visibility');
    }

    return response.json();
}
