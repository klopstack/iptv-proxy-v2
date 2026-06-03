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

/** Live sync rows from GET /api/sync/epg/status (source_id -> snapshot) */
let epgSyncStatusById = {};

/* global AccountSelect, escapeHtml */

async function loadAccounts() {
    try {
        accounts = await AccountSelect.fetchAccounts();
        AccountSelect.populateAccountSelects(
            ['mappingAccountSelect', 'matchAccountSelect'],
            accounts,
            { preserveFirstOption: true },
        );
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
        refreshSourceRowProgress();
    } catch (error) {
        document.getElementById('sources-list').innerHTML = `
            <div class="alert alert-danger">Error loading EPG sources: ${escapeHtml(error.message)}</div>
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
                const option = document.createElement('option');
                option.value = s.id;
                option.dataset.sourceType = s.source_type;
                option.textContent = `${s.name} (${s.source_type})`;
                select.appendChild(option);
            });
            select.dispatchEvent(new Event('change'));
        }
    });
}

function onEpgSourcesPageProgress(statusSources) {
    if (!window.EpgSyncProgress) return;
    epgSyncStatusById = window.EpgSyncProgress.indexSourcesById(statusSources);
    refreshSourceRowProgress();
}

function refreshSourceRowProgress() {
    if (!window.EpgSyncProgress) return;
    document.querySelectorAll('tr[data-epg-source-id]').forEach((row) => {
        const sourceId = parseInt(row.dataset.epgSourceId, 10);
        const cell = row.querySelector('.epg-sync-status-cell');
        if (!cell) return;
        const source = sources.find((s) => s.id === sourceId);
        if (source) {
            cell.innerHTML = renderSourceStatusCell(source);
        }
    });
}

function renderSourceStatusCell(source) {
    const live = epgSyncStatusById[source.id];
    if (live && (window.EpgSyncProgress.isLiveSyncStatus(live) || live.sync_phase === 'error')) {
        return window.EpgSyncProgress.renderSourceRowStatusHtml(live);
    }

    if (source.last_sync_status === 'success') {
        return '<span class="badge bg-success">Success</span>';
    }
    if (source.last_sync_status === 'partial') {
        const msg = source.last_sync_message
            ? `<div class="small text-muted mt-1">${escapeHtml(source.last_sync_message)}</div>`
            : '';
        return `<span class="badge bg-warning text-dark">Partial</span>${msg}`;
    }
    if (source.last_sync_status === 'error') {
        const msg = source.last_sync_message
            ? `<div class="small text-muted mt-1">${escapeHtml(source.last_sync_message)}</div>`
            : '';
        return `<span class="badge bg-danger">Error</span>${msg}`;
    }
    if (source.last_sync_status == null || source.last_sync_status === undefined) {
        return '<span class="badge bg-secondary">Never synced</span>';
    }
    return `<span class="badge bg-secondary">${escapeHtml(source.last_sync_status)}</span>`;
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
        const isLegacyProvider = isLegacyProviderSource(source);
        const statusBadge = renderSourceStatusCell(source);

        const sourceInfo = source.source_type === 'provider' 
            ? escapeHtml(source.account_name || `Account ${source.account_id}`)
            : source.source_type === 'xmltv_url'
            ? `<small class="text-muted">${escapeHtml((source.url?.substring(0, 40) || 'No URL') + '...')}</small>`
            : source.source_type === 'schedules_direct'
            ? '<i class="bi bi-broadcast-pin"></i> SD'
            : source.source_type === 'xmltv_grabber'
            ? `<i class="bi bi-terminal"></i> ${escapeHtml(source.xmltv_grabber || 'Grabber')}`
            : '-';

        const usedCount = source.used_mapping_count || 0;
        const inUseHtml = usedCount > 0
            ? `<a href="#" onclick="showSourceMappings(${source.id}, '${escapeJsSingleQuoted(source.name)}'); return false;" class="text-decoration-none">
                <span class="badge bg-primary">${usedCount}</span>
               </a>`
            : '<span class="badge bg-secondary">0</span>';
            
        html += `
            <tr data-epg-source-id="${source.id}">
                <td>
                    ${escapeHtml(source.name)}
                    ${!source.enabled ? '<span class="badge bg-secondary ms-2">Disabled</span>' : ''}
                    ${source.source_type === 'schedules_direct' ? '<button class="btn btn-sm btn-link p-0 ms-2" onclick="toggleSdLineups(' + source.id + ')" title="Show/Hide Lineups" id="sd-toggle-' + source.id + '"><i class="bi bi-chevron-down"></i></button>' : ''}
                </td>
                <td>
                    <span class="badge bg-info">${escapeHtml(source.source_type)}</span>
                    ${isLegacyProvider ? '<span class="badge bg-warning text-dark ms-1">Legacy</span>' : ''}
                </td>
                <td>${sourceInfo}</td>
                <td>${source.channel_count || 0}</td>
                <td>${inUseHtml}</td>
                <td>${source.last_sync ? formatLocalDateTime(source.last_sync) : 'Never'}</td>
                <td class="epg-sync-status-cell">${statusBadge}</td>
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
    const visibility = getSourceTypeFieldVisibility(type);

    document.getElementById('xmltvUrlFields').style.display = visibility.xmltvUrlFields ? 'block' : 'none';
    document.getElementById('sdFields').style.display = visibility.sdFields ? 'block' : 'none';
    document.getElementById('grabberFields').style.display = visibility.grabberFields ? 'block' : 'none';
    document.getElementById('ppvFields').style.display = visibility.ppvFields ? 'block' : 'none';
    
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
    
    if (data.source_type === 'xmltv_url') {
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
        document.getElementById('sourceType').disabled = true;
    } else {
        document.getElementById('sourceType').disabled = false;
    }

    if (source.source_type === 'xmltv_url') {
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

    const source = sources.find((s) => s.id === id);
    if (source && source.source_type === 'schedules_direct') {
        alert('⚠️ Schedules Direct Sync\n\nSchedules Direct sources are synced per-lineup.\n\nPlease go to the "Schedules Direct" tab and sync individual lineups.');
        btn.disabled = false;
        btn.innerHTML = originalHtml;
        return;
    }

    window.EpgSyncProgress?.poller?.start(onEpgSourcesPageProgress);

    try {
        const response = await fetch(`/api/epg/sources/${id}/sync`, { method: 'POST' });
        const result = await response.json();

        if (response.status === 409) {
            alert('Sync already in progress for this source. Wait for it to finish, or use Force sync on the Settings page (Sync EPG).');
        } else if (response.ok) {
            await loadSources();
            alert(`✓ Synced! ${result.message}`);
        } else {
            alert('Error: ' + (result.error || 'Sync failed'));
        }
    } catch (error) {
        alert('Error syncing: ' + error.message);
    } finally {
        await window.EpgSyncProgress?.poller?.pollOnce();
        btn.disabled = false;
        btn.innerHTML = originalHtml;
    }
}

function initEpgSourcesProgressPolling() {
    if (!window.EpgSyncProgress?.poller) return;
    window.EpgSyncProgress.poller.start(onEpgSourcesPageProgress);
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
    toggleSdLineups(sourceId);
}

async function loadSdLineupsInline(sourceId) {
    const container = document.getElementById(`sd-lineups-content-${sourceId}`);
    container.innerHTML = '<div class="text-center"><div class="spinner-border spinner-border-sm" role="status"></div></div>';
    
    try {
        const response = await fetch(`/api/epg/sd/lineups?source_id=${sourceId}`);
        const result = await response.json();
        
        if (result.error || result.success === false) {
            container.innerHTML = `<div class="alert alert-sm alert-danger mb-0">${escapeHtml(result.error || 'Failed to load lineups')}</div>`;
            return;
        }
        
        const lineups = result.lineups || [];
        
        if (lineups.length === 0) {
            container.innerHTML = `
                <div class="text-muted text-center py-2">
                    <small>No lineups configured.</small>
                    <div class="mt-2">
                        <button class="btn btn-sm btn-outline-primary" onclick="openSearchLineupsModal(${sourceId})">
                            <i class="bi bi-search"></i> Search Lineups
                        </button>
                    </div>
                </div>
            `;
            return;
        }

        let statuses = {};
        try {
            const statusResp = await fetch(`/api/epg/sd/lineups/status?source_id=${sourceId}`);
            const statusJson = await statusResp.json();
            if (statusResp.ok && statusJson && Array.isArray(statusJson.statuses)) {
                for (const st of statusJson.statuses) statuses[st.lineup_id] = st;
            }
        } catch (_) {}

        let html = `
            <div class="d-flex justify-content-end mb-2 px-3">
                <button class="btn btn-sm btn-outline-primary" onclick="openSearchLineupsModal(${sourceId})">
                    <i class="bi bi-search"></i> Search Lineups
                </button>
            </div>
        `;
        html += '<p class="small text-muted mb-2 px-3">Lineup sync shows per-lineup progress below. Source-level sync progress is separate.</p>';
        html += '<div class="list-group list-group-flush">';
        for (const lineup of lineups) {
            const st = statuses[lineup.id];
            const badge = st?.sync_in_progress
                ? '<span class="badge bg-primary ms-2">Syncing</span>'
                : st?.last_sync_status === 'error'
                    ? '<span class="badge bg-danger ms-2">Error</span>'
                    : st?.last_sync_status === 'success'
                        ? '<span class="badge bg-success ms-2">OK</span>'
                        : '';
            const detail = st?.progress?.message ? `<br><small class="text-muted">${escapeHtml(st.progress.message)}</small>` : '';
            html += `
                <div class="list-group-item px-3 py-2 d-flex justify-content-between align-items-center">
                    <div>
                        <strong>${escapeHtml(lineup.name || lineup.lineup_id)}</strong>${badge}
                        ${lineup.location ? `<br><small class="text-muted">${escapeHtml(lineup.location)}</small>` : ''}
                        <br><small class="text-muted">${lineup.channel_count || 0} channels</small>${detail}
                        ${lineup.last_sync ? '<small class="text-muted"> | Last sync: ' + formatLocalDateTime(lineup.last_sync) + '</small>' : ''}
                    </div>
                    <div class="btn-group btn-group-sm">
                        <button class="btn btn-sm btn-outline-secondary" onclick="viewStations(${lineup.id}, '${escapeJsSingleQuoted(lineup.name || lineup.lineup_id)}')" title="View stations">
                            <i class="bi bi-list"></i>
                        </button>
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
        container.innerHTML = `<div class="alert alert-sm alert-danger mb-0">Error: ${escapeHtml(error.message)}</div>`;
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
    if (!document.getElementById('sourceMappingsModal')) {
        showToast('Source mappings viewer is not available on this page', 'error');
        return;
    }

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
        container.innerHTML = `<div class="alert alert-danger">Error: ${escapeHtml(error.message)}</div>`;
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
            ? `<img src="${escapeHtml(m.channel_icon)}" style="max-height: 20px; max-width: 30px; margin-right: 5px;" onerror="this.style.display='none'">`
            : '';
        const epgIcon = m.epg_channel_icon
            ? `<img src="${escapeHtml(m.epg_channel_icon)}" style="max-height: 20px; max-width: 30px; margin-right: 5px;" onerror="this.style.display='none'">`
            : '';
        
        html += `
            <tr>
                <td>
                    ${channelIcon}
                    <span title="${escapeHtml(m.channel_name)}">${escapeHtml(m.channel_clean_name || m.channel_name)}</span>
                </td>
                <td>
                    ${epgIcon}
                    <span title="XMLTV ID: ${escapeHtml(m.epg_channel_xmltv_id)}">${escapeHtml(m.epg_channel_name || m.epg_channel_xmltv_id)}</span>
                </td>
                <td><small class="text-muted">${escapeHtml(m.category_name || '-')}</small></td>
                <td><span class="badge bg-secondary">${escapeHtml(m.mapping_type)}</span></td>
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
    if (!showingText || !prevBtn || !nextBtn) return;

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
        content.innerHTML = `<div class="alert alert-danger">Error loading coverage: ${escapeHtml(error.message)}</div>`;
    }
}
