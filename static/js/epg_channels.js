// ============================================================================
// EPG Channels
// ============================================================================

let epgChannelsState = {
    offset: 0,
    total: 0,
    limit: 100,
    loading: false,
    sourceId: '',
    search: ''
};

async function loadEpgChannels() {
    const sourceSelect = document.getElementById('channelSourceSelect');
    const searchInput = document.getElementById('channelSearch');
    const container = document.getElementById('channels-list');
    
    // Return early if elements don't exist (feature not available on this page)
    if (!sourceSelect || !searchInput || !container) {
        return;
    }
    
    const sourceId = sourceSelect.value;
    const search = searchInput.value;
    
    epgChannelsState = {
        offset: 0,
        total: 0,
        limit: 100,
        loading: false,
        sourceId: sourceId,
        search: search
    };
    
    if (!sourceId && !search) {
        container.innerHTML = '<div class="text-center text-muted py-4">Select a source or search to view EPG channels</div>';
        return;
    }
    
    container.innerHTML = '<div class="text-center"><div class="spinner-border" role="status"></div></div>';
    
    try {
        let url = `/api/epg/channels?limit=${epgChannelsState.limit}&offset=0`;
        if (sourceId) url += `&source_id=${sourceId}`;
        if (search) url += `&search=${encodeURIComponent(search)}`;
        
        const response = await fetch(url);
        const data = await response.json();
        
        if (data.channels.length === 0) {
            container.innerHTML = '<div class="alert alert-info">No EPG channels found</div>';
            return;
        }
        
        epgChannelsState.total = data.total;
        epgChannelsState.offset = data.channels.length;
        
        let html = `<p class="text-muted mb-2" id="epg-channels-count">Showing ${data.channels.length} of ${data.total} channels</p>`;
        html += '<div class="table-responsive" id="epg-channels-table-container" style="max-height: 600px; overflow-y: auto;">';
        html += '<table class="table table-striped table-sm">';
        html += `
            <thead style="position: sticky; top: 0; background: white; z-index: 1;">
                <tr>
                    <th>Channel ID</th>
                    <th>Display Name</th>
                    <th>Icon</th>
                    <th>Programs</th>
                    <th>Mappings</th>
                </tr>
            </thead>
            <tbody id="epg-channels-tbody">
        `;
        
        for (const ch of data.channels) {
            html += renderEpgChannelRow(ch);
        }
        
        html += '</tbody></table>';
        
        if (epgChannelsState.offset < epgChannelsState.total) {
            html += '<div id="epg-channels-loader" class="text-center py-3"><div class="spinner-border spinner-border-sm" role="status"></div> Loading more...</div>';
        }
        
        html += '</div>';
        container.innerHTML = html;
        
        const tableContainer = document.getElementById('epg-channels-table-container');
        tableContainer.addEventListener('scroll', handleEpgChannelsScroll);
        
    } catch (error) {
        container.innerHTML = `<div class="alert alert-danger">Error: ${error.message}</div>`;
    }
}

function renderEpgChannelRow(ch) {
    return `
        <tr>
            <td><code>${ch.channel_id}</code></td>
            <td>${ch.display_name || '-'}</td>
            <td>${ch.icon_url ? `<img src="${ch.icon_url}" style="max-height: 24px;">` : '-'}</td>
            <td>${ch.program_count || 0}</td>
            <td>${ch.mapping_count || 0}</td>
        </tr>
    `;
}

async function handleEpgChannelsScroll(event) {
    const container = event.target;
    const scrollBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
    
    if (scrollBottom < 100 && !epgChannelsState.loading && epgChannelsState.offset < epgChannelsState.total) {
        await loadMoreEpgChannels();
    }
}

async function loadMoreEpgChannels() {
    if (epgChannelsState.loading || epgChannelsState.offset >= epgChannelsState.total) {
        return;
    }
    
    epgChannelsState.loading = true;
    const loader = document.getElementById('epg-channels-loader');
    if (loader) loader.style.display = 'block';
    
    try {
        let url = `/api/epg/channels?limit=${epgChannelsState.limit}&offset=${epgChannelsState.offset}`;
        if (epgChannelsState.sourceId) url += `&source_id=${epgChannelsState.sourceId}`;
        if (epgChannelsState.search) url += `&search=${encodeURIComponent(epgChannelsState.search)}`;
        
        const response = await fetch(url);
        const data = await response.json();
        
        if (data.channels.length > 0) {
            const tbody = document.getElementById('epg-channels-tbody');
            let html = '';
            for (const ch of data.channels) {
                html += renderEpgChannelRow(ch);
            }
            tbody.insertAdjacentHTML('beforeend', html);
            
            epgChannelsState.offset += data.channels.length;
            
            const countEl = document.getElementById('epg-channels-count');
            if (countEl) {
                countEl.textContent = `Showing ${epgChannelsState.offset} of ${epgChannelsState.total} channels`;
            }
        }
        
        if (epgChannelsState.offset >= epgChannelsState.total && loader) {
            loader.style.display = 'none';
        }
        
    } catch (error) {
        console.error('Error loading more EPG channels:', error);
    } finally {
        epgChannelsState.loading = false;
    }
}
