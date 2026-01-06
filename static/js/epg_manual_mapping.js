// ============================================================================
// Manual EPG Mapping - Enhanced with Program Search and Preview
// ============================================================================

/* global showToast, escapeHtml, manualMappingModal, mpegts */

let epgSearchState = { search: '', offset: 0, hasMore: true, loading: false };
let currentSearchMode = 'channel'; // 'channel' or 'program'
let currentOnlyFilter = false;
let channelPreviewActive = false;
let channelPreviewPlayer = null;

const EPG_CHANNELS_PER_PAGE = 20;

async function populateEpgSourcesForManualMapping() {
    const sourceSelect = document.getElementById('manualMappingEpgSource');
    if (!sourceSelect) return;
    
    try {
        const response = await fetch('/api/epg/sources');
        const sourcesData = await response.json();
        const sourcesList = Array.isArray(sourcesData) ? sourcesData : (sourcesData.sources || []);
        
        sourceSelect.innerHTML = '<option value="">All Sources</option>';
        for (const source of sourcesList) {
            const option = document.createElement('option');
            option.value = source.id;
            option.textContent = `${source.name} (${source.source_type || source.type})`;
            sourceSelect.appendChild(option);
        }
    } catch (error) {
        console.error('Error loading EPG sources:', error);
        sourceSelect.innerHTML = '<option value="">Error loading sources</option>';
    }
}

// Track edit mode state
let isEditMode = false;
let currentMappingId = null;

function showManualMappingModal(channelId, channelName, accountId, streamId, existingMapping = null) {
    document.getElementById('manualMappingChannelId').value = channelId;
    document.getElementById('manualMappingChannel').textContent = channelName;
    document.getElementById('manualMappingAccountId').value = accountId || '';
    document.getElementById('manualMappingStreamId').value = streamId || '';
    document.getElementById('manualMappingEpgSearch').value = '';
    document.getElementById('manualMappingEpgChannel').value = '';
    document.getElementById('epgChannelList').innerHTML = '<div class="list-group-item text-muted">Type to search EPG channels...</div>';
    document.getElementById('selectedEpgChannel').style.display = 'none';
    document.getElementById('resultsCount').textContent = '';
    
    // Reset schedule display
    document.getElementById('epgScheduleSection').style.display = 'none';
    
    // Reset search mode
    currentSearchMode = 'channel';
    currentOnlyFilter = false;
    document.getElementById('searchModeChannel').checked = true;
    updateSearchModeUI();
    
    // Reset preview
    stopChannelPreview();
    document.getElementById('channelPreviewPlaceholder').style.display = 'flex';
    document.getElementById('channelPreviewVideo').style.display = 'none';
    document.getElementById('toggleChannelPreviewBtn').innerHTML = '<i class="bi bi-play-fill"></i> Start Preview';
    
    // Handle edit mode vs create mode
    const modalTitle = document.getElementById('manualMappingModalTitle');
    const saveBtn = document.getElementById('saveManualMappingBtn');
    const deleteBtn = document.getElementById('deleteMappingBtn');
    const existingIdField = document.getElementById('manualMappingExistingId');
    const currentMappingCard = document.getElementById('currentMappingCard');
    
    if (existingMapping && existingMapping.id) {
        // Edit mode
        isEditMode = true;
        currentMappingId = existingMapping.id;
        existingIdField.value = existingMapping.id;
        
        modalTitle.innerHTML = `Edit EPG Mapping for <span id="manualMappingChannel">${escapeHtml(channelName)}</span>`;
        saveBtn.textContent = 'Update Mapping';
        deleteBtn.style.display = 'block';
        
        // Set the time offset from existing mapping
        document.getElementById('manualMappingTimeOffset').value = existingMapping.time_offset_hours || '0';
        
        // Show current mapping info
        currentMappingCard.style.display = 'block';
        document.getElementById('currentEpgChannelName').textContent = existingMapping.epg_display_name || '-';
        document.getElementById('currentEpgSourceName').textContent = existingMapping.source_name || '-';
        
        // Pre-select the EPG channel if available
        if (existingMapping.epg_channel_id) {
            document.getElementById('manualMappingEpgChannel').value = existingMapping.epg_channel_id;
            document.getElementById('selectedEpgChannelName').textContent = existingMapping.epg_display_name || `EPG #${existingMapping.epg_channel_id}`;
            document.getElementById('selectedEpgChannel').style.display = 'block';
            
            // Load schedule for the existing EPG channel
            loadEpgSchedule(existingMapping.epg_channel_id, parseInt(document.getElementById('manualMappingTimeOffset').value) || 0);
        }
        
        loadCurrentMappingProgram(existingMapping.epg_channel_id);
    } else {
        // Create mode
        isEditMode = false;
        currentMappingId = null;
        existingIdField.value = '';
        
        modalTitle.innerHTML = `Create Manual EPG Mapping for <span id="manualMappingChannel">${escapeHtml(channelName)}</span>`;
        saveBtn.textContent = 'Create Mapping';
        deleteBtn.style.display = 'none';
        document.getElementById('manualMappingTimeOffset').value = '0';
        
        currentMappingCard.style.display = 'none';
    }
    
    epgSearchState = { search: '', offset: 0, hasMore: true, loading: false };
    
    // Populate EPG sources if not already done
    populateEpgSourcesForManualMapping();
    
    if (manualMappingModal) manualMappingModal.show();
}

