/**
 * EPG Data Preview tab (ESM).
 */
import { parseUTCDateTime } from '../lib/epg_datetime.js';
import { formatDuration } from '../lib/epg_preview_helpers.js';
import { escapeHtml } from '../lib/escape_html.js';

const previewState = {
    selectedSourceId: null,
    selectedSourceType: null,
    selectedLineupId: null,
    selectedChannelId: null,
    loading: false,
};
let previewTabInitialized = false;

async function loadPreviewSources() {
    const sourceSelect = document.getElementById('preview-source-select');
    if (!sourceSelect) return;

    try {
        const response = await fetch('/api/epg/sources');
        if (!response.ok) throw new Error('Failed to load EPG sources');

        const sources = apiUnwrapData(response, await response.json());

        sourceSelect.innerHTML = '<option value="">Select an EPG source...</option>';

        sources.forEach((source) => {
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

        lineupSelect.innerHTML = '<option value="">All lineups</option>';

        if (data.lineups && data.lineups.length > 0) {
            data.lineups.forEach((lineup) => {
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

        channelSelect.innerHTML = '<option value="">All channels</option>';

        if (data.channels && data.channels.length > 0) {
            data.channels.forEach((channel) => {
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

async function loadPreviewData() {
    const sourceId = previewState.selectedSourceId;
    const channelId = previewState.selectedChannelId;

    if (!sourceId) {
        showToast('Please select an EPG source', 'warning');
        return;
    }

    previewState.loading = true;

    document.getElementById('preview-results').style.display = 'none';
    document.getElementById('preview-empty').style.display = 'none';
    document.getElementById('preview-loading').style.display = 'block';

    try {
        let url;
        if (channelId) {
            url = `/api/epg/programs/${channelId}?hours=24&limit=50&include_current=true`;
        } else {
            url = `/api/epg/programs/current?source_id=${sourceId}`;
        }

        const response = await fetch(url);
        if (!response.ok) throw new Error('Failed to load EPG data');

        const data = await response.json();

        document.getElementById('preview-loading').style.display = 'none';

        if (channelId) {
            displaySingleChannelPrograms(data);
        } else {
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

function displaySingleChannelPrograms(data) {
    const container = document.getElementById('preview-programs-container');

    if (!data.current_program && (!data.upcoming_programs || data.upcoming_programs.length === 0)) {
        document.getElementById('preview-empty').style.display = 'block';
        return;
    }

    document.getElementById('preview-results').style.display = 'block';
    container.innerHTML = '';

    if (data.current_program) {
        container.appendChild(createProgramCard(data.current_program, true));
    }

    if (data.upcoming_programs.length > 0) {
        const upcomingHeader = document.createElement('h6');
        upcomingHeader.className = 'mt-4 mb-3';
        upcomingHeader.innerHTML = '<i class="bi bi-clock"></i> Upcoming Programs';
        container.appendChild(upcomingHeader);

        data.upcoming_programs.forEach((program) => {
            container.appendChild(createProgramCard(program, false));
        });
    }
}

async function displayMultiChannelPrograms(programs, sourceId) {
    const container = document.getElementById('preview-programs-container');

    if (Object.keys(programs).length === 0) {
        document.getElementById('preview-empty').style.display = 'block';
        return;
    }

    document.getElementById('preview-results').style.display = 'block';
    container.innerHTML = '';

    const response = await fetch(`/api/epg/channels?source_id=${sourceId}&limit=1000`);
    const channelData = await response.json();
    const channelMap = {};
    channelData.channels.forEach((ch) => {
        channelMap[ch.id] = ch.display_name;
    });

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
        container.appendChild(createProgramCard(program, false, channelName));
    });
}

function createProgramCard(program, isCurrent, channelName = null) {
    const card = document.createElement('div');
    card.className = `card mb-2 ${isCurrent ? 'border-primary' : ''}`;

    const cardBody = document.createElement('div');
    cardBody.className = 'card-body p-3';

    let headerHtml = '';
    if (channelName) {
        headerHtml += `<h6 class="card-subtitle text-muted mb-2"><i class="bi bi-tv"></i> ${escapeHtml(channelName)}</h6>`;
    }
    if (isCurrent) {
        headerHtml += '<span class="badge bg-primary mb-2"><i class="bi bi-broadcast"></i> Now Playing</span>';
    }

    const titleHtml = `<h5 class="card-title mb-2">${escapeHtml(program.title)}</h5>`;

    const startTime = parseUTCDateTime(program.start_time);
    const stopTime = parseUTCDateTime(program.stop_time);
    const timeHtml = `
        <p class="card-text small mb-2">
            <i class="bi bi-clock"></i> 
            ${startTime.toLocaleTimeString()} - ${stopTime.toLocaleTimeString()}
            <span class="text-muted">(${formatDuration(startTime, stopTime)})</span>
        </p>
    `;

    let descriptionHtml = '';
    if (program.description) {
        const maxLength = 200;
        const desc = program.description.length > maxLength
            ? program.description.substring(0, maxLength) + '...'
            : program.description;
        descriptionHtml = `<p class="card-text text-muted small mb-2">${escapeHtml(desc)}</p>`;
    }

    let categoriesHtml = '';
    if (program.categories && program.categories.length > 0) {
        const categoryBadges = program.categories
            .slice(0, 3)
            .map((cat) => `<span class="badge bg-secondary">${escapeHtml(cat)}</span>`)
            .join(' ');
        categoriesHtml = `<div class="mb-2">${categoryBadges}</div>`;
    }

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

async function initializePreviewTab() {
    await loadPreviewSources();

    if (previewTabInitialized) {
        return;
    }
    previewTabInitialized = true;

    const sourceSelect = document.getElementById('preview-source-select');
    if (sourceSelect) {
        sourceSelect.addEventListener('change', async (e) => {
            previewState.selectedSourceId = e.target.value ? parseInt(e.target.value, 10) : null;
            previewState.selectedChannelId = null;
            previewState.selectedLineupId = null;

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

            document.getElementById('preview-results').style.display = 'none';
            document.getElementById('preview-empty').style.display = 'none';
        });
    }

    const lineupSelect = document.getElementById('preview-lineup-select');
    if (lineupSelect) {
        lineupSelect.addEventListener('change', async (e) => {
            previewState.selectedLineupId = e.target.value ? parseInt(e.target.value, 10) : null;
            previewState.selectedChannelId = null;
            await loadPreviewChannels();
        });
    }

    const channelSelect = document.getElementById('preview-channel-select');
    if (channelSelect) {
        channelSelect.addEventListener('change', (e) => {
            previewState.selectedChannelId = e.target.value ? parseInt(e.target.value, 10) : null;
        });
    }

    const loadBtn = document.getElementById('preview-load-btn');
    if (loadBtn) {
        loadBtn.addEventListener('click', async () => {
            await loadPreviewData();
            document.getElementById('preview-refresh-btn').disabled = false;
        });
    }

    const refreshBtn = document.getElementById('preview-refresh-btn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', loadPreviewData);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const previewTab = document.getElementById('preview-tab');
    if (previewTab) {
        previewTab.addEventListener('shown.bs.tab', initializePreviewTab);
    }
});

const epgPreviewExports = {
    initializePreviewTab,
    loadPreviewSources,
    loadPreviewData,
};

Object.assign(window, epgPreviewExports);
export { epgPreviewExports, formatDuration, createProgramCard };
