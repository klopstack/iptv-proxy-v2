/**
 * EPG Data Preview functionality
 * 
 * Allows users to preview EPG program data from configured sources
 */

// State management
let previewState = {
    selectedSourceId: null,
    selectedSourceType: null,
    selectedLineupId: null,
    selectedChannelId: null,
    loading: false
};
let previewTabInitialized = false;

/**
 * Load EPG sources into the source dropdown
 */
async function loadPreviewSources() {
    const sourceSelect = document.getElementById('preview-source-select');
    if (!sourceSelect) return;

    try {
        const response = await fetch('/api/epg/sources');
        if (!response.ok) throw new Error('Failed to load EPG sources');
        
        const sources = apiUnwrapData(response, await response.json());
        
        // Clear existing options except the first one
        sourceSelect.innerHTML = '<option value="">Select an EPG source...</option>';
        
        // Add sources
        sources.forEach(source => {
            const option = document.createElement('option');
            option.value = source.id;
            option.dataset.sourceType = source.source_type;
            option.textContent = `${source.name} (${source.source_type})`;
            if (!source.enabled) {
                option.textContent += ' [Disabled]';
                option.disabled = true;
            }
            sourceSelect.appendChild(option);
        });
    } catch (error) {
        console.error('Error loading preview sources:', error);
        showToast('Error loading EPG sources', 'danger');
    }
}

/**
 * Load lineups for a Schedules Direct source
 */
async function loadPreviewLineups() {
    const lineupSelect = document.getElementById('preview-lineup-select');
    const sourceId = previewState.selectedSourceId;
    
    if (!lineupSelect || !sourceId) return;
    
    lineupSelect.disabled = true;
    lineupSelect.innerHTML = '<option value="">Loading...</option>';
    
    try {
        const response = await fetch(`/api/epg/sd/lineups?source_id=${sourceId}`);
        if (!response.ok) throw new Error('Failed to load lineups');
        
        const data = await response.json();
        
        // Clear and populate
        lineupSelect.innerHTML = '<option value="">All lineups</option>';
        
        if (data.lineups && data.lineups.length > 0) {
            data.lineups.forEach(lineup => {
                const option = document.createElement('option');
                option.value = lineup.id;
                option.textContent = `${lineup.name || lineup.lineup_id} (${lineup.channel_count || 0} channels)`;
                lineupSelect.appendChild(option);
            });
            lineupSelect.disabled = false;
        } else {
            lineupSelect.innerHTML = '<option value="">No lineups configured</option>';
        }
    } catch (error) {
        console.error('Error loading preview lineups:', error);
        showToast('Error loading lineups', 'danger');
        lineupSelect.innerHTML = '<option value="">All lineups</option>';
        lineupSelect.disabled = false;
    }
}

/**
 * Load channels for the selected source and optionally lineup
 */
async function loadPreviewChannels() {
    const channelSelect = document.getElementById('preview-channel-select');
    const sourceId = previewState.selectedSourceId;
    const lineupId = previewState.selectedLineupId;
    
    if (!channelSelect || !sourceId) return;
    
    channelSelect.disabled = true;
    channelSelect.innerHTML = '<option value="">Loading...</option>';
    
    try {
        let url = `/api/epg/channels?source_id=${sourceId}&limit=1000`;
        if (lineupId) {
            url += `&lineup_id=${lineupId}`;
        }
        
        const response = await fetch(url);
        if (!response.ok) throw new Error('Failed to load channels');
        
        const data = await response.json();
        
        // Clear and populate
        channelSelect.innerHTML = '<option value="">All channels</option>';
        
        if (data.channels && data.channels.length > 0) {
            data.channels.forEach(channel => {
                const option = document.createElement('option');
                option.value = channel.id;
                option.textContent = channel.display_name;
                channelSelect.appendChild(option);
            });
            channelSelect.disabled = false;
        } else {
            channelSelect.innerHTML = '<option value="">No channels found</option>';
        }
    } catch (error) {
        console.error('Error loading preview channels:', error);
        showToast('Error loading channels', 'danger');
        channelSelect.innerHTML = '<option value="">All channels</option>';
        channelSelect.disabled = false;
    }
}

/**
 * Load EPG program data
 */
