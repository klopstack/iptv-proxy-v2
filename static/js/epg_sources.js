// ============================================================================
// EPG Sources Management
// ============================================================================
// Note: accounts, sources, sourceModal, searchLineupModal, manualMappingModal,
// sdStationsModal, sourceMappingsModal are declared in epg_common.js

    // Source mappings state
let currentSourceMappings = {
    sourceId: null,
    sourceName: '',
    offset: 0,
    limit: 50,
    search: ''
};

async function loadAccounts() {
    try {
        const response = await fetch('/api/accounts');
        const data = await response.json();
        
        if (!response.ok || !Array.isArray(data)) {
            console.error('Error loading accounts:', data.error || 'Invalid response');
            return;
        }
        
        accounts = data;
        
        // Populate account selects
        const selects = ['sourceAccountId', 'mappingAccountSelect', 'matchAccountSelect'];
        selects.forEach(id => {
            const select = document.getElementById(id);
            if (select) {
                const firstOption = select.options[0].outerHTML;
                select.innerHTML = firstOption;
                accounts.forEach(a => {
                    select.innerHTML += `<option value="${a.id}">${a.name}</option>`;
                });
            }
        });
    } catch (error) {
        console.error('Error loading accounts:', error);
    }
}

async function loadSources() {
    try {
        const response = await fetch('/api/epg/sources');
        const data = await response.json();
        
        if (!response.ok || !Array.isArray(data)) {
            throw new Error(data.error || 'Invalid response from server');
        }
        
        sources = data;
        renderSources();
        populateSourceSelects();
    } catch (error) {
        document.getElementById('sources-list').innerHTML = `
            <div class="alert alert-danger">Error loading EPG sources: ${error.message}</div>
        `;
    }
}

function populateSourceSelects() {
    const selects = ['channelSourceSelect', 'matchSourceSelect', 'mappingEpgSourceSelect', 'manualMappingEpgSource'];
    selects.forEach(id => {
        const select = document.getElementById(id);
        if (select) {
            const firstOption = select.options[0].outerHTML;
            select.innerHTML = firstOption;
            sources.forEach(s => {
                select.innerHTML += `<option value="${s.id}">${s.name} (${s.source_type})</option>`;
            });
        }
    });
}