async function loadCurrentMappingProgram(epgChannelId) {
    const container = document.getElementById('currentMappingProgram');
    if (!epgChannelId) {
        container.innerHTML = '<small class="text-muted">No mapping</small>';
        return;
    }
    
    try {
        const response = await fetch(`/api/epg/programs/current?epg_channel_ids=${epgChannelId}`);
        const data = await response.json();
        
        const program = data.programs && data.programs[epgChannelId];
        if (program) {
            container.innerHTML = `
                <strong>${escapeHtml(program.title)}</strong>
                ${program.sub_title ? `<br><small>${escapeHtml(program.sub_title)}</small>` : ''}
                <br><small class="text-muted">${formatProgramTime(program.start_time, program.stop_time)}</small>
            `;
        } else {
            container.innerHTML = '<small class="text-muted">No program data available</small>';
        }
    } catch (error) {
        console.error('Error loading current program:', error);
        container.innerHTML = '<small class="text-danger">Error loading program data</small>';
    }
}

async function loadEpgSchedule(epgChannelId, offsetHours = 0) {
    const scheduleSection = document.getElementById('epgScheduleSection');
    const scheduleContent = document.getElementById('epgScheduleContent');
    const offsetInfo = document.getElementById('scheduleOffsetInfo');
    
    if (!epgChannelId) {
        scheduleSection.style.display = 'none';
        return;
    }
    
    scheduleSection.style.display = 'block';
    scheduleContent.innerHTML = '<div class="list-group-item text-center"><span class="spinner-border spinner-border-sm"></span> Loading schedule...</div>';
    
    // Update offset info display
    if (offsetHours === 0) {
        offsetInfo.textContent = 'Current time (no offset)';
    } else if (offsetHours > 0) {
        offsetInfo.textContent = `Adjusted time: +${offsetHours} hour${offsetHours !== 1 ? 's' : ''} from now`;
    } else {
        offsetInfo.textContent = `Adjusted time: ${offsetHours} hour${Math.abs(offsetHours) !== 1 ? 's' : ''} from now`;
    }
    
    try {
        const response = await fetch(`/api/epg/programs/${epgChannelId}/schedule?offset_hours=${offsetHours}&hours_before=3&hours_after=3`);
        const data = await response.json();
        
        if (!response.ok) {
            scheduleContent.innerHTML = `<div class="list-group-item text-danger">${data.error || 'Error loading schedule'}</div>`;
            return;
        }
        
        let html = '';
        
        // Programs before current
        if (data.programs_before && data.programs_before.length > 0) {
            for (const program of data.programs_before) {
                html += renderScheduleProgram(program, 'before');
            }
        }
        
        // Current program (highlighted)
        if (data.current_program) {
            html += renderScheduleProgram(data.current_program, 'current');
        } else {
            html += '<div class="list-group-item list-group-item-warning text-center"><em>No program at adjusted time</em></div>';
        }
        
        // Programs after current
        if (data.programs_after && data.programs_after.length > 0) {
            for (const program of data.programs_after) {
                html += renderScheduleProgram(program, 'after');
            }
        }
        
        if (!html) {
            html = '<div class="list-group-item text-muted text-center">No programs found in schedule</div>';
        }
        
        scheduleContent.innerHTML = html;
    } catch (error) {
        console.error('Error loading EPG schedule:', error);
        scheduleContent.innerHTML = '<div class="list-group-item text-danger">Error loading schedule</div>';
    }
}

