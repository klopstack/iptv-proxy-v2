// ============================================================================
// Schedules Direct
// ============================================================================

async function loadSdStatus() {
    const container = document.getElementById('sd-status-content');
    
    try {
        const response = await fetch('/api/epg/sd/status');
        const status = await response.json();
        
        if (status.status === 'online') {
            container.innerHTML = `
                <div class="alert alert-success mb-0">
                    <i class="bi bi-check-circle-fill"></i> Service is <strong>Online</strong>
                    <br><small>Message: ${status.message || 'All systems operational'}</small>
                </div>
            `;
        } else {
            container.innerHTML = `
                <div class="alert alert-warning mb-0">
                    <i class="bi bi-exclamation-triangle-fill"></i> Service status: <strong>${status.status || 'Unknown'}</strong>
                    <br><small>${status.message || ''}</small>
                </div>
            `;
        }
    } catch (error) {
        container.innerHTML = `
            <div class="alert alert-secondary mb-0">
                <i class="bi bi-question-circle"></i> Could not check SD status: ${error.message}
            </div>
        `;
    }
}

async function testSdCredentials() {
    const username = document.getElementById('sdUsername').value;
    const password = document.getElementById('sdPassword').value;
    const resultDiv = document.getElementById('sdCredentialsResult');
    
    if (!username || !password) {
        alert('Please enter credentials first');
        return;
    }
    
    resultDiv.style.display = 'block';
    resultDiv.innerHTML = '<div class="alert alert-secondary"><span class="spinner-border spinner-border-sm"></span> Testing...</div>';
    
    try {
        const response = await fetch('/api/epg/sd/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });
        
        const result = await response.json();
        
        if (result.success) {
            resultDiv.innerHTML = `
                <div class="alert alert-success">
                    <i class="bi bi-check-circle"></i> Credentials valid!
                    ${result.account_info ? `<br><small>Account: ${JSON.stringify(result.account_info)}</small>` : ''}
                </div>
            `;
        } else {
            resultDiv.innerHTML = `<div class="alert alert-danger"><i class="bi bi-x-circle"></i> ${result.error || 'Invalid credentials'}</div>`;
        }
    } catch (error) {
        resultDiv.innerHTML = `<div class="alert alert-danger">Error: ${error.message}</div>`;
    }
}

async function loadSdLineups() {
    const sourceId = document.getElementById('sdSourceSelect').value;
    const container = document.getElementById('sd-lineups-list');
    const searchBtn = document.getElementById('searchLineupsModalBtn');
    
    if (!sourceId) {
        searchBtn.disabled = true;
        searchBtn.title = 'Select a Schedules Direct source first';
        container.innerHTML = '<div class="text-center text-muted py-3">Select a Schedules Direct source to view lineups</div>';
        return;
    }
    
    container.innerHTML = '<div class="text-center"><div class="spinner-border" role="status"></div></div>';
    
    try {
        const response = await fetch(`/api/epg/sd/lineups?source_id=${sourceId}`);
        const result = await response.json();
        
        if (result.error || result.success === false) {
            container.innerHTML = `<div class="alert alert-danger">${result.error || 'Failed to load lineups'}</div>`;
            searchBtn.disabled = true;
            return;
        }
        
        const lineups = result.lineups || [];
        const accountLineups = result.account_lineups || 0;
        const maxLineups = result.max_lineups || 4;
        const atLimit = accountLineups >= maxLineups;
        
        if (atLimit) {
            searchBtn.disabled = true;
            searchBtn.title = `Lineup limit reached (${accountLineups}/${maxLineups}). Remove a lineup to add more.`;
        } else {
            searchBtn.disabled = false;
            searchBtn.title = `Search for lineups to add (${accountLineups}/${maxLineups} used)`;
        }
        
        let html = `
            <div class="alert ${atLimit ? 'alert-warning' : 'alert-info'} mb-3">
                <i class="bi bi-${atLimit ? 'exclamation-triangle' : 'info-circle'}"></i>
                <strong>SD Account Lineups:</strong> ${accountLineups} of ${maxLineups} used
                ${atLimit ? '<br><small>Remove a lineup from your SD account to add more.</small>' : ''}
            </div>
        `;
        
        if (lineups.length === 0) {
            if (atLimit) {
                html += `
                    <div class="alert alert-secondary">
                        No lineups added to this source yet. Your SD account has ${accountLineups} lineup(s) 
                        that may be added to other sources or managed via schedulesdirect.org.
                    </div>
                `;
            } else {
                html += `
                    <div class="alert alert-secondary">
                        No lineups added yet. Use "Search Lineups" to find and add lineups for your area.
                    </div>
                `;
            }
            container.innerHTML = html;
            return;
        }
        
        html += '<div class="list-group">';
        for (const lineup of lineups) {
            html += `
                <div class="list-group-item">
                    <div class="d-flex justify-content-between align-items-center">
                        <div>
                            <strong>${lineup.name || lineup.lineup_id}</strong>
                            <br><small class="text-muted">${lineup.location || ''} - ${lineup.lineup_type || ''}</small>
                            <br><small>${lineup.channel_count} channels</small>
                        </div>
                        <div class="btn-group btn-group-sm">
                            <button class="btn btn-outline-primary" onclick="viewStations(${lineup.id}, '${escapeHtml(lineup.name || lineup.lineup_id)}')">
                                <i class="bi bi-list"></i> Stations
                            </button>
                            <button class="btn btn-outline-success" onclick="syncSdLineup(${lineup.id})">
                                <i class="bi bi-arrow-repeat"></i> Sync
                            </button>
                            <button class="btn btn-outline-danger" onclick="removeSdLineup(${lineup.id})">
                                <i class="bi bi-trash"></i>
                            </button>
                        </div>
                    </div>
                </div>
            `;
        }
        html += '</div>';
        container.innerHTML = html;
    } catch (error) {
        container.innerHTML = `<div class="alert alert-danger">Error: ${error.message}</div>`;
    }
}

async function searchLineups() {
    const sourceId = document.getElementById('sdSourceSelect').value;
    if (!sourceId) {
        alert('Please select a Schedules Direct source first');
        return;
    }
    
    const country = document.getElementById('searchCountry').value;
    const postalcode = document.getElementById('searchPostalCode').value;
    const container = document.getElementById('lineupSearchResults');
    
    if (!postalcode) {
        alert('Please enter a postal code');
        return;
    }
    
    container.innerHTML = '<div class="text-center"><div class="spinner-border" role="status"></div></div>';
    
    try {
        const response = await fetch(`/api/epg/sd/lineups/search?source_id=${sourceId}&country=${country}&postalcode=${postalcode}`);
        const result = await response.json();
        
        if (!result.success) {
            container.innerHTML = `<div class="alert alert-danger">${result.error || 'Search failed'}</div>`;
            return;
        }
        
        const lineups = Array.isArray(result.lineups) ? result.lineups : [];
        
        if (lineups.length === 0) {
            container.innerHTML = '<div class="alert alert-info">No lineups found for this location</div>';
            return;
        }
        
        let html = '<div class="list-group">';
        for (const lineup of lineups) {
            html += `
                <div class="list-group-item d-flex justify-content-between align-items-center">
                    <div>
                        <strong>${lineup.name || lineup.lineup}</strong>
                        <br><small class="text-muted">${lineup.location || ''}</small>
                        <br><small>Type: ${lineup.type || lineup.transport || '-'}</small>
                    </div>
                    <button class="btn btn-sm btn-primary" onclick="addSdLineup('${lineup.lineup}', '${escapeHtml(lineup.name || '')}', '${escapeHtml(lineup.location || '')}', '${lineup.type || lineup.transport || ''}')">
                        <i class="bi bi-plus"></i> Add
                    </button>
                </div>
            `;
        }
        html += '</div>';
        container.innerHTML = html;
    } catch (error) {
        container.innerHTML = `<div class="alert alert-danger">Error: ${error.message}</div>`;
    }
}

async function addSdLineup(lineupId, name, location, type) {
    const sourceId = document.getElementById('sdSourceSelect').value;
    
    try {
        const response = await fetch('/api/epg/sd/lineups?sync=true', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                source_id: parseInt(sourceId),
                lineup_id: lineupId,
                name: name,
                location: location,
                lineup_type: type
            })
        });
        
        const result = await response.json();
        
        if (response.ok) {
            searchLineupModal.hide();
            loadSdLineups();
            alert(`✓ Lineup added! ${result.message}`);
        } else {
            if (result.limit_reached) {
                alert(`⚠️ Lineup limit reached!\n\nYour Schedules Direct account allows a maximum of ${result.max_lineups} lineups.\n\nYou currently have ${result.current_count} lineup(s). Please remove a lineup before adding a new one.`);
            } else {
                alert('Error: ' + (result.error || 'Failed to add lineup'));
            }
            loadSdLineups();
        }
    } catch (error) {
        alert('Error: ' + error.message);
    }
}