function renderSources() {
    const container = document.getElementById('sources-list');
    
    if (sources.length === 0) {
        container.innerHTML = `
            <div class="alert alert-info">
                <i class="bi bi-info-circle"></i> No EPG sources configured yet.
                Click "Add EPG Source" to get started.
            </div>
        `;
        return;
    }
    
    let html = '<div class="table-responsive"><table class="table table-striped">';
    html += `
        <thead>
            <tr>
                <th>Name</th>
                <th>Type</th>
                <th>Source</th>
                <th>Channels</th>
                <th>In Use</th>
                <th>Last Sync</th>
                <th>Status</th>
                <th>Actions</th>
            </tr>
        </thead>
        <tbody>
    `;
    
    for (const source of sources) {
        const statusBadge = source.last_sync_status === 'success' 
            ? '<span class="badge bg-success">Success</span>'
            : source.last_sync_status === 'error'
            ? '<span class="badge bg-danger">Error</span>'
            : source.last_sync_status === null || source.last_sync_status === undefined
            ? '<span class="badge bg-secondary">Never synced</span>'
            : '<span class="badge bg-secondary">' + source.last_sync_status + '</span>';
            
        const sourceInfo = source.source_type === 'provider' 
            ? (source.account_name || 'Account ' + source.account_id)
            : source.source_type === 'xmltv_url'
            ? '<small class="text-muted">' + (source.url?.substring(0, 40) || 'No URL') + '...</small>'
            : source.source_type === 'schedules_direct'
            ? '<i class="bi bi-broadcast-pin"></i> SD'
            : source.source_type === 'xmltv_grabber'
            ? '<i class="bi bi-terminal"></i> ' + (source.xmltv_grabber || 'Grabber')
            : '-';

        const usedCount = source.used_mapping_count || 0;
        const inUseHtml = usedCount > 0
            ? `<a href="#" onclick="showSourceMappings(${source.id}, '${source.name.replace(/'/g, "\\'")}'); return false;" class="text-decoration-none">
                <span class="badge bg-primary">${usedCount}</span>
               </a>`
            : '<span class="badge bg-secondary">0</span>';
            
        html += `
            <tr>
                <td>
                    ${source.name}
                    ${!source.enabled ? '<span class="badge bg-secondary ms-2">Disabled</span>' : ''}
                    ${source.source_type === 'schedules_direct' ? '<button class="btn btn-sm btn-link p-0 ms-2" onclick="toggleSdLineups(' + source.id + ')" title="Show/Hide Lineups" id="sd-toggle-' + source.id + '"><i class="bi bi-chevron-down"></i></button>' : ''}
                </td>
                <td><span class="badge bg-info">${source.source_type}</span></td>
                <td>${sourceInfo}</td>
                <td>${source.channel_count || 0}</td>
                <td>${inUseHtml}</td>
                <td>${source.last_sync ? formatLocalDateTime(source.last_sync) : 'Never'}</td>
                <td>${statusBadge}</td>
                <td>
                    <div class="btn-group btn-group-sm">
                        ${source.source_type === 'schedules_direct' 
                            ? '<button class="btn btn-outline-info" onclick="showSdLineups(' + source.id + ')" title="Manage Lineups"><i class="bi bi-list-ul"></i></button>'
                            : source.source_type === 'ppv_events'
                            ? '<a href="/ppv" class="btn btn-outline-info" title="Manage PPV events and enrichment - auto-synced during enrichment"><i class="bi bi-info-circle"></i></a>'
                            : '<button class="btn btn-outline-primary" onclick="syncSource(' + source.id + ')" title="Sync"><i class="bi bi-arrow-repeat"></i></button>'}
                        <button class="btn btn-outline-secondary" onclick="editSource(${source.id})" title="Edit">
                            <i class="bi bi-pencil"></i>
                        </button>
                        <button class="btn btn-outline-danger" onclick="deleteSource(${source.id})" title="Delete">
                            <i class="bi bi-trash"></i>
                        </button>
                    </div>
                </td>
            </tr>
        `;
        
        if (source.source_type === 'schedules_direct') {
            html += `
                <tr id="sd-lineups-${source.id}" class="sd-lineup-rows" style="display: none;">
                    <td colspan="8" class="bg-light">
                        <div class="p-2" id="sd-lineups-content-${source.id}">
                            <div class="text-center text-muted">
                                <div class="spinner-border spinner-border-sm" role="status"></div> Loading lineups...
                            </div>
                        </div>
                    </td>
                </tr>
            `;
        }
    }
    
    html += '</tbody></table></div>';
    container.innerHTML = html;
}

function onSourceTypeChange() {
    const type = document.getElementById('sourceType').value;
    document.getElementById('providerFields').style.display = type === 'provider' ? 'block' : 'none';
    document.getElementById('xmltvUrlFields').style.display = type === 'xmltv_url' ? 'block' : 'none';
    document.getElementById('sdFields').style.display = type === 'schedules_direct' ? 'block' : 'none';
    document.getElementById('grabberFields').style.display = type === 'xmltv_grabber' ? 'block' : 'none';
    document.getElementById('ppvFields').style.display = type === 'ppv_events' ? 'block' : 'none';
    
    if (type === 'xmltv_grabber') {
        populateGrabberSelect();
    }
}