function renderScheduleProgram(program, position) {
    const startTime = parseUTCDateTime(program.start_time);
    const stopTime = parseUTCDateTime(program.stop_time);
    const timeStr = `${startTime.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'})} - ${stopTime.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'})}`;
    
    let bgClass = '';
    let icon = '';
    if (position === 'current') {
        bgClass = 'list-group-item-primary';
        icon = '<i class="bi bi-play-fill me-1"></i>';
    } else if (position === 'before') {
        bgClass = 'text-muted';
    }
    
    return `
        <div class="list-group-item ${bgClass} py-2">
            <div class="d-flex justify-content-between align-items-start">
                <div>
                    ${icon}<strong>${escapeHtml(program.title)}</strong>
                    ${program.sub_title ? `<br><small class="text-muted">${escapeHtml(program.sub_title)}</small>` : ''}
                </div>
                <small class="text-nowrap ms-2">${timeStr}</small>
            </div>
        </div>
    `;
}

async function deleteExistingMapping() {
    if (!currentMappingId) {
        showToast('No mapping to delete', 'error');
        return;
    }
    
    if (!confirm('Are you sure you want to delete this mapping?')) {
        return;
    }
    
    try {
        const response = await fetch(`/api/epg/mappings/${currentMappingId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            showToast('Mapping deleted successfully', 'success');
            if (manualMappingModal) manualMappingModal.hide();
            // Refresh the mappings table
            if (typeof loadMappings === 'function') {
                loadMappings();
            }
        } else {
            const error = await response.json();
            showToast('Error: ' + (error.error || 'Failed to delete mapping'), 'error');
        }
    } catch (error) {
        showToast('Error: ' + error.message, 'error');
    }
}

function updateSearchModeUI() {
    const searchLabel = document.getElementById('searchLabel');
    const searchHint = document.getElementById('searchHint');
    const resultsLabel = document.getElementById('resultsLabel');
    const searchInput = document.getElementById('manualMappingEpgSearch');
    const nowBtn = document.getElementById('searchCurrentProgramsBtn');
    
    if (currentSearchMode === 'program') {
        searchLabel.textContent = 'Search by Program Title';
        searchHint.textContent = 'Type what\'s currently playing (e.g., "A&M football", "Lakers"). Enable "Now" to show only currently airing.';
        resultsLabel.textContent = 'Programs Found';
        searchInput.placeholder = 'Type program title...';
        nowBtn.style.display = 'inline-block';
    } else {
        searchLabel.textContent = 'Search EPG Channels';
        searchHint.textContent = 'Search by channel name or ID.';
        resultsLabel.textContent = 'Available Channels';
        searchInput.placeholder = 'Type to search channels...';
        nowBtn.style.display = 'none';
    }
}

function clearSelectedEpgChannel() {
    document.getElementById('manualMappingEpgChannel').value = '';
    document.getElementById('selectedEpgChannel').style.display = 'none';
    document.querySelectorAll('#epgChannelList .list-group-item').forEach(item => {
        item.classList.remove('active');
    });
}

async function selectEpgChannel(id, displayName, channelId, currentProgram = null) {
    document.getElementById('manualMappingEpgChannel').value = id;
    document.getElementById('selectedEpgChannelName').textContent = `${displayName} (${channelId})`;
    document.getElementById('selectedEpgChannel').style.display = 'block';
    
    // Update selected program info
    const programTitle = document.getElementById('selectedProgramTitle');
    if (currentProgram) {
        programTitle.textContent = currentProgram.title || '-';
    } else {
        // Load current program for this EPG channel
        try {
            const response = await fetch(`/api/epg/programs/current?epg_channel_ids=${id}`);
            const data = await response.json();
            const program = data.programs && data.programs[id];
            programTitle.textContent = program ? program.title : 'No data';
        } catch {
            programTitle.textContent = '-';
        }
    }
    
    document.querySelectorAll('#epgChannelList .list-group-item').forEach(item => {
        item.classList.remove('active');
        if (item.dataset.id === String(id)) {
            item.classList.add('active');
        }
    });
    
    // Load schedule for the selected EPG channel
    const offsetHours = parseInt(document.getElementById('manualMappingTimeOffset').value) || 0;
    loadEpgSchedule(id, offsetHours);
}

async function searchEpgChannels(resetResults = true) {
    const search = document.getElementById('manualMappingEpgSearch').value.trim();
    const sourceId = document.getElementById('manualMappingEpgSource').value;
    
    if (resetResults) {
        epgSearchState = { search: search, offset: 0, hasMore: true, loading: false };
        document.getElementById('epgChannelList').innerHTML = '';
        document.getElementById('manualMappingEpgChannel').value = '';
        document.getElementById('selectedEpgChannel').style.display = 'none';
        document.getElementById('resultsCount').textContent = '';
    }
    
    if (search.length < 2) {
        const msg = currentSearchMode === 'program' 
            ? 'Type at least 2 characters to search programs...'
            : 'Type at least 2 characters to search...';
        document.getElementById('epgChannelList').innerHTML = `<div class="list-group-item text-muted">${msg}</div>`;
        return;
    }
    
    if (epgSearchState.loading || !epgSearchState.hasMore) return;
    
    epgSearchState.loading = true;
    const loader = document.getElementById('epgChannelLoader');
    loader.style.display = 'block';
    
    try {
        let url, response, data;
        
        if (currentSearchMode === 'program') {
            // Search by program title
            url = `/api/epg/programs/search?q=${encodeURIComponent(search)}&limit=${EPG_CHANNELS_PER_PAGE}`;
            if (sourceId) url += `&source_id=${sourceId}`;
            if (currentOnlyFilter) url += '&current_only=true';
            
            response = await fetch(url);
            data = await response.json();
            
            renderProgramSearchResults(data);
        } else {
            // Search by channel name
            url = `/api/epg/channels?search=${encodeURIComponent(search)}&limit=${EPG_CHANNELS_PER_PAGE}&offset=${epgSearchState.offset}`;
            if (sourceId) url += `&source_id=${sourceId}`;
            
            response = await fetch(url);
            data = await response.json();
            
            renderChannelSearchResults(data);
        }
        
    } catch (error) {
        console.error('Error searching:', error);
        document.getElementById('epgChannelList').innerHTML = '<div class="list-group-item text-danger">Error loading results</div>';
    } finally {
        loader.style.display = 'none';
        epgSearchState.loading = false;
    }
}

function renderChannelSearchResults(data) {
    const list = document.getElementById('epgChannelList');
    
    if (data.channels.length === 0 && epgSearchState.offset === 0) {
        list.innerHTML = '<div class="list-group-item text-muted">No channels found. Try different search terms.</div>';
        epgSearchState.hasMore = false;
        return;
    }
    
    document.getElementById('resultsCount').textContent = data.total;
    
    // Fetch current programs for these channels
    const channelIds = data.channels.map(ch => ch.id).join(',');
    
    fetch(`/api/epg/programs/current?epg_channel_ids=${channelIds}`)
        .then(resp => resp.json())
        .then(programData => {
            const programs = programData.programs || {};
            
            data.channels.forEach(ch => {
                const program = programs[ch.id];
                const item = document.createElement('button');
                item.type = 'button';
                item.className = 'list-group-item list-group-item-action';
                item.dataset.id = ch.id;
                item.innerHTML = `
                    <div class="d-flex justify-content-between align-items-start">
                        <div style="flex: 1;">
                            <strong>${escapeHtml(ch.display_name)}</strong>
                            <small class="text-muted ms-2">(${escapeHtml(ch.channel_id)})</small>
                            ${program ? `
                                <div class="small text-primary mt-1">
                                    <i class="bi bi-play-circle-fill"></i> 
                                    <strong>Now:</strong> ${escapeHtml(program.title)}
                                    ${program.is_live ? '<span class="badge bg-danger ms-1">LIVE</span>' : ''}
                                </div>
                            ` : '<div class="small text-muted mt-1">No current program data</div>'}
                        </div>
                        <small class="text-muted">${ch.program_count || 0} programs</small>
                    </div>
                `;
                item.onclick = () => selectEpgChannel(ch.id, ch.display_name, ch.channel_id, program);
                list.appendChild(item);
            });
        })
        .catch(() => {
            // Fallback without program data
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
        });
    
    epgSearchState.offset += data.channels.length;
    epgSearchState.hasMore = epgSearchState.offset < data.total;
}

function renderProgramSearchResults(data) {
    const list = document.getElementById('epgChannelList');
    
    if (data.results.length === 0) {
        list.innerHTML = '<div class="list-group-item text-muted">No programs found. Try different search terms.</div>';
        epgSearchState.hasMore = false;
        return;
    }
    
    document.getElementById('resultsCount').textContent = data.count;
    list.innerHTML = ''; // Clear for program search (no pagination)
    
    data.results.forEach(result => {
        const program = result.program;
        const epgChannel = result.epg_channel;
        
        const item = document.createElement('button');
        item.type = 'button';
        item.className = 'list-group-item list-group-item-action';
        item.dataset.id = epgChannel.id;
        item.innerHTML = `
            <div class="d-flex justify-content-between align-items-start">
                <div style="flex: 1;">
                    <div class="fw-bold text-primary">
                        ${escapeHtml(program.title)}
                        ${program.is_live ? '<span class="badge bg-danger ms-1">LIVE</span>' : ''}
                        ${program.is_currently_airing ? '<span class="badge bg-success ms-1">NOW</span>' : ''}
                    </div>
                    ${program.sub_title ? `<div class="small">${escapeHtml(program.sub_title)}</div>` : ''}
                    <div class="small text-muted">
                        <i class="bi bi-broadcast"></i> ${escapeHtml(epgChannel.display_name)}
                    </div>
                    <div class="small text-muted">
                        <i class="bi bi-clock"></i> ${formatProgramTime(program.start_time, program.stop_time)}
                    </div>
                </div>
            </div>
        `;
        item.onclick = () => selectEpgChannel(epgChannel.id, epgChannel.display_name, epgChannel.channel_id, program);
        list.appendChild(item);
    });
    
    epgSearchState.hasMore = false; // Program search doesn't paginate
}

function formatProgramTime(startTime, stopTime) {
    try {
        const start = parseUTCDateTime(startTime);
        const stop = parseUTCDateTime(stopTime);
        const options = { hour: 'numeric', minute: '2-digit' };
        return `${start.toLocaleTimeString([], options)} - ${stop.toLocaleTimeString([], options)}`;
    } catch {
        return '';
    }
}

function setupEpgChannelScroll() {
    const container = document.getElementById('epgChannelListContainer');
    if (container) {
        container.addEventListener('scroll', () => {
            const scrollBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
            if (scrollBottom < 50 && epgSearchState.hasMore && !epgSearchState.loading && currentSearchMode === 'channel') {
                searchEpgChannels(false);
            }
        });
    }
}

// Channel preview functionality
async function toggleChannelPreview() {
    const accountId = document.getElementById('manualMappingAccountId').value;
    const streamId = document.getElementById('manualMappingStreamId').value;
    
    if (!accountId || !streamId) {
        showToast('Cannot preview: missing account or stream info', 'error');
        return;
    }
    
    const btn = document.getElementById('toggleChannelPreviewBtn');
    const video = document.getElementById('channelPreviewVideo');
    const placeholder = document.getElementById('channelPreviewPlaceholder');
    
    if (channelPreviewActive) {
        stopChannelPreview();
        btn.innerHTML = '<i class="bi bi-play-fill"></i> Start Preview';
        placeholder.style.display = 'flex';
        video.style.display = 'none';
    } else {
        btn.innerHTML = '<i class="bi bi-hourglass-split"></i> Loading...';
        btn.disabled = true;
        
        try {
            // Build stream URL - mpegts.js requires absolute URLs
            const streamUrl = `${window.location.protocol}//${window.location.host}/stream/${accountId}/${streamId}.ts`;
            
            // Check if mpegts.js is supported
            if (typeof mpegts === 'undefined' || !mpegts.getFeatureList().mseLivePlayback) {
                showToast('Your browser doesn\'t support MSE for live playback. Please use Chrome, Firefox, or Edge.', 'error');
                btn.innerHTML = '<i class="bi bi-play-fill"></i> Start Preview';
                btn.disabled = false;
                return;
            }
            
            // Initialize mpegts.js player with same settings as player.html
            channelPreviewPlayer = mpegts.createPlayer({
                type: 'mpegts',
                isLive: true,
                url: streamUrl,
                hasAudio: true,
                hasVideo: true
            }, {
                enableWorker: true,
                enableStashBuffer: false,
                liveBufferLatencyChasing: false,
                liveSync: true,
                liveSyncMaxLatency: 3.0,
                liveSyncTargetLatency: 1.5,
                liveSyncPlaybackRate: 1.1,
                autoCleanupSourceBuffer: false,
                fixAudioTimestampGap: true,
                lazyLoad: false,
                seekType: 'range'
            });
            
            channelPreviewPlayer.attachMediaElement(video);
            
            // Error handling
            channelPreviewPlayer.on(mpegts.Events.ERROR, (errType, errDetail) => {
                console.error('mpegts.js error:', errType, errDetail);
                const errorDiv = document.getElementById('channelPreviewError');
                const errorMsg = document.getElementById('channelPreviewErrorMessage');
                errorMsg.textContent = `Playback error: ${errDetail}`;
                errorDiv.style.display = 'block';
                setTimeout(() => {
                    errorDiv.style.display = 'none';
                }, 5000);
            });
            
            // Loading complete
            channelPreviewPlayer.on(mpegts.Events.LOADING_COMPLETE, () => {
                console.log('Stream loading complete');
            });
            
            // Media info received
            channelPreviewPlayer.on(mpegts.Events.MEDIA_INFO, (mediaInfo) => {
                console.log('Media info:', mediaInfo);
            });
            
            // Handle video element events
            video.addEventListener('loadedmetadata', () => {
                console.log('Video metadata loaded');
                video.play().catch(err => {
                    console.warn('Play prevented:', err);
                });
            });
            
            video.addEventListener('error', (e) => {
                console.error('Video element error:', e);
                const errorDiv = document.getElementById('channelPreviewError');
                const errorMsg = document.getElementById('channelPreviewErrorMessage');
                errorMsg.textContent = 'Video playback error. The stream may be offline.';
                errorDiv.style.display = 'block';
            });
            
            // Load and start playback
            channelPreviewPlayer.load();
            channelPreviewPlayer.play().catch(err => {
                console.warn('Autoplay prevented:', err);
            });
            
            channelPreviewActive = true;
            placeholder.style.display = 'none';
            video.style.display = 'block';
            btn.innerHTML = '<i class="bi bi-stop-fill"></i> Stop Preview';
            btn.disabled = false;
            
        } catch (error) {
            console.error('Preview error:', error);
            showToast('Failed to start preview: ' + error.message, 'error');
            btn.innerHTML = '<i class="bi bi-play-fill"></i> Start Preview';
            btn.disabled = false;
        }
    }
}

