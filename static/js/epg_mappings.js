// ============================================================================
// Channel EPG Mappings
// ============================================================================

const mappingsState = {
    offset: 0,
    limit: 100,
    total: 0,
    loading: false,
    hasMore: false,
    accountId: null,
    categoryId: null,
    epgSourceId: null,
    viewMode: 'all',
    showFiltered: false
};

function updateAutoMatchButton() {
    const accountId = document.getElementById('mappingAccountSelect').value;
    const btn = document.getElementById('auto-match-btn');
    const dropdown = document.getElementById('auto-match-dropdown');
    const rulesetInfo = document.getElementById('account-ruleset-info');
    
    // Only update if elements exist (may not be visible on non-mappings tabs)
    if (!btn || !dropdown || !rulesetInfo) {
        return;
    }
    
    if (accountId) {
        btn.disabled = false;
        if (dropdown) dropdown.disabled = false;
        rulesetInfo.style.display = 'flex';
        loadAccountRulesetInfo(accountId);
    } else {
        btn.disabled = true;
        if (dropdown) dropdown.disabled = true;
        rulesetInfo.style.display = 'none';
    }
}

async function loadAccountRulesetInfo(accountId) {
    const infoText = document.getElementById('ruleset-info-text');
    // Return early if element doesn't exist (not on the mappings tab yet)
    if (!infoText) return;
    
    try {
        const response = await fetch(`/api/accounts/${accountId}/epg-match-rulesets`);
        const data = await response.json();
        
        if (Array.isArray(data) && data.length > 0) {
            const rulesetNames = data.map(r => r.ruleset_name).join(', ');
            infoText.innerHTML = `<i class="bi bi-list-check text-success"></i> <strong>Rule-based matching enabled:</strong> ${rulesetNames}`;
        } else {
            const defaultResponse = await fetch('/api/epg-match-rules/rulesets?is_default=true');
            const defaultData = await defaultResponse.json();
            
            const defaultRulesets = Array.isArray(defaultData) ? defaultData : (defaultData.rulesets || []);
            if (defaultRulesets.length > 0) {
                const defaultNames = defaultRulesets.map(r => r.name).join(', ');
                infoText.innerHTML = `<i class="bi bi-info-circle"></i> <strong>Using default rulesets:</strong> ${defaultNames}`;
            } else {
                infoText.innerHTML = `<i class="bi bi-exclamation-triangle text-warning"></i> No EPG match rules configured. <a href="/epg-match-rules">Create rules</a> for better matching.`;
            }
        }
    } catch (error) {
        console.error('Error loading ruleset info:', error);
        infoText.innerHTML = `<i class="bi bi-exclamation-circle text-danger"></i> Error loading ruleset info`;
    }
}

async function loadCategoriesForAccount(accountId) {
    const categorySelect = document.getElementById('mappingCategorySelect');
    categorySelect.innerHTML = '<option value="">Loading categories...</option>';
    
    if (!accountId) {
        categorySelect.innerHTML = '<option value="">Select an account first</option>';
        return;
    }
    
    try {
        const response = await fetch(`/api/categories?account_id=${accountId}&include_empty=false&include_ppv=false`);
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const categories = await response.json();
        
        if (!Array.isArray(categories)) {
            throw new Error('Categories response is not an array');
        }
        
        categorySelect.innerHTML = '<option value="">All Categories</option>';
        
        if (categories.length === 0) {
            const opt = document.createElement('option');
            opt.value = '';
            opt.textContent = '(No categories available)';
            opt.disabled = true;
            categorySelect.appendChild(opt);
            return;
        }
        
        for (const cat of categories) {
            const opt = document.createElement('option');
            opt.value = cat.id;
            opt.textContent = `${cat.category_name} (${cat.visible_count} channels)`;
            categorySelect.appendChild(opt);
        }
    } catch (error) {
        console.error('Error loading categories:', error);
        categorySelect.innerHTML = '<option value="">Error loading categories</option>';
        const opt = document.createElement('option');
        opt.value = '';
        opt.textContent = `(${error.message})`;
        opt.disabled = true;
        categorySelect.appendChild(opt);
    }
}