async function syncSdLineup(lineupId) {
    const btn = event.target.closest('button');
    const originalHtml = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';
    
    try {
        const response = await fetch(`/api/epg/sd/lineups/${lineupId}/sync`, { method: 'POST' });
        const result = await response.json();
        
        if (response.ok) {
            loadSdLineups();
            const msg = result.message || `Synced ${(result.channels_synced || 0) + (result.channels_updated || 0)} channels`;
            alert(`✓ ${msg}`);
        } else {
            alert('Error: ' + (result.error || 'Sync failed'));
        }
    } catch (error) {
        alert('Error: ' + error.message);
    } finally {
        btn.disabled = false;
        btn.innerHTML = originalHtml;
    }
}

async function removeSdLineup(lineupId) {
    if (!confirm('Remove this lineup and all its stations?')) return;
    
    try {
        const response = await fetch(`/api/epg/sd/lineups/${lineupId}`, { method: 'DELETE' });
        if (response.ok) {
            loadSdLineups();
        } else {
            const error = await response.json();
            alert('Error: ' + (error.error || 'Failed to remove lineup'));
        }
    } catch (error) {
        alert('Error: ' + error.message);
    }
}

let currentStations = [];

async function viewStations(lineupId, lineupName) {
    document.getElementById('sdStationsModalTitle').textContent = `Stations: ${lineupName}`;
    document.getElementById('stationSearch').value = '';
    const container = document.getElementById('sd-stations-list');
    container.innerHTML = '<div class="text-center"><div class="spinner-border" role="status"></div></div>';
    if (sdStationsModal) sdStationsModal.show();
    
    try {
        const response = await fetch(`/api/epg/sd/lineups/${lineupId}/stations`);
        const data = await response.json();
        currentStations = data.stations || [];
        renderStations(currentStations);
    } catch (error) {
        container.innerHTML = `<div class="alert alert-danger">Error: ${error.message}</div>`;
    }
}

