// ============================================================================
// Exclusion Patterns
// ============================================================================

async function loadExclusions() {
    try {
        const response = await fetch('/api/epg-match-rules/exclusions');
        const exclusions = await response.json();
        
        let html = '';
        
        if (exclusions.length === 0) {
            html = `
                <div class="alert alert-info">
                    <h5><i class="bi bi-info-circle"></i> No Exclusion Patterns</h5>
                    <p>Create exclusion patterns to prevent specific channels from being matched to EPG data.</p>
                </div>
            `;
        } else {
            html = '<div class="table-responsive"><table class="table table-striped">';
            html += '<thead><tr><th>Priority</th><th>Name</th><th>Type</th><th>Pattern</th><th>Hide</th><th>Status</th><th>Actions</th></tr></thead><tbody>';
            
            exclusions.forEach(p => {
                const status = p.enabled ? '<span class="badge bg-success">Enabled</span>' : '<span class="badge bg-secondary">Disabled</span>';
                const hideIcon = p.hide_channel ? '<i class="bi bi-eye-slash text-warning" title="Hides channel"></i>' : '';
                const regexBadge = p.is_regex ? '<span class="badge bg-secondary">regex</span>' : '<span class="badge bg-light text-dark">literal</span>';
                
                html += `
                    <tr>
                        <td>${p.priority}</td>
                        <td>${escapeHtml(p.name)}</td>
                        <td><span class="badge bg-info">${p.pattern_type}</span></td>
                        <td><code>${escapeHtml(p.pattern)}</code> ${regexBadge}</td>
                        <td>${hideIcon}</td>
                        <td>${status}</td>
                        <td>
                            <button class="btn btn-sm btn-outline-secondary" data-action="edit-exclusion" data-exclusion-id="${p.id}">
                                <i class="bi bi-pencil"></i>
                            </button>
                            <button class="btn btn-sm btn-outline-danger" data-action="delete-exclusion" data-exclusion-id="${p.id}">
                                <i class="bi bi-trash"></i>
                            </button>
                        </td>
                    </tr>
                `;
            });
            
            html += '</tbody></table></div>';
        }
        
        document.getElementById('exclusions-list').innerHTML = html;
    } catch (error) {
        document.getElementById('exclusions-list').innerHTML = `
            <div class="alert alert-danger">Error loading exclusions: ${error.message}</div>
        `;
    }
}

function showCreateExclusionModal() {
    document.getElementById('exclusionModalTitle').textContent = 'New Exclusion Pattern';
    document.getElementById('exclusionForm').reset();
    document.getElementById('exclusion-id').value = '';
    document.getElementById('exclusion-case-sensitive').checked = false;
    document.getElementById('exclusion-enabled').checked = true;
    
    populateExclusionAccountDropdown();
    resetExclusionPreview();
    
    if (exclusionModal) exclusionModal.show();
}

async function editExclusion(exclusionId) {
    const response = await fetch(`/api/epg-match-rules/exclusions/${exclusionId}`);
    const exclusion = await response.json();
    
    document.getElementById('exclusionModalTitle').textContent = 'Edit Exclusion Pattern';
    document.getElementById('exclusion-id').value = exclusion.id;
    document.getElementById('exclusion-name').value = exclusion.name;
    document.getElementById('exclusion-description').value = exclusion.description || '';
    document.getElementById('exclusion-pattern-type').value = exclusion.pattern_type;
    document.getElementById('exclusion-pattern').value = exclusion.pattern;
    document.getElementById('exclusion-case-sensitive').checked = !exclusion.is_regex;
    document.getElementById('exclusion-enabled').checked = exclusion.enabled;
    document.getElementById('exclusion-priority').value = exclusion.priority;
    
    populateExclusionAccountDropdown();
    resetExclusionPreview();
    
    if (exclusionModal) exclusionModal.show();
}

