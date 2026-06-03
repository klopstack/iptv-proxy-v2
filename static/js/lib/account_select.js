/**
 * Shared account list fetch and select population for admin UI.
 */
import { escapeHtml } from './escape_html.js';

/**
 * @returns {Promise<Array<{ id: number|string, name?: string }>>}
 */
function unwrapAccountsPayload(response, payload) {
    if (payload !== null && typeof payload === 'object' && Object.prototype.hasOwnProperty.call(payload, 'data')) {
        return payload.data;
    }
    return payload;
}

export async function fetchAccounts() {
    const response = await fetch('/api/accounts');
    const payload = await response.json();
    const data = unwrapAccountsPayload(response, payload);

    if (!response.ok || !Array.isArray(data)) {
        const message = (payload && typeof payload === 'object' && payload.error) || 'Invalid accounts response';
        throw new Error(message);
    }

    return data;
}

/**
 * @param {HTMLElement} select
 * @param {Array<{ id: number|string, name?: string }>} accounts
 * @param {{ placeholder?: string, preserveFirstOption?: boolean }} [options]
 */
export function populateAccountSelect(select, accounts, options = {}) {
    const { placeholder = '', preserveFirstOption = false } = options;

    if (!select) {
        return;
    }

    const firstOption = preserveFirstOption && select.options.length > 0
        ? select.options[0].outerHTML
        : '';

    select.innerHTML = firstOption || (placeholder ? `<option value="">${escapeHtml(placeholder)}</option>` : '');

    for (const account of accounts) {
        const option = document.createElement('option');
        option.value = String(account.id);
        option.textContent = account.name || `Account ${account.id}`;
        select.appendChild(option);
    }
}

/**
 * Populate multiple selects with the same account list.
 * @param {string[]} selectIds
 * @param {Array<{ id: number|string, name?: string }>} accounts
 * @param {{ preserveFirstOption?: boolean }} [options]
 */
export function populateAccountSelects(selectIds, accounts, options = {}) {
    for (const id of selectIds) {
        const select = document.getElementById(id);
        if (select) {
            populateAccountSelect(select, accounts, options);
        }
    }
}
