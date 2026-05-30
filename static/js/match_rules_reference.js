// ============================================================================
// Match Rules Reference and Account Assignment
// ============================================================================

async function loadReference() {
    try {
        const response = await fetch('/api/epg-match-rules/match-types');
        const data = await response.json();
        
        let html = '<div class="row">';
        
        html += '<div class="col-md-4 mb-4">';
        html += '<div class="card h-100"><div class="card-header"><h5 class="mb-0">Match Types</h5></div>';
        html += '<div class="card-body"><dl>';
        data.match_types.forEach(t => {
            html += `<dt><code>${t.value}</code></dt><dd class="mb-3">${t.description}</dd>`;
        });
        html += '</dl></div></div></div>';
        
        html += '<div class="col-md-4 mb-4">';
        html += '<div class="card h-100"><div class="card-header"><h5 class="mb-0">Actions</h5></div>';
        html += '<div class="card-body"><dl>';
        data.actions.forEach(a => {
            html += `<dt><code>${a.value}</code></dt><dd class="mb-3">${a.description}</dd>`;
        });
        html += '</dl></div></div></div>';
        
        html += '<div class="col-md-4 mb-4">';
        html += '<div class="card h-100"><div class="card-header"><h5 class="mb-0">Source Fields</h5></div>';
        html += '<div class="card-body"><dl>';
        data.sources.forEach(s => {
            html += `<dt><code>${s.value}</code></dt><dd class="mb-3">${s.description}</dd>`;
        });
        html += '</dl></div></div></div>';
        
        html += '</div>';
        
        html += '<div class="row"><div class="col-12">';
        html += '<div class="card"><div class="card-header"><h5 class="mb-0">Exclusion Pattern Types</h5></div>';
        html += '<div class="card-body"><dl class="row">';
        data.exclusion_types.forEach(e => {
            html += `<dt class="col-sm-3"><code>${e.value}</code></dt><dd class="col-sm-9">${e.description}</dd>`;
        });
        html += '</dl></div></div></div></div>';
        
        const container = document.getElementById('reference-content');
        if (!container) return;
        container.innerHTML = html;
    } catch (error) {
        const container = document.getElementById('reference-content');
        if (!container) return;
        container.innerHTML = `
            <div class="alert alert-danger">Error loading reference: ${error.message}</div>
        `;
    }
}

async function showAssignModal(rulesetId) {
    document.getElementById('assign-ruleset-id').value = rulesetId;
    
    const assignmentsResponse = await fetch(`/api/epg-match-rules/rulesets/${rulesetId}`);
    const ruleset = await assignmentsResponse.json();
    
    const assignedAccountIds = new Set();
    for (const account of accounts) {
        try {
            const resp = await fetch(`/api/accounts/${account.id}/epg-match-rulesets`);
            const assignments = await resp.json();
            if (assignments.some(a => a.ruleset_id === rulesetId)) {
                assignedAccountIds.add(account.id);
            }
        } catch (e) {
            console.error('Error checking assignments:', e);
        }
    }
    
    let html = '<div class="list-group">';
    accounts.forEach(account => {
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
    if (assignModal) assignModal.show();
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
                body: JSON.stringify({ ruleset_id: parseInt(rulesetId), priority: 100 })
            });
        }
        
        await showAssignModal(parseInt(rulesetId));
        await loadRulesets(true);
    } catch (error) {
        alert('Error updating assignment: ' + error.message);
    }
}
