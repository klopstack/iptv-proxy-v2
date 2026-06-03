/**
 * EPG match rulesets tab (ESM).
 */
import { escapeHtml } from '../lib/escape_html.js';
import { buildAssignedAccountsBadgeHtml } from '../lib/match_rules_rulesets_helpers.js';
const expandedRulesets = new Set();

async function loadRulesets(preserveExpanded = false) {
    if (preserveExpanded) {
        document.querySelectorAll('[id^="rules-"].show').forEach(el => {
            const id = el.id.replace('rules-', '');
            expandedRulesets.add(parseInt(id));
        });
    } else {
        expandedRulesets.clear();
    }
    
    try {
        const response = await fetch('/api/epg-match-rules/rulesets');
        const rulesets = await response.json();
        
        let html = '';
        
        if (rulesets.length === 0) {
            html = `
                <div class="alert alert-info">
                    <h5><i class="bi bi-info-circle"></i> No EPG Match Rulesets Found</h5>
                    <p>Create a default ruleset to get started with EPG matching.</p>
                </div>
            `;
        } else {
            rulesets.forEach(ruleset => {
                // Expand all rulesets by default if not preserving state
                if (!preserveExpanded && expandedRulesets.size === 0) {
                    expandedRulesets.add(ruleset.id);
                }
                
                const defaultBadge = ruleset.is_default ? '<span class="badge bg-primary ms-2">Default</span>' : '';
                const status = ruleset.enabled ? '<span class="badge bg-success">Enabled</span>' : '<span class="badge bg-secondary">Disabled</span>';
                const isExpanded = expandedRulesets.has(ruleset.id);
                
                const assignedAccountsBadges = buildAssignedAccountsBadgeHtml(ruleset.assigned_accounts);
                
                html += `
                    <div class="card mb-3">
                        <div class="card-header d-flex justify-content-between align-items-center">
                            <h5 class="mb-0">
                                ${escapeHtml(ruleset.name)} ${defaultBadge}${assignedAccountsBadges}
                                <small class="text-muted ms-2">(${ruleset.rule_count} rules, priority: ${ruleset.priority})</small>
                            </h5>
                            <div>
                                ${status}
                                <div class="btn-group ms-2">
                                    <button class="btn btn-sm btn-outline-primary" data-action="show-rules" data-ruleset-id="${ruleset.id}">
                                        <i class="bi bi-list"></i> Rules
                                    </button>
                                    <button class="btn btn-sm btn-outline-info" data-action="show-assign" data-ruleset-id="${ruleset.id}">
                                        <i class="bi bi-link"></i> Assign
                                    </button>
                                    <button class="btn btn-sm btn-outline-warning" data-action="duplicate" data-ruleset-id="${ruleset.id}" title="Duplicate ruleset">
                                        <i class="bi bi-copy"></i>
                                    </button>
                                    <button class="btn btn-sm btn-outline-secondary" data-action="edit" data-ruleset-id="${ruleset.id}">
                                        <i class="bi bi-pencil"></i>
                                    </button>
                                    <button class="btn btn-sm btn-outline-danger" data-action="delete" data-ruleset-id="${ruleset.id}">
                                        <i class="bi bi-trash"></i>
                                    </button>
                                </div>
                            </div>
                        </div>
                        ${ruleset.description ? `<div class="card-body"><p class="text-muted mb-0">${escapeHtml(ruleset.description)}</p></div>` : ''}
                        <div class="card-body collapse ${isExpanded ? 'show' : ''}" id="rules-${ruleset.id}">
                            <div class="d-flex justify-content-between align-items-center mb-3">
                                <h6>EPG Match Rules</h6>
                                <button class="btn btn-sm btn-success" data-action="create-rule" data-ruleset-id="${ruleset.id}">
                                    <i class="bi bi-plus"></i> Add Rule
                                </button>
                            </div>
                            <div id="rules-list-${ruleset.id}">
                                <div class="text-center py-3">
                                    <div class="spinner-border spinner-border-sm" role="status"></div>
                                </div>
                            </div>
                        </div>
                    </div>
                `;
            });
        }
        
        document.getElementById('rulesets-list').innerHTML = html;
        
        for (const rulesetId of expandedRulesets) {
            await loadRulesForRuleset(rulesetId);
        }
    } catch (error) {
        document.getElementById('rulesets-list').innerHTML = `
            <div class="alert alert-danger">Error loading rulesets: ${error.message}</div>
        `;
    }
}