async function saveExclusion() {
    const id = document.getElementById('exclusion-id').value;
    const data = {
        name: document.getElementById('exclusion-name').value,
        description: document.getElementById('exclusion-description').value,
        pattern_type: document.getElementById('exclusion-pattern-type').value,
        pattern: document.getElementById('exclusion-pattern').value,
        is_regex: !document.getElementById('exclusion-case-sensitive').checked,
        enabled: document.getElementById('exclusion-enabled').checked,
        priority: parseInt(document.getElementById('exclusion-priority').value)
    };
    
    try {
        const url = id ? `/api/epg-match-rules/exclusions/${id}` : '/api/epg-match-rules/exclusions';
        const method = id ? 'PUT' : 'POST';
        
        const response = await fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        
        if (response.ok) {
            bootstrap.Modal.getInstance(document.getElementById('exclusionModal')).hide();
            await loadExclusions();
        } else {
            const error = await response.json();
            alert('Error: ' + (error.error || 'Failed to save exclusion'));
        }
    } catch (error) {
        alert('Error saving exclusion: ' + error.message);
    }
}

async function deleteExclusion(exclusionId) {
    if (!confirm('Delete this exclusion pattern?')) return;
    
    try {
        const response = await fetch(`/api/epg-match-rules/exclusions/${exclusionId}`, { method: 'DELETE' });
        if (response.ok) {
            await loadExclusions();
        }
    } catch (error) {
        alert('Error deleting exclusion: ' + error.message);
    }
}

async function createDefaultExclusions() {
    if (!confirm('Create default exclusion patterns for PPV and event channels?')) return;
    
    try {
        const response = await fetch('/api/epg-match-rules/create-default-exclusions', { method: 'POST' });
        const result = await response.json();
        
        if (result.success) {
            alert(result.message);
            new bootstrap.Tab(document.getElementById('exclusions-tab')).show();
            await loadExclusions();
        } else {
            alert('Error: ' + result.error);
        }
    } catch (error) {
        alert('Error creating default exclusions: ' + error.message);
    }
}

async function previewExclusionPattern() {
    const pattern = document.getElementById('exclusion-pattern').value;
    const patternType = document.getElementById('exclusion-pattern-type').value;
    const isRegex = document.getElementById('exclusion-is-regex').checked;
    const accountId = document.getElementById('exclusion-account-filter').value;
    
    if (!pattern) {
        document.getElementById('exclusion-preview-results').style.display = 'block';
        document.getElementById('exclusion-preview-error').style.display = 'block';
        document.getElementById('exclusion-preview-error').textContent = 'Please enter a pattern to preview';
        document.getElementById('exclusion-preview-content').style.display = 'none';
        return;
    }
    
    document.getElementById('exclusion-preview-results').style.display = 'block';
    document.getElementById('exclusion-preview-loading').style.display = 'block';
    document.getElementById('exclusion-preview-error').style.display = 'none';
    document.getElementById('exclusion-preview-content').style.display = 'none';
    
    try {
        const response = await fetch('/api/epg-match-rules/exclusions/preview', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                pattern_type: patternType,
                pattern: pattern,
                is_regex: isRegex,
                account_id: accountId || null
            })
        });
        
        const data = await response.json();
        
        document.getElementById('exclusion-preview-loading').style.display = 'none';
        
        if (data.error) {
            document.getElementById('exclusion-preview-error').style.display = 'block';
            document.getElementById('exclusion-preview-error').textContent = data.error;
            document.getElementById('exclusion-preview-content').style.display = 'none';
        } else {
            document.getElementById('exclusion-preview-content').style.display = 'block';
            document.getElementById('exclusion-preview-count').textContent = data.total_count;
            document.getElementById('exclusion-preview-more').style.display = data.total_count > 100 ? 'inline' : 'none';
            
            let html = '';
            if (data.matches.length === 0) {
                html = '<p class="text-muted mb-0">No channels match this pattern</p>';
            } else {
                html = '<ul class="list-unstyled mb-0">';
                data.matches.forEach(match => {
                    const name = escapeHtml(match.cleaned_name || match.name);
                    const category = match.category ? `<small class="text-muted"> (${escapeHtml(match.category)})</small>` : '';
                    html += `<li class="mb-1"><code>${name}</code>${category}</li>`;
                });
                html += '</ul>';
            }
            document.getElementById('exclusion-preview-list').innerHTML = html;
        }
    } catch (error) {
        document.getElementById('exclusion-preview-loading').style.display = 'none';
        document.getElementById('exclusion-preview-error').style.display = 'block';
        document.getElementById('exclusion-preview-error').textContent = 'Error: ' + error.message;
        document.getElementById('exclusion-preview-content').style.display = 'none';
    }
}