async function saveSource() {
    const id = document.getElementById('sourceId').value;
    const data = {
        name: document.getElementById('sourceName').value,
        source_type: document.getElementById('sourceType').value,
        priority: parseInt(document.getElementById('sourcePriority').value) || 100,
        enabled: document.getElementById('sourceEnabled').checked
    };
    
    if (data.source_type === 'provider') {
        data.account_id = parseInt(document.getElementById('sourceAccountId').value);
        if (!data.account_id) {
            alert('Please select an account');
            return;
        }
    } else if (data.source_type === 'xmltv_url') {
        data.url = document.getElementById('sourceUrl').value;
        if (!data.url) {
            alert('Please enter a URL');
            return;
        }
    } else if (data.source_type === 'schedules_direct') {
        data.sd_username = document.getElementById('sdUsername').value;
        data.sd_password = document.getElementById('sdPassword').value;
        if (!data.sd_username || !data.sd_password) {
            alert('Please enter SD credentials');
            return;
        }
    } else if (data.source_type === 'xmltv_grabber') {
        data.xmltv_grabber = document.getElementById('grabberSelect').value;
        data.xmltv_config_name = document.getElementById('grabberConfigName').value || null;
        data.xmltv_days = parseInt(document.getElementById('grabberDays').value) || 7;
        data.xmltv_offset = parseInt(document.getElementById('grabberOffset').value) || 0;
        if (!data.xmltv_grabber) {
            alert('Please select a grabber');
            return;
        }
    }
    
    try {
        const url = id ? `/api/epg/sources/${id}` : '/api/epg/sources';
        const method = id ? 'PUT' : 'POST';
        
        const response = await fetch(url, {
            method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        
        if (response.ok) {
            if (sourceModal) sourceModal.hide();
            await loadSources();
            alert('✓ EPG source saved successfully');
        } else {
            const error = await response.json();
            alert('Error: ' + (error.error || 'Failed to save source'));
        }
    } catch (error) {
        alert('Error saving source: ' + error.message);
    }
}

function editSource(id) {
    const source = sources.find(s => s.id === id);
    if (!source) return;
    
    document.getElementById('sourceId').value = source.id;
    document.getElementById('sourceName').value = source.name;
    document.getElementById('sourceType').value = source.source_type;
    document.getElementById('sourcePriority').value = source.priority;
    document.getElementById('sourceEnabled').checked = source.enabled;
    
    if (source.source_type === 'provider') {
        document.getElementById('sourceAccountId').value = source.account_id || '';
    } else if (source.source_type === 'xmltv_url') {
        document.getElementById('sourceUrl').value = source.url || '';
    } else if (source.source_type === 'xmltv_grabber') {
        populateGrabberSelect().then(() => {
            document.getElementById('grabberSelect').value = source.xmltv_grabber || '';
            document.getElementById('grabberConfigName').value = source.xmltv_config_name || '';
            document.getElementById('grabberDays').value = source.xmltv_days || 7;
            document.getElementById('grabberOffset').value = source.xmltv_offset || 0;
        });
    }
    
    onSourceTypeChange();
    document.getElementById('sourceModalLabel').textContent = 'Edit EPG Source';
    if (sourceModal) sourceModal.show();
}

async function deleteSource(id) {
    if (!confirm('Delete this EPG source? This will also delete all its channels.')) return;
    
    try {
        const response = await fetch(`/api/epg/sources/${id}`, { method: 'DELETE' });
        if (response.ok) {
            await loadSources();
            alert('✓ EPG source deleted');
        } else {
            const error = await response.json();
            alert('Error: ' + (error.error || 'Failed to delete source'));
        }
    } catch (error) {
        alert('Error deleting source: ' + error.message);
    }
}

async function syncSource(id) {
    const btn = event.target.closest('button');
    const originalHtml = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status"></span>';
    
    try {
        const source = sources.find(s => s.id === id);
        if (source && source.source_type === 'schedules_direct') {
            alert('⚠️ Schedules Direct Sync\n\nSchedules Direct sources are synced per-lineup.\n\nPlease go to the "Schedules Direct" tab and sync individual lineups.');
            btn.disabled = false;
            btn.innerHTML = originalHtml;
            return;
        }
        
        const response = await fetch(`/api/epg/sources/${id}/sync`, { method: 'POST' });
        const result = await response.json();
        
        if (response.ok) {
            await loadSources();
            alert(`✓ Synced! ${result.message}`);
        } else {
            alert('Error: ' + (result.error || 'Sync failed'));
        }
    } catch (error) {
        alert('Error syncing: ' + error.message);
    } finally {
        btn.disabled = false;
        btn.innerHTML = originalHtml;
    }
}

async function toggleSdLineups(sourceId) {
    const row = document.getElementById(`sd-lineups-${sourceId}`);
    const toggle = document.getElementById(`sd-toggle-${sourceId}`);
    
    if (row.style.display === 'none') {
        row.style.display = 'table-row';
        toggle.innerHTML = '<i class="bi bi-chevron-up"></i>';
        await loadSdLineupsInline(sourceId);
    } else {
        row.style.display = 'none';
        toggle.innerHTML = '<i class="bi bi-chevron-down"></i>';
    }
}

function showSdLineups(sourceId) {
    document.getElementById('sd-tab').click();
    document.getElementById('sdSourceSelect').value = sourceId;
    loadSdLineups();
}

async function loadSdLineupsInline(sourceId) {
    const container = document.getElementById(`sd-lineups-content-${sourceId}`);
    container.innerHTML = '<div class="text-center"><div class="spinner-border spinner-border-sm" role="status"></div></div>';
    
    try {
        const response = await fetch(`/api/epg/sd/lineups?source_id=${sourceId}`);
        const result = await response.json();
        
        if (result.error || result.success === false) {
            container.innerHTML = `<div class="alert alert-sm alert-danger mb-0">${result.error || 'Failed to load lineups'}</div>`;
            return;
        }
        
        const lineups = result.lineups || [];
        
        if (lineups.length === 0) {
            container.innerHTML = `
                <div class="text-muted text-center py-2">
                    <small>No lineups configured. <a href="#" onclick="showSdLineups(${sourceId}); return false;">Go to SD tab</a> to add lineups.</small>
                </div>
            `;
            return;
        }
        
        let html = '<div class="list-group list-group-flush">';
        for (const lineup of lineups) {
            html += `
                <div class="list-group-item px-3 py-2 d-flex justify-content-between align-items-center">
                    <div>
                        <strong>${lineup.name || lineup.lineup_id}</strong>
                        ${lineup.location ? '<br><small class="text-muted">' + lineup.location + '</small>' : ''}
                        <br><small class="text-muted">${lineup.channel_count || 0} channels</small>
                        ${lineup.last_sync ? '<small class="text-muted"> | Last sync: ' + formatLocalDateTime(lineup.last_sync) + '</small>' : ''}
                    </div>
                    <div class="btn-group btn-group-sm">
                        <button class="btn btn-sm btn-outline-primary" onclick="syncSdLineupInline(${lineup.id}, ${sourceId})" title="Sync lineup">
                            <i class="bi bi-arrow-repeat"></i>
                        </button>
                    </div>
                </div>
            `;
        }
        html += '</div>';
        container.innerHTML = html;
    } catch (error) {
        container.innerHTML = `<div class="alert alert-sm alert-danger mb-0">Error: ${error.message}</div>`;
    }
}

async function syncSdLineupInline(lineupId, sourceId) {
    const btn = event.target.closest('button');
    const originalHtml = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';
    
    try {
        const response = await fetch(`/api/epg/sd/lineups/${lineupId}/sync`, { method: 'POST' });
        const result = await response.json();
        
        if (response.ok) {
            await loadSdLineupsInline(sourceId);
            await loadSources();
            alert(`✓ Synced ${result.channels_synced || 0} channels!`);
        } else {
            alert('Error: ' + (result.error || 'Sync failed'));
            btn.disabled = false;
            btn.innerHTML = originalHtml;
        }
    } catch (error) {
        alert('Error: ' + error.message);
        btn.disabled = false;
        btn.innerHTML = originalHtml;
    }
}

async function showSourceMappings(sourceId, sourceName) {
    currentSourceMappings = {
        sourceId: sourceId,
        sourceName: sourceName,
        offset: 0,
        limit: 50,
        search: ''
    };
    
    document.getElementById('sourceMappingsModalTitle').textContent = `Channels using EPG from: ${sourceName}`;
    document.getElementById('sourceMappingsSearch').value = '';
    
    document.getElementById('sourceMappingsSearch').oninput = debounce(() => {
        currentSourceMappings.search = document.getElementById('sourceMappingsSearch').value;
        currentSourceMappings.offset = 0;
        loadSourceMappingsPage();
    }, 300);
    
    document.getElementById('mappings-prev-btn').onclick = () => {
        if (currentSourceMappings.offset > 0) {
            currentSourceMappings.offset -= currentSourceMappings.limit;
            loadSourceMappingsPage();
        }
    };
    
    document.getElementById('mappings-next-btn').onclick = () => {
        currentSourceMappings.offset += currentSourceMappings.limit;
        loadSourceMappingsPage();
    };
    
    if (sourceMappingsModal) sourceMappingsModal.show();
    await loadSourceMappingsPage();
}

async function loadSourceMappingsPage() {
    const container = document.getElementById('source-mappings-list');
    container.innerHTML = '<div class="text-center"><div class="spinner-border" role="status"></div></div>';
    
    try {
        let url = `/api/epg/sources/${currentSourceMappings.sourceId}/mappings?limit=${currentSourceMappings.limit}&offset=${currentSourceMappings.offset}`;
        if (currentSourceMappings.search) {
            url += `&search=${encodeURIComponent(currentSourceMappings.search)}`;
        }
        
        const response = await fetch(url);
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.error || 'Failed to load mappings');
        }
        
        renderSourceMappings(data);
        updateMappingsPagination(data.total, data.offset, data.limit);
    } catch (error) {
        container.innerHTML = `<div class="alert alert-danger">Error: ${error.message}</div>`;
    }
}

