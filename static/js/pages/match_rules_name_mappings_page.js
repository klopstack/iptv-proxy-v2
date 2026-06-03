/**
 * EPG match rule channel name mappings (ESM).
 */
import { escapeHtml } from '../lib/escape_html.js';
import { validateNameMappingPreviewInput } from '../lib/match_rules_helpers.js';

async function loadNameMappings() {
    try {
        const response = await fetch('/api/epg-match-rules/name-mappings');
        const mappings = await response.json();

        let html = '';

        if (mappings.length === 0) {
            html = `
                <div class="alert alert-info">
                    <h5><i class="bi bi-info-circle"></i> No Name Mappings</h5>
                    <p>Create name mappings to transform legacy channel names for EPG matching (e.g., "Bally Sports" → "FanDuel Sports Network").</p>
                </div>
            `;
        } else {
            html = '<div class="table-responsive"><table class="table table-striped">';
            html += '<thead><tr><th>Priority</th><th>Name</th><th>Match Type</th><th>Old Name</th><th>New Name</th><th>Status</th><th>Actions</th></tr></thead><tbody>';

            mappings.forEach((m) => {
                const status = m.enabled ? '<span class="badge bg-success">Enabled</span>' : '<span class="badge bg-secondary">Disabled</span>';
                const caseIcon = m.case_sensitive ? '<i class="bi bi-text-left text-info" title="Case sensitive"></i>' : '';

                html += `
                    <tr>
                        <td>${m.priority}</td>
                        <td>${escapeHtml(m.name)}</td>
                        <td><span class="badge bg-info">${m.match_type}</span> ${caseIcon}</td>
                        <td><code>${escapeHtml(m.old_name)}</code></td>
                        <td><code>${escapeHtml(m.new_name)}</code></td>
                        <td>${status}</td>
                        <td>
                            <button class="btn btn-sm btn-outline-secondary" data-action="edit-name-mapping" data-mapping-id="${m.id}">
                                <i class="bi bi-pencil"></i>
                            </button>
                            <button class="btn btn-sm btn-outline-danger" data-action="delete-name-mapping" data-mapping-id="${m.id}">
                                <i class="bi bi-trash"></i>
                            </button>
                        </td>
                    </tr>
                `;
            });

            html += '</tbody></table></div>';
        }

        document.getElementById('name-mappings-list').innerHTML = html;
    } catch (error) {
        document.getElementById('name-mappings-list').innerHTML = `
            <div class="alert alert-danger">Error loading name mappings: ${escapeHtml(error.message)}</div>
        `;
    }
}

function showCreateNameMappingModal() {
    document.getElementById('nameMappingModalTitle').textContent = 'New Channel Name Mapping';
    document.getElementById('nameMappingForm').reset();
    document.getElementById('name-mapping-id').value = '';
    document.getElementById('name-mapping-enabled').checked = true;
    document.getElementById('name-mapping-case-sensitive').checked = false;

    populateNameMappingAccountDropdown();
    resetNameMappingPreview();

    if (window.EpgManagementState.nameMappingModal) window.EpgManagementState.nameMappingModal.show();
}

async function editNameMapping(mappingId) {
    const response = await fetch(`/api/epg-match-rules/name-mappings/${mappingId}`);
    const mapping = await response.json();

    document.getElementById('nameMappingModalTitle').textContent = 'Edit Channel Name Mapping';
    document.getElementById('name-mapping-id').value = mapping.id;
    document.getElementById('name-mapping-name').value = mapping.name;
    document.getElementById('name-mapping-description').value = mapping.description || '';
    document.getElementById('name-mapping-old-name').value = mapping.old_name;
    document.getElementById('name-mapping-new-name').value = mapping.new_name;
    document.getElementById('name-mapping-match-type').value = mapping.match_type;
    document.getElementById('name-mapping-case-sensitive').checked = mapping.case_sensitive;
    document.getElementById('name-mapping-priority').value = mapping.priority;
    document.getElementById('name-mapping-enabled').checked = mapping.enabled;

    populateNameMappingAccountDropdown();
    resetNameMappingPreview();

    if (window.EpgManagementState.nameMappingModal) window.EpgManagementState.nameMappingModal.show();
}

async function saveNameMapping() {
    const id = document.getElementById('name-mapping-id').value;

    const data = {
        name: document.getElementById('name-mapping-name').value,
        description: document.getElementById('name-mapping-description').value,
        old_name: document.getElementById('name-mapping-old-name').value,
        new_name: document.getElementById('name-mapping-new-name').value,
        match_type: document.getElementById('name-mapping-match-type').value,
        case_sensitive: document.getElementById('name-mapping-case-sensitive').checked,
        priority: parseInt(document.getElementById('name-mapping-priority').value, 10),
        enabled: document.getElementById('name-mapping-enabled').checked,
    };

    try {
        const url = id ? `/api/epg-match-rules/name-mappings/${id}` : '/api/epg-match-rules/name-mappings';
        const method = id ? 'PUT' : 'POST';

        const response = await fetch(url, {
            method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });

        if (response.ok) {
            bootstrap.Modal.getInstance(document.getElementById('nameMappingModal')).hide();
            await loadNameMappings();
        } else {
            const error = await response.json();
            alert('Error: ' + (error.error || error.validation_errors || 'Failed to save name mapping'));
        }
    } catch (error) {
        alert('Error saving name mapping: ' + error.message);
    }
}

