// ============================================================================
// EPG Match Rules (Rules within Rulesets)
// ============================================================================

function showCreateRuleModal(rulesetId) {
    document.getElementById('ruleModalTitle').textContent = 'New EPG Match Rule';
    document.getElementById('ruleForm').reset();
    document.getElementById('rule-id').value = '';
    document.getElementById('rule-ruleset-id').value = rulesetId;
    document.getElementById('rule-enabled').checked = true;
    document.getElementById('rule-stop-on-match').checked = true;
    
    populateRuleAccountDropdown();
    resetRulePreview();
    updateRuleFormVisibility();
    if (ruleModal) ruleModal.show();
}

async function editRule(ruleId) {
    const response = await fetch(`/api/epg-match-rules/rules/${ruleId}`);
    const rule = await response.json();
    
    document.getElementById('ruleModalTitle').textContent = 'Edit EPG Match Rule';
    document.getElementById('rule-id').value = rule.id;
    document.getElementById('rule-ruleset-id').value = rule.ruleset_id;
    document.getElementById('rule-name').value = rule.name;
    document.getElementById('rule-description').value = rule.description || '';
    document.getElementById('rule-match-type').value = rule.match_type;
    document.getElementById('rule-source').value = rule.source || 'cleaned_name';
    document.getElementById('rule-action').value = rule.action || 'map_epg';
    document.getElementById('rule-min-confidence').value = rule.min_confidence || 0.75;
    document.getElementById('rule-pattern').value = rule.pattern || '';
    document.getElementById('rule-fallback-epg-id').value = rule.fallback_epg_id || '';
    document.getElementById('rule-category-pattern').value = rule.category_pattern || '';
    document.getElementById('rule-category-exclude-pattern').value = rule.category_exclude_pattern || '';
    document.getElementById('rule-country-codes').value = (rule.country_codes || []).join(', ');
    document.getElementById('rule-time-offset').value = rule.time_offset_hours || 0;
    document.getElementById('rule-priority').value = rule.priority;
    document.getElementById('rule-enabled').checked = rule.enabled;
    document.getElementById('rule-stop-on-match').checked = rule.stop_on_match;
    
    populateRuleAccountDropdown();
    resetRulePreview();
    updateRuleFormVisibility();
    if (ruleModal) ruleModal.show();
}

function updateRuleFormVisibility() {
    const matchType = document.getElementById('rule-match-type').value;
    const action = document.getElementById('rule-action').value;
    
    const confidenceGroup = document.getElementById('confidence-group');
    confidenceGroup.style.display = matchType === 'fuzzy_name' ? 'block' : 'none';
    
    const fallbackGroup = document.getElementById('fallback-group');
    fallbackGroup.style.display = action === 'use_fallback' ? 'block' : 'none';
}

async function saveRule() {
    const id = document.getElementById('rule-id').value;
    const countryCodes = document.getElementById('rule-country-codes').value
        .split(',')
        .map(s => s.trim().toUpperCase())
        .filter(s => s.length > 0);
    
    const data = {
        ruleset_id: parseInt(document.getElementById('rule-ruleset-id').value),
        name: document.getElementById('rule-name').value,
        description: document.getElementById('rule-description').value,
        match_type: document.getElementById('rule-match-type').value,
        source: document.getElementById('rule-source').value,
        action: document.getElementById('rule-action').value,
        min_confidence: parseFloat(document.getElementById('rule-min-confidence').value),
        pattern: document.getElementById('rule-pattern').value || null,
        fallback_epg_id: document.getElementById('rule-fallback-epg-id').value || null,
        category_pattern: document.getElementById('rule-category-pattern').value || null,
        category_exclude_pattern: document.getElementById('rule-category-exclude-pattern').value || null,
        country_codes: countryCodes.length > 0 ? countryCodes : null,
        time_offset_hours: parseInt(document.getElementById('rule-time-offset').value) || 0,
        priority: parseInt(document.getElementById('rule-priority').value),
        enabled: document.getElementById('rule-enabled').checked,
        stop_on_match: document.getElementById('rule-stop-on-match').checked
    };
    
    try {
        const url = id ? `/api/epg-match-rules/rules/${id}` : '/api/epg-match-rules/rules';
        const method = id ? 'PUT' : 'POST';
        
        const response = await fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        
        if (response.ok) {
            bootstrap.Modal.getInstance(document.getElementById('ruleModal')).hide();
            await loadRulesets(true);
        } else {
            const error = await response.json();
            alert('Error: ' + (error.error || error.validation_errors || 'Failed to save rule'));
        }
    } catch (error) {
        alert('Error saving rule: ' + error.message);
    }
}