function renderSourceMappings(data) {
    const container = document.getElementById('source-mappings-list');
    
    if (!data.mappings || data.mappings.length === 0) {
        container.innerHTML = '<div class="alert alert-info">No channels are currently using EPG data from this source.</div>';
        return;
    }
    
    let html = '<div class="table-responsive"><table class="table table-sm table-striped">';
    html += `
        <thead>
            <tr>
                <th style="width: 35%">Channel</th>
                <th style="width: 35%">EPG Channel</th>
                <th>Category</th>
                <th>Match Type</th>
                <th>Confidence</th>
            </tr>
        </thead>
        <tbody>
    `;
    
    for (const m of data.mappings) {
        const confidenceClass = m.confidence >= 0.9 ? 'text-success' : m.confidence >= 0.7 ? 'text-warning' : 'text-danger';
        const confidencePct = Math.round(m.confidence * 100);
        
        const channelIcon = m.channel_icon 
            ? `<img src="${m.channel_icon}" style="max-height: 20px; max-width: 30px; margin-right: 5px;" onerror="this.style.display='none'">`
            : '';
        const epgIcon = m.epg_channel_icon
            ? `<img src="${m.epg_channel_icon}" style="max-height: 20px; max-width: 30px; margin-right: 5px;" onerror="this.style.display='none'">`
            : '';
        
        html += `
            <tr>
                <td>
                    ${channelIcon}
                    <span title="${m.channel_name}">${m.channel_clean_name || m.channel_name}</span>
                </td>
                <td>
                    ${epgIcon}
                    <span title="XMLTV ID: ${m.epg_channel_xmltv_id}">${m.epg_channel_name || m.epg_channel_xmltv_id}</span>
                </td>
                <td><small class="text-muted">${m.category_name || '-'}</small></td>
                <td><span class="badge bg-secondary">${m.mapping_type}</span></td>
                <td><span class="${confidenceClass}">${confidencePct}%</span></td>
            </tr>
        `;
    }
    
    html += '</tbody></table></div>';
    container.innerHTML = html;
}