async function loadRulesForRuleset(rulesetId) {
    try {
        const response = await fetch(`/api/epg-match-rules/rules?ruleset_id=${rulesetId}`);
        const rules = await response.json();
        
        let html = '';
        if (rules.length === 0) {
            html = '<div class="alert alert-warning">No rules in this ruleset</div>';
        } else {
            html = '<div class="table-responsive"><table class="table table-sm table-hover">';
            html += '<thead><tr><th>Priority</th><th>Name</th><th>Type</th><th>Source</th><th>Action</th><th>Status</th><th>Actions</th></tr></thead><tbody>';
            
            rules.forEach(rule => {
                const status = rule.enabled ? '<span class="badge bg-success">On</span>' : '<span class="badge bg-secondary">Off</span>';
                const stopIcon = rule.stop_on_match ? '<i class="bi bi-stop-circle text-warning" title="Stops processing on match"></i>' : '';
                
                html += `
                    <tr>
                        <td>${rule.priority}</td>
                        <td>${escapeHtml(rule.name)}</td>
                        <td><span class="badge bg-info">${rule.match_type}</span></td>
                        <td>${rule.source || '-'}</td>
                        <td><span class="badge bg-primary">${rule.action}</span></td>
                        <td>${status} ${stopIcon}</td>
                        <td>
                            <button class="btn btn-sm btn-outline-secondary" data-action="edit-rule" data-rule-id="${rule.id}">
                                <i class="bi bi-pencil"></i>
                            </button>
                            <button class="btn btn-sm btn-outline-danger" data-action="delete-rule" data-rule-id="${rule.id}" data-ruleset-id="${rulesetId}">
                                <i class="bi bi-trash"></i>
                            </button>
                        </td>
                    </tr>
                `;
            });
            
            html += '</tbody></table></div>';
        }
        
        document.getElementById(`rules-list-${rulesetId}`).innerHTML = html;
    } catch (error) {
        document.getElementById(`rules-list-${rulesetId}`).innerHTML = `
            <div class="alert alert-danger">Error loading rules: ${error.message}</div>
        `;
    }
}

async function showRulesetRules(rulesetId) {
    const rulesDiv = document.getElementById(`rules-${rulesetId}`);
    const isCurrentlyShown = rulesDiv.classList.contains('show');
    
    new bootstrap.Collapse(rulesDiv, { toggle: true });
    
    if (isCurrentlyShown) {
        expandedRulesets.delete(rulesetId);
        return;
    }
    
    expandedRulesets.add(rulesetId);
    await loadRulesForRuleset(rulesetId);
}

function showCreateRulesetModal() {
    document.getElementById('rulesetModalTitle').textContent = 'New EPG Match Ruleset';
    document.getElementById('rulesetForm').reset();
    document.getElementById('ruleset-id').value = '';
    document.getElementById('ruleset-enabled').checked = true;
    if (window.EpgManagementState.rulesetModal) window.EpgManagementState.rulesetModal.show();
}

async function editRuleset(rulesetId) {
    const response = await fetch(`/api/epg-match-rules/rulesets/${rulesetId}`);
    const ruleset = await response.json();
    
    document.getElementById('rulesetModalTitle').textContent = 'Edit EPG Match Ruleset';
    document.getElementById('ruleset-id').value = ruleset.id;
    document.getElementById('ruleset-name').value = ruleset.name;
    document.getElementById('ruleset-description').value = ruleset.description || '';
    document.getElementById('ruleset-priority').value = ruleset.priority;
    document.getElementById('ruleset-is-default').checked = ruleset.is_default;
    document.getElementById('ruleset-enabled').checked = ruleset.enabled;
    
    if (window.EpgManagementState.rulesetModal) window.EpgManagementState.rulesetModal.show();
}

async function saveRuleset() {
    const id = document.getElementById('ruleset-id').value;
    const data = {
        name: document.getElementById('ruleset-name').value,
        description: document.getElementById('ruleset-description').value,
        priority: parseInt(document.getElementById('ruleset-priority').value),
        is_default: document.getElementById('ruleset-is-default').checked,
        enabled: document.getElementById('ruleset-enabled').checked
    };
    
    try {
        const url = id ? `/api/epg-match-rules/rulesets/${id}` : '/api/epg-match-rules/rulesets';
        const method = id ? 'PUT' : 'POST';
        
        const response = await fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        
        if (response.ok) {
            bootstrap.Modal.getInstance(document.getElementById('rulesetModal')).hide();
            await loadRulesets(true);
        } else {
            const error = await response.json();
            alert('Error: ' + (error.error || 'Failed to save ruleset'));
        }
    } catch (error) {
        alert('Error saving ruleset: ' + error.message);
    }
}

async function deleteRuleset(rulesetId) {
    if (!confirm('Delete this ruleset and all its rules?')) return;
    
    try {
        const response = await fetch(`/api/epg-match-rules/rulesets/${rulesetId}`, { method: 'DELETE' });
        if (response.ok) {
            await loadRulesets();
        }
    } catch (error) {
        alert('Error deleting ruleset: ' + error.message);
    }
}

async function duplicateRuleset(rulesetId) {
    try {
        const response = await fetch(`/api/epg-match-rules/rulesets/${rulesetId}/duplicate`, { method: 'POST' });
        const result = await response.json();
        
        if (response.ok) {
            alert(result.message);
            await loadRulesets();
        } else {
            alert('Error: ' + (result.error || 'Failed to duplicate ruleset'));
        }
    } catch (error) {
        alert('Error duplicating ruleset: ' + error.message);
    }
}

async function createDefaultRuleset() {
    if (!confirm('Create default EPG match ruleset with standard matching rules?')) return;
    
    try {
        const response = await fetch('/api/epg-match-rules/create-default', { method: 'POST' });
        const result = await response.json();
        
        if (result.success) {
            alert(result.message);
            await loadRulesets();
        } else {
            alert('Error: ' + result.error);
        }
    } catch (error) {
        alert('Error creating default ruleset: ' + error.message);
    }
}

const matchRulesRulesetsExports = {
    loadRulesets,
    loadRulesForRuleset,
    showRulesetRules,
    showCreateRulesetModal,
    editRuleset,
    saveRuleset,
    deleteRuleset,
    duplicateRuleset,
    createDefaultRuleset,
};

Object.assign(window, matchRulesRulesetsExports);
export { matchRulesRulesetsExports };