async function loadMappings(reset = true) {
    const accountId = document.getElementById('mappingAccountSelect').value;
    const categoryId = document.getElementById('mappingCategorySelect').value;
    const epgSourceId = document.getElementById('mappingEpgSourceSelect').value;
    const viewMode = document.getElementById('mappingViewSelect').value;
    const showFiltered = document.getElementById('showFilteredChannels').checked;
    const container = document.getElementById('mappings-list');
    
    updateAutoMatchButton();
    
    if (!accountId) {
        container.innerHTML = '<div class="text-center text-muted py-4">Select an account to view channel mappings</div>';
        document.getElementById('mappingCategorySelect').innerHTML = '<option value="">All Categories</option>';
        return;
    }
    
    if (reset || accountId !== mappingsState.accountId || 
        categoryId !== mappingsState.categoryId ||
        epgSourceId !== mappingsState.epgSourceId ||
        viewMode !== mappingsState.viewMode ||
        showFiltered !== mappingsState.showFiltered) {
        mappingsState.offset = 0;
        mappingsState.accountId = accountId;
        mappingsState.categoryId = categoryId;
        mappingsState.epgSourceId = epgSourceId;
        mappingsState.viewMode = viewMode;
        mappingsState.showFiltered = showFiltered;
        container.innerHTML = '<div class="text-center"><div class="spinner-border" role="status"></div></div>';
    }
    
    if (mappingsState.loading) return;
    mappingsState.loading = true;
    
    try {
        let url = `/api/epg/mappings?account_id=${accountId}&view_mode=${viewMode}&show_filtered=${showFiltered}&limit=${mappingsState.limit}&offset=${mappingsState.offset}`;
        if (categoryId) {
            url += `&category_id=${categoryId}`;
        }
        if (epgSourceId) {
            url += `&epg_source_id=${epgSourceId}`;
        }
        const response = await fetch(url);
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.error || `HTTP ${response.status}: ${response.statusText}`);
        }
        
        mappingsState.total = data.total;
        mappingsState.hasMore = data.has_more || false;
        
        if (mappingsState.offset === 0 && data.total === 0) {
            let message = 'No channels found with current filters.';
            if (viewMode === 'unmapped') {
                message = '<i class="bi bi-check-circle"></i> All channels have EPG mappings!';
                container.innerHTML = `<div class="alert alert-success">${message}</div>`;
            } else if (viewMode === 'mapped') {
                message = 'No channel mappings found. Run auto-match or create manual mappings.';
                container.innerHTML = `<div class="alert alert-info">${message}</div>`;
            } else {
                container.innerHTML = `<div class="alert alert-info">${message}</div>`;
            }
            return;
        }
        
        let html = '';
        if (mappingsState.offset === 0) {
            const labelMap = { all: 'channels', unmapped: 'unmapped channels', mapped: 'mapped channels' };
            const filterNote = !showFiltered ? ' (filtered-out channels hidden)' : '';
            html = `<p class="text-muted mb-2" id="mappings-count">Showing 0 of ${data.total} ${labelMap[viewMode] || 'channels'}${filterNote}</p>`;
            html += '<div class="table-responsive" id="mappings-table-container" style="max-height: 600px; overflow-y: auto;">';
            html += '<table class="table table-striped table-sm" id="mappings-table">';
            html += `
                <thead style="position: sticky; top: 0; background: white; z-index: 1;">
                    <tr>
                        <th style="width: 30%">Channel Name</th>
                        <th style="width: 15%">Category</th>
                        <th style="width: 25%">EPG Mapping</th>
                        <th style="width: 15%">Match Info</th>
                        <th style="width: 15%">Actions</th>
                    </tr>
                </thead>
                <tbody id="mappings-tbody">
            `;
        }
        
        const items = data.channels || data.unmapped_channels || data.mappings || [];
        
        for (const item of items) {
            html += renderMappingRow(item, viewMode);
        }
        
        if (mappingsState.offset === 0) {
            html += '</tbody></table>';
            if (data.has_more) {
                html += '<div id="mappings-loader" class="text-center py-3"><div class="spinner-border spinner-border-sm"></div> Loading more...</div>';
            }
            html += '</div>';
            container.innerHTML = html;
            
            const tableContainer = document.getElementById('mappings-table-container');
            if (tableContainer) {
                tableContainer.addEventListener('scroll', handleMappingsScroll);
            }
        } else {
            document.getElementById('mappings-tbody').insertAdjacentHTML('beforeend', html);
        }
        
        mappingsState.offset += items.length;
        
        const countEl = document.getElementById('mappings-count');
        if (countEl) {
            const labelMap = { all: 'channels', unmapped: 'unmapped channels', mapped: 'mapped channels' };
            const filterNote = !showFiltered ? ' (filtered-out channels hidden)' : '';
            countEl.textContent = `Showing ${mappingsState.offset} of ${mappingsState.total} ${labelMap[viewMode] || 'channels'}${filterNote}`;
        }
        
        const loader = document.getElementById('mappings-loader');
        if (loader) {
            loader.style.display = mappingsState.hasMore ? 'block' : 'none';
        }
        
    } catch (error) {
        if (mappingsState.offset === 0) {
            container.innerHTML = `<div class="alert alert-danger">Error: ${error.message}</div>`;
        }
        console.error('Error loading mappings:', error);
    } finally {
        mappingsState.loading = false;
    }
}