function stopChannelPreview() {
    const video = document.getElementById('channelPreviewVideo');
    
    if (channelPreviewPlayer) {
        channelPreviewPlayer.pause();
        channelPreviewPlayer.unload();
        channelPreviewPlayer.detachMediaElement();
        channelPreviewPlayer.destroy();
        channelPreviewPlayer = null;
    }
    
    if (video) {
        video.pause();
        video.src = '';
        video.load();
    }
    
    channelPreviewActive = false;
}

async function saveManualMapping() {
    const channelId = document.getElementById('manualMappingChannelId').value;
    const epgChannelId = document.getElementById('manualMappingEpgChannel').value;
    const timeOffset = parseInt(document.getElementById('manualMappingTimeOffset').value) || 0;
    const existingId = document.getElementById('manualMappingExistingId').value;
    
    if (!channelId || !epgChannelId) {
        showToast('Please select an EPG channel', 'warning');
        return;
    }
    
    // Stop preview before saving
    stopChannelPreview();
    
    try {
        let response;
        if (isEditMode && existingId) {
            // Update existing mapping
            response = await fetch(`/api/epg/mappings/${existingId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    epg_channel_id: parseInt(epgChannelId),
                    time_offset_hours: timeOffset
                })
            });
        } else {
            // Create new mapping
            response = await fetch('/api/epg/mappings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    channel_id: parseInt(channelId),
                    epg_channel_id: parseInt(epgChannelId),
                    time_offset_hours: timeOffset
                })
            });
        }
        
        if (response.ok) {
            const mapping = await response.json();
            manualMappingModal.hide();
            
            // Update the row in the table
            const row = document.querySelector(`tr[data-channel-id="${channelId}"]`);
            if (row) {
                const cells = row.querySelectorAll('td');
                if (cells.length >= 4) {
                    cells[2].innerHTML = `<span class="text-success">${mapping.epg_display_name || 'EPG #' + epgChannelId}</span>`;
                    cells[3].innerHTML = '<span class="badge bg-primary">Manual</span> 100%';
                }
                const actionsDiv = cells[4]?.querySelector('.btn-group');
                if (actionsDiv) {
                    const createBtn = actionsDiv.querySelector('button[onclick^="showManualMappingModal"]');
                    if (createBtn) {
                        const deleteBtn = document.createElement('button');
                        deleteBtn.className = 'btn btn-outline-danger btn-sm';
                        deleteBtn.setAttribute('onclick', `deleteMapping(${mapping.mapping_id}, ${channelId})`);
                        deleteBtn.setAttribute('title', 'Delete mapping');
                        deleteBtn.innerHTML = '<i class="bi bi-trash"></i>';
                        createBtn.replaceWith(deleteBtn);
                    }
                }
            }
            showToast(isEditMode ? 'Mapping updated successfully' : 'Mapping created successfully', 'success');
            
            // Reload mappings to show updated data
            if (typeof loadMappings === 'function') {
                loadMappings();
            }
        } else {
            const error = await response.json();
            showToast('Error: ' + (error.error || (isEditMode ? 'Failed to update mapping' : 'Failed to create mapping')), 'error');
        }
    } catch (error) {
        showToast('Error: ' + error.message, 'error');
    }
}

// Initialize event listeners when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    // Search mode toggle
    const searchModeChannel = document.getElementById('searchModeChannel');
    const searchModeProgram = document.getElementById('searchModeProgram');
    
    if (searchModeChannel) {
        searchModeChannel.addEventListener('change', () => {
            if (searchModeChannel.checked) {
                currentSearchMode = 'channel';
                updateSearchModeUI();
                searchEpgChannels(true);
            }
        });
    }
    
    if (searchModeProgram) {
        searchModeProgram.addEventListener('change', () => {
            if (searchModeProgram.checked) {
                currentSearchMode = 'program';
                updateSearchModeUI();
                searchEpgChannels(true);
            }
        });
    }
    
    // Current only toggle
    const searchCurrentBtn = document.getElementById('searchCurrentProgramsBtn');
    if (searchCurrentBtn) {
        searchCurrentBtn.addEventListener('click', () => {
            currentOnlyFilter = !currentOnlyFilter;
            searchCurrentBtn.classList.toggle('btn-primary', currentOnlyFilter);
            searchCurrentBtn.classList.toggle('btn-outline-secondary', !currentOnlyFilter);
            if (document.getElementById('manualMappingEpgSearch').value.trim().length >= 2) {
                searchEpgChannels(true);
            }
        });
    }
    
    // Preview toggle
    const previewBtn = document.getElementById('toggleChannelPreviewBtn');
    if (previewBtn) {
        previewBtn.addEventListener('click', toggleChannelPreview);
    }
    
    // Clean up preview when modal closes
    const modalElement = document.getElementById('manualMappingModal');
    if (modalElement) {
        modalElement.addEventListener('hidden.bs.modal', () => {
            stopChannelPreview();
        });
    }
    
    // Time offset change listener - refresh schedule when offset changes
    const timeOffsetInput = document.getElementById('manualMappingTimeOffset');
    if (timeOffsetInput) {
        timeOffsetInput.addEventListener('change', () => {
            const epgChannelId = document.getElementById('manualMappingEpgChannel').value;
            if (epgChannelId) {
                const offsetHours = parseInt(timeOffsetInput.value) || 0;
                loadEpgSchedule(epgChannelId, offsetHours);
            }
        });
    }
    
    // Delete mapping button handler
    const deleteMappingBtn = document.getElementById('deleteMappingBtn');
    if (deleteMappingBtn) {
        deleteMappingBtn.addEventListener('click', deleteExistingMapping);
    }
});