async function loadPreviewData() {
    const sourceId = previewState.selectedSourceId;
    const channelId = previewState.selectedChannelId;
    
    if (!sourceId) {
        showToast('Please select an EPG source', 'warning');
        return;
    }
    
    previewState.loading = true;
    
    // Show loading state
    document.getElementById('preview-results').style.display = 'none';
    document.getElementById('preview-empty').style.display = 'none';
    document.getElementById('preview-loading').style.display = 'block';
    
    try {
        let url;
        if (channelId) {
            // Get programs for specific channel
            url = `/api/epg/programs/${channelId}?hours=24&limit=50&include_current=true`;
        } else {
            // Get current programs for all channels in source
            url = `/api/epg/programs/current?source_id=${sourceId}`;
        }
        
        const response = await fetch(url);
        if (!response.ok) throw new Error('Failed to load EPG data');
        
        const data = await response.json();
        
        // Hide loading
        document.getElementById('preview-loading').style.display = 'none';
        
        if (channelId) {
            // Display single channel programs
            displaySingleChannelPrograms(data);
        } else {
            // Display multi-channel current programs
            displayMultiChannelPrograms(data.programs || {}, sourceId);
        }
    } catch (error) {
        console.error('Error loading EPG data:', error);
        document.getElementById('preview-loading').style.display = 'none';
        showToast('Error loading EPG data', 'danger');
    } finally {
        previewState.loading = false;
    }
}

/**
 * Display programs for a single channel
 */
function displaySingleChannelPrograms(data) {
    const container = document.getElementById('preview-programs-container');
    
    if (!data.current_program && (!data.upcoming_programs || data.upcoming_programs.length === 0)) {
        document.getElementById('preview-empty').style.display = 'block';
        return;
    }
    
    document.getElementById('preview-results').style.display = 'block';
    container.innerHTML = '';
    
    // Current program
    if (data.current_program) {
        const currentCard = createProgramCard(data.current_program, true);
        container.appendChild(currentCard);
    }
    
    // Upcoming programs
    if (data.upcoming_programs.length > 0) {
        const upcomingHeader = document.createElement('h6');
        upcomingHeader.className = 'mt-4 mb-3';
        upcomingHeader.innerHTML = '<i class="bi bi-clock"></i> Upcoming Programs';
        container.appendChild(upcomingHeader);
        
        data.upcoming_programs.forEach(program => {
            const card = createProgramCard(program, false);
            container.appendChild(card);
        });
    }
}

/**
 * Display current programs for multiple channels
 */
async function displayMultiChannelPrograms(programs, sourceId) {
    const container = document.getElementById('preview-programs-container');
    
    if (Object.keys(programs).length === 0) {
        document.getElementById('preview-empty').style.display = 'block';
        return;
    }
    
    document.getElementById('preview-results').style.display = 'block';
    container.innerHTML = '';
    
    // Get channel names
    const response = await fetch(`/api/epg/channels?source_id=${sourceId}&limit=1000`);
    const channelData = await response.json();
    const channelMap = {};
    channelData.channels.forEach(ch => {
        channelMap[ch.id] = ch.display_name;
    });
    
    // Sort by channel name
    const sortedPrograms = Object.entries(programs).sort((a, b) => {
        const nameA = channelMap[a[0]] || '';
        const nameB = channelMap[b[0]] || '';
        return nameA.localeCompare(nameB);
    });
    
    const info = document.createElement('div');
    info.className = 'alert alert-info mb-3';
    info.innerHTML = `<i class="bi bi-info-circle"></i> Showing currently airing programs for <strong>${sortedPrograms.length}</strong> channels`;
    container.appendChild(info);
    
    sortedPrograms.forEach(([channelId, program]) => {
        const channelName = channelMap[channelId] || `Channel ${channelId}`;
        const card = createProgramCard(program, false, channelName);
        container.appendChild(card);
    });
}

/**
 * Create a program card element
 */
function createProgramCard(program, isCurrent, channelName = null) {
    const card = document.createElement('div');
    card.className = `card mb-2 ${isCurrent ? 'border-primary' : ''}`;
    
    const cardBody = document.createElement('div');
    cardBody.className = 'card-body p-3';
    
    // Header with channel name (if provided) and current badge
    let headerHtml = '';
    if (channelName) {
        headerHtml += `<h6 class="card-subtitle text-muted mb-2"><i class="bi bi-tv"></i> ${escapeHtml(channelName)}</h6>`;
    }
    if (isCurrent) {
        headerHtml += '<span class="badge bg-primary mb-2"><i class="bi bi-broadcast"></i> Now Playing</span>';
    }
    
    // Program title
    const titleHtml = `<h5 class="card-title mb-2">${escapeHtml(program.title)}</h5>`;
    
    // Time info - use parseUTCDateTime for proper local time display
    const startTime = parseUTCDateTime(program.start_time);
    const stopTime = parseUTCDateTime(program.stop_time);
    const timeHtml = `
        <p class="card-text small mb-2">
            <i class="bi bi-clock"></i> 
            ${startTime.toLocaleTimeString()} - ${stopTime.toLocaleTimeString()}
            <span class="text-muted">(${formatDuration(startTime, stopTime)})</span>
        </p>
    `;
    
    // Description (if available)
    let descriptionHtml = '';
    if (program.description) {
        const maxLength = 200;
        const desc = program.description.length > maxLength 
            ? program.description.substring(0, maxLength) + '...'
            : program.description;
        descriptionHtml = `<p class="card-text text-muted small mb-2">${escapeHtml(desc)}</p>`;
    }
    
    // Categories (if available)
    let categoriesHtml = '';
    if (program.categories && program.categories.length > 0) {
        const categoryBadges = program.categories
            .slice(0, 3)
            .map(cat => `<span class="badge bg-secondary">${escapeHtml(cat)}</span>`)
            .join(' ');
        categoriesHtml = `<div class="mb-2">${categoryBadges}</div>`;
    }
    
    // Episode info (if available)
    let episodeHtml = '';
    if (program.season || program.episode) {
        const episodeText = program.season && program.episode 
            ? `S${program.season}E${program.episode}`
            : program.season 
                ? `Season ${program.season}`
                : `Episode ${program.episode}`;
        episodeHtml = `<small class="text-muted"><i class="bi bi-film"></i> ${escapeHtml(episodeText)}</small>`;
    }
    
    cardBody.innerHTML = headerHtml + titleHtml + timeHtml + descriptionHtml + categoriesHtml + episodeHtml;
    card.appendChild(cardBody);
    
    return card;
}