function updateMappingsPagination(total, offset, limit) {
    const showingText = document.getElementById('mappings-showing-text');
    const prevBtn = document.getElementById('mappings-prev-btn');
    const nextBtn = document.getElementById('mappings-next-btn');
    
    const start = offset + 1;
    const end = Math.min(offset + limit, total);
    showingText.textContent = total > 0 ? `Showing ${start}-${end} of ${total}` : 'No mappings';
    
    prevBtn.disabled = offset === 0;
    nextBtn.disabled = (offset + limit) >= total;
}

async function loadCoverage() {
    const container = document.getElementById('coverage-summary');
    const content = document.getElementById('coverage-content');
    container.style.display = 'block';
    content.innerHTML = '<div class="text-center"><div class="spinner-border" role="status"></div></div>';
    
    try {
        const response = await fetch('/api/epg/coverage');
        const stats = await response.json();
        
        const coveragePercent = stats.total_channels > 0 
            ? ((stats.channels_with_epg_mapping / stats.total_channels) * 100).toFixed(1)
            : 0;
            
        content.innerHTML = `
            <div class="row">
                <div class="col-md-3 text-center">
                    <h3 class="text-primary">${stats.total_channels}</h3>
                    <small>Total Channels</small>
                </div>
                <div class="col-md-3 text-center">
                    <h3 class="text-success">${stats.channels_with_epg_mapping}</h3>
                    <small>With EPG Mapping</small>
                </div>
                <div class="col-md-3 text-center">
                    <h3 class="text-info">${stats.epg_sources}</h3>
                    <small>EPG Sources</small>
                </div>
                <div class="col-md-3 text-center">
                    <h3 class="text-warning">${coveragePercent}%</h3>
                    <small>Coverage</small>
                </div>
            </div>
            <div class="progress mt-3" style="height: 25px;">
                <div class="progress-bar bg-success" style="width: ${coveragePercent}%">${coveragePercent}% covered</div>
            </div>
        `;
    } catch (error) {
        content.innerHTML = `<div class="alert alert-danger">Error loading coverage: ${error.message}</div>`;
    }
}
