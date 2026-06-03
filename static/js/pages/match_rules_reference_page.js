/**
 * Match rules reference documentation and ruleset account assignment (ESM).
 */
import { escapeHtml } from '../lib/escape_html.js';
import { buildMatchRulesReferenceHtml } from '../lib/match_rules_reference_helpers.js';

async function loadReference() {
    try {
        const response = await fetch('/api/epg-match-rules/match-types');
        const data = await response.json();

        const container = document.getElementById('reference-content');
        if (!container) return;
        container.innerHTML = buildMatchRulesReferenceHtml(data);
    } catch (error) {
        const container = document.getElementById('reference-content');
        if (!container) return;
        container.innerHTML = `
            <div class="alert alert-danger">Error loading reference: ${escapeHtml(error.message)}</div>
        `;
    }
}

async function showAssignModal(rulesetId) {
    document.getElementById('assign-ruleset-id').value = rulesetId;

    const assignedAccountIds = new Set();
    for (const account of window.EpgManagementState.accounts) {
        try {
            const resp = await fetch(`/api/accounts/${account.id}/epg-match-rulesets`);
            const assignments = await resp.json();
            if (assignments.some((a) => a.ruleset_id === rulesetId)) {
                assignedAccountIds.add(account.id);
            }
        } catch (e) {
            console.error('Error checking assignments:', e);
        }
    }

    let html = '<div class="list-group">';
    window.EpgManagementState.accounts.forEach((account) => {
        const isAssigned = assignedAccountIds.has(account.id);
        html += `
            <div class="list-group-item d-flex justify-content-between align-items-center">
                <span>${escapeHtml(account.name)}</span>
                <button class="btn btn-sm ${isAssigned ? 'btn-danger' : 'btn-success'}" 
                        data-action="toggle-assign" 
                        data-account-id="${account.id}" 
                        data-assigned="${isAssigned}">
                    ${isAssigned ? '<i class="bi bi-x"></i> Remove' : '<i class="bi bi-plus"></i> Assign'}
                </button>
            </div>
        `;
    });
    html += '</div>';

    const container = document.getElementById('accounts-assign-list');
    if (!container) return;
    container.innerHTML = html;
    if (window.EpgManagementState.assignModal) window.EpgManagementState.assignModal.show();
}

async function toggleAssignment(accountId, isCurrentlyAssigned) {
    const rulesetId = document.getElementById('assign-ruleset-id').value;

    try {
        if (isCurrentlyAssigned) {
            await fetch(`/api/accounts/${accountId}/epg-match-rulesets/${rulesetId}`, { method: 'DELETE' });
        } else {
            await fetch(`/api/accounts/${accountId}/epg-match-rulesets`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ruleset_id: parseInt(rulesetId, 10), priority: 100 }),
            });
        }

        await showAssignModal(parseInt(rulesetId, 10));
        await loadRulesets(true);
    } catch (error) {
        alert('Error updating assignment: ' + error.message);
    }
}

const matchRulesReferenceExports = {
    loadReference,
    showAssignModal,
    toggleAssignment,
};

Object.assign(window, matchRulesReferenceExports);
export { matchRulesReferenceExports };
