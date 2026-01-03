// ============================================================================
// Manual EPG Mapping
// ============================================================================

let epgSearchState = { search: '', offset: 0, hasMore: true, loading: false };
const EPG_CHANNELS_PER_PAGE = 20;

function showManualMappingModal(channelId, channelName) {
    document.getElementById('manualMappingChannelId').value = channelId;
    document.getElementById('manualMappingChannel').textContent = channelName;
    document.getElementById('manualMappingEpgSearch').value = '';
    document.getElementById('manualMappingEpgChannel').value = '';
    document.getElementById('epgChannelList').innerHTML = '<div class="list-group-item text-muted">Type to search EPG channels...</div>';
    document.getElementById('manualMappingTimeOffset').value = '0';
    document.getElementById('selectedEpgChannel').style.display = 'none';
    epgSearchState = { search: '', offset: 0, hasMore: true, loading: false };
    if (manualMappingModal) manualMappingModal.show();
}

function clearSelectedEpgChannel() {
    document.getElementById('manualMappingEpgChannel').value = '';
    document.getElementById('selectedEpgChannel').style.display = 'none';
    document.querySelectorAll('#epgChannelList .list-group-item').forEach(item => {
        item.classList.remove('active');
    });
}

function selectEpgChannel(id, displayName, channelId) {
    document.getElementById('manualMappingEpgChannel').value = id;
    document.getElementById('selectedEpgChannelName').textContent = `${displayName} (${channelId})`;
    document.getElementById('selectedEpgChannel').style.display = 'block';
    document.querySelectorAll('#epgChannelList .list-group-item').forEach(item => {
        item.classList.remove('active');
        if (item.dataset.id === String(id)) {
            item.classList.add('active');
        }
    });
}

async function searchEpgChannels(resetResults = true) {
    const search = document.getElementById('manualMappingEpgSearch').value.trim();
    const sourceId = document.getElementById('manualMappingEpgSource').value;
    
    if (resetResults) {
        epgSearchState = { search: search, offset: 0, hasMore: true, loading: false };
        document.getElementById('epgChannelList').innerHTML = '';
        document.getElementById('manualMappingEpgChannel').value = '';
        document.getElementById('selectedEpgChannel').style.display = 'none';
    }
    
    if (search.length < 2) {
        document.getElementById('epgChannelList').innerHTML = '<div class="list-group-item text-muted">Type at least 2 characters to search...</div>';
        return;
    }
    
    if (epgSearchState.loading || !epgSearchState.hasMore) return;
    
    epgSearchState.loading = true;
    const loader = document.getElementById('epgChannelLoader');
    loader.style.display = 'block';
    
    try {
        let url = `/api/epg/channels?search=${encodeURIComponent(search)}&limit=${EPG_CHANNELS_PER_PAGE}&offset=${epgSearchState.offset}`;
        if (sourceId) url += `&source_id=${sourceId}`;
        const response = await fetch(url);
        const data = await response.json();
        
        const list = document.getElementById('epgChannelList');
        
        if (data.channels.length === 0 && epgSearchState.offset === 0) {
            list.innerHTML = '<div class="list-group-item text-muted">No channels found. Try different search terms.</div>';
            epgSearchState.hasMore = false;
            loader.style.display = 'none';
            epgSearchState.loading = false;
            return;
        }
        
        data.channels.forEach(ch => {
            const item = document.createElement('button');
            item.type = 'button';
            item.className = 'list-group-item list-group-item-action';
            item.dataset.id = ch.id;
            item.innerHTML = `
                <div class="d-flex justify-content-between align-items-center">
                    <div>
                        <strong>${escapeHtml(ch.display_name)}</strong>
                        <small class="text-muted ms-2">(${escapeHtml(ch.channel_id)})</small>
                    </div>
                    <small class="text-muted">${ch.program_count || 0} programs</small>
                </div>
            `;
            item.onclick = () => selectEpgChannel(ch.id, ch.display_name, ch.channel_id);
            list.appendChild(item);
        });
        
        epgSearchState.offset += data.channels.length;
        epgSearchState.hasMore = epgSearchState.offset < data.total;
        
    } catch (error) {
        console.error('Error searching EPG channels:', error);
        document.getElementById('epgChannelList').innerHTML = '<div class="list-group-item text-danger">Error loading channels</div>';
    } finally {
        loader.style.display = 'none';
        epgSearchState.loading = false;
    }
}

function setupEpgChannelScroll() {
    const container = document.getElementById('epgChannelListContainer');
    if (container) {
        container.addEventListener('scroll', () => {
            const scrollBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
            if (scrollBottom < 50 && epgSearchState.hasMore && !epgSearchState.loading) {
                searchEpgChannels(false);
            }
        });
    }
}

async function saveManualMapping() {
    const channelId = document.getElementById('manualMappingChannelId').value;
    const epgChannelId = document.getElementById('manualMappingEpgChannel').value;
    const timeOffset = parseInt(document.getElementById('manualMappingTimeOffset').value) || 0;
    
    if (!channelId || !epgChannelId) {
        alert('Please select an EPG channel');
        return;
    }
    
    try {
        const response = await fetch('/api/epg/mappings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                channel_id: parseInt(channelId),
                epg_channel_id: parseInt(epgChannelId),
                time_offset_hours: timeOffset
            })
        });
        
        if (response.ok) {
            const mapping = await response.json();
            manualMappingModal.hide();
            
            const row = document.querySelector(`tr[data-channel-id="${channelId}"]`);
            if (row) {
                const cells = row.querySelectorAll('td');
                if (cells.length >= 4) {
                    cells[2].innerHTML = `<span class="text-success">${mapping.epg_display_name || 'EPG #' + epgChannelId}</span>`;
                    cells[3].innerHTML = '<span class="badge bg-primary">Manual</span> 100%';
                }
                const actionsDiv = cells[4].querySelector('.btn-group');
                if (actionsDiv) {
                    const createBtn = actionsDiv.querySelector('button[onclick^="showManualMappingModal"]');
                    if (createBtn) {
                        const deleteBtn = document.createElement('button');
                        deleteBtn.className = 'btn btn-outline-danger btn-sm';
                        deleteBtn.setAttribute('onclick', `deleteMapping(${mapping.id}, ${channelId})`);
                        deleteBtn.setAttribute('title', 'Delete mapping');
                        deleteBtn.innerHTML = '<i class="bi bi-trash"></i>';
                        createBtn.replaceWith(deleteBtn);
                    }
                }
            }
            showToast('Mapping created', 'success');
        } else {
            const error = await response.json();
            showToast('Error: ' + (error.error || 'Failed to create mapping'), 'error');
        }
    } catch (error) {
        showToast('Error: ' + error.message, 'error');
    }
}