function renderMappingRow(item, viewMode) {
    const filteredBadge = item.is_visible === false ? '<span class="badge bg-secondary ms-1">Filtered</span>' : '';
    
    let channelId, channelName, originalName, streamId, accountId, categoryName, mapping, currentProgram;
    
    if (viewMode === 'all') {
        channelId = item.id;
        originalName = item.name;
        channelName = item.cleaned_name || item.name;
        streamId = item.stream_id;
        accountId = item.account_id;
        categoryName = item.category_name || '-';
        mapping = item.mapping;
        currentProgram = item.current_program;
    } else if (viewMode === 'unmapped') {
        channelId = item.id;
        originalName = item.name;
        channelName = item.cleaned_name || item.name;
        streamId = item.stream_id;
        accountId = item.account_id;
        categoryName = item.category_name || '-';
        mapping = null;
        currentProgram = null;
    } else {
        channelId = item.channel_id;
        originalName = item.channel_name;
        channelName = item.cleaned_name || item.channel_name || `Channel #${item.channel_id}`;
        streamId = item.stream_id;
        accountId = item.account_id;
        categoryName = '-';
        mapping = {
            id: item.id,
            epg_channel_id: item.epg_channel_id,
            epg_display_name: item.epg_display_name,
            mapping_type: item.mapping_type,
            confidence: item.confidence,
            is_override: item.is_override,
            source_name: item.source_name
        };
        currentProgram = item.current_program;
    }
    
    let mappingCell, matchInfoCell;
    if (mapping) {
        let programInfo = '';
        if (currentProgram) {
            const liveTag = currentProgram.is_live ? '<span class="badge bg-danger ms-1">LIVE</span>' : '';
            programInfo = `<div class="small text-primary mt-1"><i class="bi bi-play-circle"></i> ${escapeHtml(currentProgram.title)}${liveTag}</div>`;
        }
        mappingCell = `<span class="text-success">${mapping.epg_display_name || 'EPG #' + mapping.epg_channel_id}</span>${programInfo}`;
        
        const typeBadge = mapping.mapping_type === 'manual' 
            ? '<span class="badge bg-primary">Manual</span>'
            : mapping.mapping_type === 'provider'
            ? '<span class="badge bg-success">Provider</span>'
            : mapping.mapping_type === 'callsign_tag'
            ? '<span class="badge bg-info">Callsign</span>'
            : mapping.mapping_type === 'fcc_lookup'
            ? '<span class="badge bg-info">FCC</span>'
            : mapping.mapping_type === 'ppv_event'
            ? '<span class="badge bg-warning">PPV Event</span>'
            : mapping.mapping_type?.includes('auto')
            ? '<span class="badge bg-info">Auto</span>'
            : `<span class="badge bg-secondary">${mapping.mapping_type || 'Unknown'}</span>`;
        
        const confidencePercent = Math.round((mapping.confidence || 0) * 100);
        const overrideIcon = mapping.is_override ? ' <i class="bi bi-pin-fill text-warning" title="Override"></i>' : '';
        
        matchInfoCell = `${typeBadge} ${confidencePercent}%${overrideIcon}`;
    } else {
        mappingCell = '<span class="text-muted">Not mapped</span>';
        matchInfoCell = '-';
    }
    
    let actions = `<a class="btn btn-outline-success btn-sm" href="/player/${accountId}/${streamId}" target="_blank" title="Play stream"><i class="bi bi-play-fill"></i></a>`;
    
    if (mapping) {
        // PPV event mappings use EventChannelLink (can't be deleted/edited via normal mapping API)
        if (mapping.mapping_type === 'ppv_event') {
            actions += ` <button class="btn btn-outline-secondary btn-sm" disabled title="PPV event links cannot be edited"><i class="bi bi-lock"></i></button>`;
        } else {
            // Edit mapping button - opens modal with existing mapping info
            const existingMappingJson = JSON.stringify(mapping).replace(/'/g, "\\'").replace(/"/g, '&quot;');
            actions += ` <button class="btn btn-outline-primary btn-sm" onclick='showManualMappingModal(${channelId}, "${escapeHtml(channelName).replace(/"/g, '&quot;')}", ${accountId}, ${streamId}, ${existingMappingJson})' title="Edit mapping"><i class="bi bi-pencil"></i></button>`;
        }
    } else {
        actions += ` <button class="btn btn-outline-primary btn-sm" onclick="showManualMappingModal(${channelId}, '${escapeHtml(channelName).replace(/'/g, "\\'")}', ${accountId}, ${streamId})" title="Create mapping"><i class="bi bi-link"></i></button>`;
    }
    
    const escapedChannelName = escapeHtml(channelName).replace(/'/g, "\\'");
    actions += ` <button class="btn btn-outline-secondary btn-sm" onclick="hideChannel(${accountId}, '${escapedChannelName}')" title="Hide this channel"><i class="bi bi-eye-slash"></i></button>`;
    
    const tooltip = originalName && originalName !== channelName ? ` title="${escapeHtml(originalName)}"` : '';
    
    return `
        <tr data-channel-id="${channelId}">
            <td${tooltip}>${channelName}${filteredBadge}</td>
            <td><small class="text-muted">${categoryName}</small></td>
            <td>${mappingCell}</td>
            <td>${matchInfoCell}</td>
            <td><div class="btn-group btn-group-sm">${actions}</div></td>
        </tr>
    `;
}

async function handleMappingsScroll(event) {
    const container = event.target;
    const scrollBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
    
    if (scrollBottom < 100 && !mappingsState.loading && mappingsState.hasMore) {
        await loadMoreMappings();
    }
}

async function loadMoreMappings() {
    if (!mappingsState.hasMore || mappingsState.loading) return;
    
    const loader = document.getElementById('mappings-loader');
    if (loader) loader.style.display = 'block';
    
    await loadMappings(false);
}

async function deleteMapping(id, channelId) {
    try {
        const response = await fetch(`/api/epg/mappings/${id}`, { method: 'DELETE' });
        if (response.ok) {
            const row = document.querySelector(`tr[data-channel-id="${channelId}"]`);
            if (row) {
                const cells = row.querySelectorAll('td');
                if (cells.length >= 4) {
                    cells[2].innerHTML = '<span class="text-muted">Not mapped</span>';
                    cells[3].innerHTML = '-';
                }
                const channelName = cells[0].textContent.replace(/Filtered$/, '').trim();
                const actionsDiv = cells[4].querySelector('.btn-group');
                if (actionsDiv) {
                    const deleteBtn = actionsDiv.querySelector('button[onclick^="deleteMapping"]');
                    if (deleteBtn) {
                        const createBtn = document.createElement('button');
                        createBtn.className = 'btn btn-outline-primary btn-sm';
                        createBtn.setAttribute('onclick', `showManualMappingModal(${channelId}, '${escapeHtml(channelName)}')`);
                        createBtn.setAttribute('title', 'Create mapping');
                        createBtn.innerHTML = '<i class="bi bi-link"></i>';
                        deleteBtn.replaceWith(createBtn);
                    }
                }
            }
            showToast('Mapping deleted', 'success');
        } else {
            const error = await response.json();
            showToast('Error: ' + (error.error || 'Failed to delete mapping'), 'error');
        }
    } catch (error) {
        showToast('Error: ' + error.message, 'error');
    }
}

async function clearCategoryMappings() {
    const accountId = document.getElementById('mappingAccountSelect').value;
    const categoryId = document.getElementById('mappingCategorySelect').value;
    const categorySelect = document.getElementById('mappingCategorySelect');
    const categoryName = categorySelect.options[categorySelect.selectedIndex]?.text || 'selected category';
    
    if (!accountId) {
        alert('Please select an account first');
        return;
    }
    
    if (!categoryId) {
        alert('Please select a category first');
        return;
    }
    
    if (!confirm(`Are you sure you want to delete ALL EPG mappings for channels in "${categoryName}"?\n\nThis action cannot be undone.`)) {
        return;
    }
    
    try {
        const response = await fetch('/api/epg/mappings/bulk-delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ account_id: parseInt(accountId), category_id: parseInt(categoryId) })
        });
        
        const result = await response.json();
        
        if (response.ok) {
            showToast(`Deleted ${result.deleted_count} mappings from "${categoryName}"`, 'success');
            await loadMappings();
        } else {
            showToast('Error: ' + (result.error || 'Failed to delete mappings'), 'error');
        }
    } catch (error) {
        showToast('Error: ' + error.message, 'error');
    }
}