function filterStations() {
    const search = document.getElementById('stationSearch').value.toLowerCase();
    const filtered = currentStations.filter(s => 
        (s.callsign || '').toLowerCase().includes(search) ||
        (s.name || '').toLowerCase().includes(search) ||
        (s.channel_number || '').toString().includes(search)
    );
    renderStations(filtered);
}

function renderStations(stations) {
    const container = document.getElementById('sd-stations-list');
    
    if (stations.length === 0) {
        container.innerHTML = '<div class="text-center text-muted py-3">No stations found</div>';
        return;
    }
    
    let html = '<table class="table table-striped table-sm"><thead><tr>';
    html += '<th>Ch #</th><th>Callsign</th><th>Name</th><th>Affiliate</th><th>Logo</th>';
    html += '</tr></thead><tbody>';
    
    for (const s of stations) {
        html += `
            <tr>
                <td>${s.channel_number || '-'}</td>
                <td><strong>${s.callsign || '-'}</strong></td>
                <td>${s.name || '-'}</td>
                <td>${s.affiliate || '-'}</td>
                <td>${s.logo_url ? `<img src="${s.logo_url}" style="max-height: 24px;">` : '-'}</td>
            </tr>
        `;
    }
    
    html += '</tbody></table>';
    container.innerHTML = html;
}