/**
 * Format duration between two times
 */
function formatDuration(start, stop) {
    const diffMs = stop - start;
    const diffMins = Math.round(diffMs / 60000);
    
    if (diffMins < 60) {
        return `${diffMins}m`;
    }
    
    const hours = Math.floor(diffMins / 60);
    const mins = diffMins % 60;
    return mins > 0 ? `${hours}h ${mins}m` : `${hours}h`;
}

/**
 * Initialize preview tab
 */
async function initializePreviewTab() {
    await loadPreviewSources();

    if (previewTabInitialized) {
        return;
    }
    previewTabInitialized = true;
    
    // Source selection change handler
    const sourceSelect = document.getElementById('preview-source-select');
    if (sourceSelect) {
        sourceSelect.addEventListener('change', async (e) => {
            previewState.selectedSourceId = e.target.value ? parseInt(e.target.value) : null;
            previewState.selectedChannelId = null;
            previewState.selectedLineupId = null;
            
            // Get source type from selected option
            const selectedOption = e.target.options[e.target.selectedIndex];
            previewState.selectedSourceType = selectedOption ? selectedOption.dataset.sourceType : null;
            
            const loadBtn = document.getElementById('preview-load-btn');
            const refreshBtn = document.getElementById('preview-refresh-btn');
            const channelSelect = document.getElementById('preview-channel-select');
            const lineupContainer = document.getElementById('preview-lineup-container');
            const lineupSelect = document.getElementById('preview-lineup-select');
            const channelContainer = document.getElementById('preview-channel-container');
            
            if (previewState.selectedSourceId) {
                loadBtn.disabled = false;
                
                // Show/hide lineup selector based on source type
                if (previewState.selectedSourceType === 'schedules_direct') {
                    lineupContainer.style.display = 'block';
                    channelContainer.className = 'col-md-4';
                    await loadPreviewLineups();
                } else {
                    lineupContainer.style.display = 'none';
                    channelContainer.className = 'col-md-8';
                    lineupSelect.innerHTML = '<option value="">All lineups</option>';
                    lineupSelect.disabled = true;
                }
                
                await loadPreviewChannels();
            } else {
                loadBtn.disabled = true;
                refreshBtn.disabled = true;
                channelSelect.disabled = true;
                channelSelect.innerHTML = '<option value="">All channels</option>';
                lineupContainer.style.display = 'none';
                lineupSelect.innerHTML = '<option value="">All lineups</option>';
                lineupSelect.disabled = true;
            }
            
            // Hide results
            document.getElementById('preview-results').style.display = 'none';
            document.getElementById('preview-empty').style.display = 'none';
        });
    }
    
    // Lineup selection change handler
    const lineupSelect = document.getElementById('preview-lineup-select');
    if (lineupSelect) {
        lineupSelect.addEventListener('change', async (e) => {
            previewState.selectedLineupId = e.target.value ? parseInt(e.target.value) : null;
            previewState.selectedChannelId = null;
            await loadPreviewChannels();
        });
    }
    
    // Channel selection change handler
    const channelSelect = document.getElementById('preview-channel-select');
    if (channelSelect) {
        channelSelect.addEventListener('change', (e) => {
            previewState.selectedChannelId = e.target.value ? parseInt(e.target.value) : null;
        });
    }
    
    // Load button click handler
    const loadBtn = document.getElementById('preview-load-btn');
    if (loadBtn) {
        loadBtn.addEventListener('click', async () => {
            await loadPreviewData();
            document.getElementById('preview-refresh-btn').disabled = false;
        });
    }
    
    // Refresh button click handler
    const refreshBtn = document.getElementById('preview-refresh-btn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', loadPreviewData);
    }
}

// Initialize when tab is shown
document.addEventListener('DOMContentLoaded', () => {
    const previewTab = document.getElementById('preview-tab');
    if (previewTab) {
        previewTab.addEventListener('shown.bs.tab', initializePreviewTab);
    }
});