async function runAutoMatch() {
    const accountId = document.getElementById('mappingAccountSelect').value;
    const categoryId = document.getElementById('mappingCategorySelect').value;
    const includeFiltered = document.getElementById('showFilteredChannels').checked;
    const sourceId = document.getElementById('mappingEpgSourceSelect').value;
    
    if (!accountId) {
        alert('Please select an account');
        return;
    }
    
    const btn = document.getElementById('auto-match-btn');
    const dropdown = document.getElementById('auto-match-dropdown');
    const originalHtml = btn.innerHTML;
    btn.disabled = true;
    dropdown.disabled = true;
    btn.innerHTML = `<span class="spinner-border spinner-border-sm"></span> Matching...`;
    
    const listContainer = document.getElementById('mappings-list');
    const originalListContent = listContainer.innerHTML;
    
    const alertDiv = document.getElementById('autoMatchResultsAlert');
    alertDiv.classList.add('d-none');
    
    try {
        await runRuleBasedMatch(accountId, categoryId, includeFiltered, sourceId, listContainer, alertDiv);
        await loadMappings();
    } catch (error) {
        listContainer.innerHTML = originalListContent;
        alertDiv.classList.remove('d-none', 'alert-info', 'alert-success');
        alertDiv.classList.add('alert-danger');
        const contentDiv = document.getElementById('autoMatchResultsContent');
        
        let errorMsg = error.message;
        if (error.name === 'AbortError') {
            errorMsg = 'Operation timed out after 10 minutes. Try filtering by category to match fewer channels at once.';
        } else if (error.message.includes('NetworkError') || error.message.includes('Failed to fetch')) {
            errorMsg = 'Network error or server timeout. For large channel lists, try filtering by category first.';
        }
        
        contentDiv.innerHTML = `<strong><i class="bi bi-x-circle"></i> Error:</strong> ${errorMsg}`;
    } finally {
        btn.disabled = false;
        dropdown.disabled = false;
        btn.innerHTML = originalHtml;
    }
}