async function deleteNameMapping(mappingId) {
    if (!confirm('Delete this name mapping?')) return;

    try {
        const response = await fetch(`/api/epg-match-rules/name-mappings/${mappingId}`, { method: 'DELETE' });
        if (response.ok) {
            await loadNameMappings();
        }
    } catch (error) {
        alert('Error deleting name mapping: ' + error.message);
    }
}

function populateNameMappingAccountDropdown() {
    const select = document.getElementById('name-mapping-account-filter');
    select.innerHTML = '<option value="">All accounts</option>';
    window.EpgManagementState.accounts.forEach((account) => {
        select.innerHTML += `<option value="${account.id}">${escapeHtml(account.name)}</option>`;
    });
}

function resetNameMappingPreview() {
    document.getElementById('name-mapping-preview-results').style.display = 'none';
    document.getElementById('name-mapping-preview-error').style.display = 'none';
    document.getElementById('name-mapping-preview-loading').style.display = 'none';
    document.getElementById('name-mapping-preview-list').innerHTML = '';
    document.getElementById('name-mapping-preview-count').textContent = '0';
    document.getElementById('name-mapping-preview-more').style.display = 'none';
}

async function previewNameMapping() {
    const oldName = document.getElementById('name-mapping-old-name').value;
    const newName = document.getElementById('name-mapping-new-name').value;
    const matchType = document.getElementById('name-mapping-match-type').value;
    const caseSensitive = document.getElementById('name-mapping-case-sensitive').checked;
    const accountId = document.getElementById('name-mapping-account-filter').value;

    const previewError = validateNameMappingPreviewInput(oldName);

    if (previewError) {
        document.getElementById('name-mapping-preview-results').style.display = 'block';
        document.getElementById('name-mapping-preview-error').style.display = 'block';
        document.getElementById('name-mapping-preview-error').textContent = previewError;
        document.getElementById('name-mapping-preview-content').style.display = 'none';
        return;
    }

    document.getElementById('name-mapping-preview-results').style.display = 'block';
    document.getElementById('name-mapping-preview-loading').style.display = 'block';
    document.getElementById('name-mapping-preview-error').style.display = 'none';
    document.getElementById('name-mapping-preview-content').style.display = 'none';

    try {
        const response = await fetch('/api/epg-match-rules/name-mappings/preview', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                old_name: oldName,
                new_name: newName || '(removed)',
                match_type: matchType,
                case_sensitive: caseSensitive,
                account_id: accountId || null,
            }),
        });

        const data = await response.json();

        document.getElementById('name-mapping-preview-loading').style.display = 'none';

        if (data.error) {
            document.getElementById('name-mapping-preview-error').style.display = 'block';
            document.getElementById('name-mapping-preview-error').textContent = data.error;
            document.getElementById('name-mapping-preview-content').style.display = 'none';
        } else {
            document.getElementById('name-mapping-preview-content').style.display = 'block';
            document.getElementById('name-mapping-preview-count').textContent = data.total_count;
            document.getElementById('name-mapping-preview-more').style.display = data.total_count > 100 ? 'inline' : 'none';

            let html = '';
            if (data.matches.length === 0) {
                html = '<p class="text-muted mb-0">No channels match this pattern</p>';
            } else {
                html = '<ul class="list-unstyled mb-0">';
                data.matches.forEach((match) => {
                    const original = escapeHtml(match.original_name);
                    const transformed = escapeHtml(match.transformed_name);
                    html += `<li class="mb-1"><code>${original}</code> → <code class="text-success">${transformed}</code></li>`;
                });
                html += '</ul>';
            }
            document.getElementById('name-mapping-preview-list').innerHTML = html;
        }
    } catch (error) {
        document.getElementById('name-mapping-preview-loading').style.display = 'none';
        document.getElementById('name-mapping-preview-error').style.display = 'block';
        document.getElementById('name-mapping-preview-error').textContent = 'Error: ' + error.message;
        document.getElementById('name-mapping-preview-content').style.display = 'none';
    }
}

const matchRulesNameMappingsExports = {
    loadNameMappings,
    showCreateNameMappingModal,
    editNameMapping,
    saveNameMapping,
    deleteNameMapping,
    previewNameMapping,
};

Object.assign(window, matchRulesNameMappingsExports);
export { matchRulesNameMappingsExports };
