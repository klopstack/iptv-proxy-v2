/**
 * Pure helpers for EPG match rulesets list UI.
 */

/**
 * @param {Array<{ name?: string }>} assignedAccounts
 * @returns {string}
 */
export function formatAssignedAccountsTitle(assignedAccounts) {
    return assignedAccounts.map((account) => account.name).join(', ');
}

/**
 * @param {Array<{ name?: string }>} assignedAccounts
 * @returns {string}
 */
export function buildAssignedAccountsBadgeHtml(assignedAccounts) {
    if (!assignedAccounts?.length) {
        return '';
    }

    const count = assignedAccounts.length;
    const plural = count > 1 ? 's' : '';
    const title = formatAssignedAccountsTitle(assignedAccounts);

    return `<span class="badge bg-info ms-2" title="Assigned to: ${title}"><i class="bi bi-person-check"></i> ${count} account${plural}</span>`;
}