async function runRuleBasedMatch(accountId, categoryId, includeFiltered, sourceId, listContainer, alertDiv) {
    listContainer.innerHTML = `
        <div class="text-center py-5">
            <div class="spinner-border text-primary mb-3" role="status" style="width: 3rem; height: 3rem;"></div>
            <h5>Running Rule-Based Match...</h5>
            <p class="text-muted">Matching channels using configured EPG match rules.</p>
        </div>
    `;
    
    let url = `/api/epg/match-with-rules/${accountId}?`;
    const params = [];
    if (categoryId) params.push(`category_id=${categoryId}`);
    if (includeFiltered) params.push('include_filtered=true');
    if (sourceId) params.push(`source_id=${sourceId}`);
    url += params.join('&');
    
    const response = await fetch(url, { method: 'POST' });
    const result = await response.json();
    
    if (!response.ok) {
        throw new Error(result.error || 'Rule-based match failed');
    }
    
    const stats = result.stats || {};
    const matchedCount = stats.matched || 0;
    
    alertDiv.classList.remove('d-none', 'alert-info', 'alert-danger');
    alertDiv.classList.add('alert-success');
    const contentDiv = document.getElementById('autoMatchResultsContent');
    
    let statsHtml = `<i class="bi bi-check-circle"></i> <strong>Rule-Based Match: ${matchedCount} channels matched</strong>`;
    
    const byType = stats.by_match_type || {};
    const typeDetails = [];
    if (byType.exact_id) typeDetails.push(`ID: ${byType.exact_id}`);
    if (byType.callsign_tag) typeDetails.push(`Callsign: ${byType.callsign_tag}`);
    if (byType.fcc_lookup) typeDetails.push(`FCC: ${byType.fcc_lookup}`);
    if (byType.exact_name) typeDetails.push(`Name: ${byType.exact_name}`);
    if (byType.fuzzy_name) typeDetails.push(`Fuzzy: ${byType.fuzzy_name}`);
    if (byType.regex) typeDetails.push(`Regex: ${byType.regex}`);
    
    if (typeDetails.length > 0) {
        statsHtml += ` <span class="ms-2 text-muted small">(${typeDetails.join(', ')}`;
        if (stats.skipped_existing) statsHtml += `, Skipped: ${stats.skipped_existing}`;
        if (stats.excluded) statsHtml += `, Excluded: ${stats.excluded}`;
        if (stats.unmatched) statsHtml += `, Unmatched: ${stats.unmatched}`;
        statsHtml += `)</span>`;
    }
    
    contentDiv.innerHTML = statsHtml;
}

async function hideChannel(accountId, channelName) {    
    try {
        const response = await fetch('/api/filters', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                account_id: accountId,
                name: `Hide: ${channelName}`,
                filter_type: 'channel_name',
                filter_action: 'blacklist',
                filter_value: channelName,
                enabled: true
            })
        });
        
        if (response.ok) {
            showToast(`Channel "${channelName}" hidden`, 'success');
            const rows = document.querySelectorAll('#mappings-list tbody tr');
            for (const row of rows) {
                const nameCell = row.querySelector('td:first-child');
                if (nameCell && nameCell.textContent.trim().replace(/Filtered$/, '').trim() === channelName) {
                    if (!nameCell.querySelector('.badge')) {
                        nameCell.innerHTML += '<span class="badge bg-secondary ms-1">Filtered</span>';
                    }
                    row.style.opacity = '0.5';
                    break;
                }
            }
        } else {
            const error = await response.json();
            showToast('Error: ' + (error.error || 'Failed to hide channel'), 'error');
        }
    } catch (error) {
        showToast('Error: ' + error.message, 'error');
    }
}