async function deleteRule(ruleId, rulesetId) {
    if (!confirm('Delete this rule?')) return;
    
    try {
        const response = await fetch(`/api/epg-match-rules/rules/${ruleId}`, { method: 'DELETE' });
        if (response.ok) {
            await loadRulesForRuleset(rulesetId);
        }
    } catch (error) {
        alert('Error deleting rule: ' + error.message);
    }
}

async function previewRulePattern() {
    const matchType = document.getElementById('rule-match-type').value;
    const source = document.getElementById('rule-source').value;
    const pattern = document.getElementById('rule-pattern').value;
    const categoryPattern = document.getElementById('rule-category-pattern').value;
    const categoryExcludePattern = document.getElementById('rule-category-exclude-pattern').value;
    const accountId = document.getElementById('rule-account-filter').value;
    
    const patternBasedTypes = ['regex', 'exact_name', 'fuzzy_name', 'category_pattern'];
    const needsPattern = patternBasedTypes.includes(matchType);
    
    if (needsPattern && !pattern && !categoryPattern) {
        document.getElementById('rule-preview-results').style.display = 'block';
        document.getElementById('rule-preview-error').style.display = 'block';
        document.getElementById('rule-preview-error').textContent = 'Please enter a pattern or category filter to preview';
        document.getElementById('rule-preview-content').style.display = 'none';
        return;
    }
    
    document.getElementById('rule-preview-results').style.display = 'block';
    document.getElementById('rule-preview-loading').style.display = 'block';
    document.getElementById('rule-preview-error').style.display = 'none';
    document.getElementById('rule-preview-content').style.display = 'none';
    
    try {
        const response = await fetch('/api/epg-match-rules/rules/preview', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                match_type: matchType,
                source: source,
                pattern: pattern || null,
                category_pattern: categoryPattern || null,
                category_exclude_pattern: categoryExcludePattern || null,
                account_id: accountId || null
            })
        });
        
        const data = await response.json();
        
        document.getElementById('rule-preview-loading').style.display = 'none';
        
        if (data.error) {
            document.getElementById('rule-preview-error').style.display = 'block';
            document.getElementById('rule-preview-error').textContent = data.error;
            document.getElementById('rule-preview-content').style.display = 'none';
        } else {
            document.getElementById('rule-preview-content').style.display = 'block';
            document.getElementById('rule-preview-count').textContent = data.total_count;
            document.getElementById('rule-preview-more').style.display = data.total_count > 100 ? 'inline' : 'none';
            
            let html = '';
            if (data.matches.length === 0) {
                html = '<p class="text-muted mb-0">No channels match this pattern</p>';
            } else {
                html = '<ul class="list-unstyled mb-0">';
                data.matches.forEach(match => {
                    const name = escapeHtml(match.cleaned_name || match.name);
                    const category = match.category ? `<small class="text-muted"> (${escapeHtml(match.category)})</small>` : '';
                    const epgId = match.epg_channel_id ? `<span class="badge bg-secondary ms-1" title="Provider EPG ID">${escapeHtml(match.epg_channel_id)}</span>` : '';
                    html += `<li class="mb-1"><code>${name}</code>${category}${epgId}</li>`;
                });
                html += '</ul>';
            }
            document.getElementById('rule-preview-list').innerHTML = html;
        }
    } catch (error) {
        document.getElementById('rule-preview-loading').style.display = 'none';
        document.getElementById('rule-preview-error').style.display = 'block';
        document.getElementById('rule-preview-error').textContent = 'Error: ' + error.message;
        document.getElementById('rule-preview-content').style.display = 'none';
    }
}
