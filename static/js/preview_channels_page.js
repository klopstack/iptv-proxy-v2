import {
    buildCollapseBadge,
    buildDataSourceBadge,
    buildPreviewUrl,
    buildTagRuleParams,
    formatChannelCount,
    getTagBadgeColorClass,
    normalizeTag,
} from './preview_channels.js';
import { fetchAccounts } from './lib/account_select.js';
import { unwrapData } from './lib/api_contract.js';
import { formatLocalDateTime } from './lib/epg_datetime.js';
import { escapeHtml, parseUrlParams } from './utils.js';

let accounts = [];
let currentAccountId = null;
let totalChannels = 0;
let loadedChannels = 0;
const CHANNELS_PER_PAGE = 50;
let loadingMore = false;
let hasMore = true;
let tagSelector = null;

async function loadAccounts() {
    accounts = await fetchAccounts();

    const select = document.getElementById('testAccountId');
    select.innerHTML = '<option value="all">All Accounts</option>';

    for (const account of accounts) {
        if (account.enabled) {
            const option = document.createElement('option');
            option.value = account.id;
            option.textContent = account.name;
            select.appendChild(option);
        }
    }

    const { account: accountId, tag: tagName, category: categoryName } = parseUrlParams(window.location.search);

    if (accountId) {
        select.value = accountId;

        if (tagName) {
            await loadTagFromUrl(accountId, tagName);
        } else if (categoryName) {
            window.categoryFilter = categoryName;
            updateCategoryFilterUI();
            await loadPreview();
        } else {
            await loadPreview();
        }
    } else {
        select.value = 'all';
        await loadPreview();
    }
}

function updateCategoryFilterUI() {
    const card = document.getElementById('categoryFilterCard');
    const nameSpan = document.getElementById('categoryFilterName');

    if (window.categoryFilter) {
        card.style.display = 'block';
        nameSpan.innerHTML = `<span class="badge bg-info">${escapeHtml(window.categoryFilter)}</span>`;
    } else {
        card.style.display = 'none';
        nameSpan.innerHTML = '';
    }
}

function clearCategoryFilter() {
    window.categoryFilter = null;
    updateCategoryFilterUI();

    const url = new URL(window.location);
    url.searchParams.delete('category');
    window.history.replaceState({}, '', url);

    loadPreview();
}

function initTagSelector() {
    if (tagSelector) {
        return;
    }

    tagSelector = new TagSelector({
        containerId: 'previewTagSelector',
        accountIdGetter: () => {
            const val = document.getElementById('testAccountId').value;
            return val === 'all' ? null : val;
        },
        badgeClass: 'bg-primary',
        placeholder: 'Search tags...',
    });
}

async function loadTagFromUrl(accountId, tagName) {
    try {
        initTagSelector();

        const response = await fetch(`/api/accounts/${accountId}/tags/search?q=${encodeURIComponent(tagName)}&limit=1`);
        const tags = await response.json();

        if (tags.length > 0 && tags[0].name === tagName) {
            tagSelector.setTags([tags[0]]);
        }

        await loadPreview();
    } catch (error) {
        console.error('Error loading tag from URL:', error);
        await loadPreview();
    }
}

async function loadPreview() {
    const accountId = document.getElementById('testAccountId').value;
    if (!accountId) {
        return;
    }

    initTagSelector();

    currentAccountId = accountId;
    totalChannels = 0;
    loadedChannels = 0;
    hasMore = true;

    document.getElementById('previewResult').innerHTML = `
        <div class="text-center">
            <div class="spinner-border" role="status"></div>
            <p>Loading channels...</p>
        </div>
    `;

    await loadActiveFilters(accountId);

    const html = `
        <div class="alert alert-info" id="channelCount">
            Loading channels...
        </div>
        <div class="table-responsive">
            <table class="table table-sm table-hover">
                <thead>
                    <tr>
                        <th>Icon</th>
                        <th>Channel Name</th>
                        <th>Cleaned Name</th>
                        <th>Category</th>
                        <th>Tags</th>
                        <th style="min-width: 90px;">Actions</th>
                    </tr>
                </thead>
                <tbody id="channelsTableBody">
                </tbody>
            </table>
        </div>
        <div id="loadingIndicator" class="text-center my-3" style="min-height: 50px;">
            <div class="spinner-border spinner-border-sm" role="status">
                <span class="visually-hidden">Loading more...</span>
            </div>
            Loading more channels...
        </div>
    `;

    document.getElementById('previewResult').innerHTML = html;

    setupInfiniteScroll();
    await loadMoreChannels();
}

async function loadMoreChannels() {
    if (loadingMore || !hasMore || !currentAccountId) {
        return;
    }

    loadingMore = true;
    const loadingIndicator = document.getElementById('loadingIndicator');
    if (loadingIndicator) {
        loadingIndicator.style.display = 'block';
    }

    try {
        const selectedTagNames = tagSelector ? tagSelector.getTagNames() : [];
        const collapseDuplicates = document.getElementById('collapseDuplicates')?.checked || false;
        const searchTerm = document.getElementById('channelSearch')?.value.trim() || '';

        const url = buildPreviewUrl(currentAccountId, {
            limit: CHANNELS_PER_PAGE,
            offset: loadedChannels,
            tags: selectedTagNames,
            category: window.categoryFilter || null,
            collapseDuplicates,
            search: searchTerm,
        });

        const response = await fetch(url);
        const data = await response.json();

        if (data.error) {
            throw new Error(data.error);
        }

        if (data.total > 0) {
            totalChannels = data.total;
        }

        if (loadedChannels === 0) {
            const countDisplay = document.getElementById('channelCount');
            if (countDisplay) {
                countDisplay.innerHTML += buildDataSourceBadge(data.using_database)
                    + buildCollapseBadge(data.collapse_duplicates, data.duplicates_collapsed || 0);
            }
        }

        const tbody = document.getElementById('channelsTableBody');
        let html = '';

        for (const channel of data.channels) {
            const tagsHtml = channel.tags && channel.tags.length > 0
                ? channel.tags.map((tag) => {
                    const { name: tagName, source: tagSource } = normalizeTag(tag);
                    const colorClass = getTagBadgeColorClass(tagSource);
                    return `<span class="badge ${colorClass} me-1" title="Source: ${tagSource}">${escapeHtml(tagName)}</span>`;
                }).join('')
                : '<span class="text-muted">No tags</span>';

            const duplicateBadge = channel.duplicate_count > 0
                ? `<span class="badge bg-warning ms-1" title="Best quality of ${channel.duplicate_count + 1} versions"><i class="bi bi-layers"></i> +${channel.duplicate_count}</span>`
                : '';

            const cleanedNameHtml = channel.cleaned_name && channel.cleaned_name !== channel.name
                ? `<div class="text-muted small">${escapeHtml(channel.cleaned_name)}</div>`
                : '';

            html += `
                <tr class="channel-row" style="cursor: pointer;"
                    data-account-id="${channel.account_id}"
                    data-stream-id="${channel.stream_id}"
                    title="Click for details">
                    <td>${channel.icon ? `<img src="${escapeHtml(channel.icon)}" width="40" height="30" onerror="this.style.display='none'">` : ''}</td>
                    <td>
                        ${escapeHtml(channel.name)}${duplicateBadge}
                        ${cleanedNameHtml}
                    </td>
                    <td>${channel.cleaned_name ? escapeHtml(channel.cleaned_name) : '<span class="text-muted">-</span>'}</td>
                    <td><span class="badge bg-secondary">${escapeHtml(channel.category || 'Uncategorized')}</span></td>
                    <td>${tagsHtml}</td>
                    <td class="text-nowrap">
                        <div class="btn-group btn-group-sm" role="group">
                            <a class="btn btn-outline-success" href="/player/${channel.account_id}/${channel.stream_id}" target="_blank" title="Play stream">
                                <i class="bi bi-play-fill"></i>
                            </a>
                            <button class="btn btn-outline-primary" data-action="create-tag-rule" data-channel-name="${escapeHtml(channel.name)}" data-channel-id="${channel.id}" title="Create tag rule for this channel">
                                <i class="bi bi-tag"></i>
                            </button>
                            <button class="btn btn-outline-info" data-action="view-details" data-account-id="${channel.account_id}" data-stream-id="${channel.stream_id}" title="View channel details">
                                <i class="bi bi-info-circle"></i>
                            </button>
                            <button class="btn btn-outline-danger" data-action="hide-channel" data-account-id="${channel.account_id}" data-channel-name="${escapeHtml(channel.name)}" title="Hide this channel">
                                <i class="bi bi-eye-slash"></i>
                            </button>
                        </div>
                    </td>
                </tr>
            `;
        }

        if (tbody) {
            tbody.innerHTML += html;
        }

        loadedChannels += data.showing;
        hasMore = data.has_more;

        const countDisplay = document.getElementById('channelCount');
        if (countDisplay) {
            countDisplay.innerHTML = formatChannelCount(loadedChannels, totalChannels);
        }

        if (!hasMore && loadingIndicator) {
            loadingIndicator.style.display = 'none';
        }
    } catch (error) {
        document.getElementById('previewResult').innerHTML = `
            <div class="alert alert-danger">
                Error loading channels: ${escapeHtml(error.message)}
            </div>
        `;
    }

    loadingMore = false;
}

function setupInfiniteScroll() {
    const loadingIndicator = document.getElementById('loadingIndicator');
    if (!loadingIndicator) {
        return;
    }

    const observer = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
            if (entry.isIntersecting && !loadingMore && hasMore) {
                loadMoreChannels();
            }
        });
    }, {
        root: null,
        rootMargin: '200px',
        threshold: 0.1,
    });

    observer.observe(loadingIndicator);
}

function downloadPlaylist() {
    const accountId = document.getElementById('testAccountId').value;
    if (!accountId) {
        alert('Please select an account first');
        return;
    }

    if (accountId === 'all') {
        alert('Please select a specific account to download playlist. "All Accounts" view is for preview only.');
        return;
    }

    window.open(`/playlist/${accountId}.m3u`, '_blank');
}

function createManualTagRule(channelName) {
    const accountId = document.getElementById('testAccountId').value;
    if (!accountId) {
        alert('Please select an account first');
        return;
    }

    const params = buildTagRuleParams(accountId, channelName);
    window.open(`/rulesets?${params.toString()}`, '_blank');
}

async function showChannelDetails(accountId, streamId) {
    const modal = new bootstrap.Modal(document.getElementById('channelDetailModal'));
    const contentDiv = document.getElementById('channelDetailContent');

    contentDiv.innerHTML = `
        <div class="text-center">
            <div class="spinner-border" role="status">
                <span class="visually-hidden">Loading...</span>
            </div>
        </div>
    `;

    modal.show();

    try {
        const response = await fetch(`/api/accounts/${accountId}/channels/${streamId}`);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const channel = await response.json();

        const tagsHtml = channel.tags && channel.tags.length > 0
            ? channel.tags.map((tag) => {
                const { name: tagName, source: tagSource } = normalizeTag(tag);
                const colorClass = getTagBadgeColorClass(tagSource);
                return `<span class="badge ${colorClass} me-1" title="Source: ${tagSource}">${escapeHtml(tagName)}</span>`;
            }).join('')
            : '<span class="text-muted">No tags</span>';

        const formatDate = (dateStr) => {
            if (!dateStr) {
                return '<span class="text-muted">-</span>';
            }
            const formatted = formatLocalDateTime(dateStr, { timeZoneName: 'short' });
            return formatted || escapeHtml(String(dateStr));
        };

        const formatBool = (val) => val
            ? '<span class="badge bg-success">Yes</span>'
            : '<span class="badge bg-secondary">No</span>';

        document.getElementById('channelDetailModalLabel').textContent = channel.cleaned_name || channel.name;

        contentDiv.innerHTML = `
            <div class="row">
                <div class="col-md-4 text-center mb-3">
                    ${channel.stream_icon
                        ? `<img src="${channel.stream_icon}" class="img-fluid rounded mb-2" style="max-height: 150px;" onerror="this.style.display='none'; this.nextElementSibling.style.display='block';">
                           <div class="text-muted" style="display:none;"><i class="bi bi-image" style="font-size: 4rem;"></i><br>No icon available</div>`
                        : '<div class="text-muted"><i class="bi bi-image" style="font-size: 4rem;"></i><br>No icon available</div>'
                    }
                </div>
                <div class="col-md-8">
                    <h5 class="mb-1">${escapeHtml(channel.name)}</h5>
                    ${channel.cleaned_name && channel.cleaned_name !== channel.name
                        ? `<p class="text-muted mb-2">Cleaned: ${escapeHtml(channel.cleaned_name)}</p>`
                        : ''}
                    <div class="mb-2">
                        <span class="badge bg-secondary">${escapeHtml(channel.category)}</span>
                        <span class="badge bg-primary ms-1">${escapeHtml(channel.account_name)}</span>
                    </div>
                    <div class="mb-2">${tagsHtml}</div>
                </div>
            </div>

            <hr>

            <div class="row">
                <div class="col-md-6">
                    <h6 class="border-bottom pb-2">Stream Information</h6>
                    <table class="table table-sm">
                        <tr>
                            <th style="width: 40%">Stream ID</th>
                            <td><code>${escapeHtml(channel.stream_id)}</code></td>
                        </tr>
                        <tr>
                            <th>Stream Type</th>
                            <td>${channel.stream_type ? escapeHtml(channel.stream_type) : '<span class="text-muted">-</span>'}</td>
                        </tr>
                        <tr>
                            <th>EPG Channel ID</th>
                            <td>${channel.epg_channel_id ? `<code>${escapeHtml(channel.epg_channel_id)}</code>` : '<span class="text-muted">-</span>'}</td>
                        </tr>
                        <tr>
                            <th>Custom SID</th>
                            <td>${channel.custom_sid ? `<code>${escapeHtml(channel.custom_sid)}</code>` : '<span class="text-muted">-</span>'}</td>
                        </tr>
                    </table>
                </div>
                <div class="col-md-6">
                    <h6 class="border-bottom pb-2">Archive & Status</h6>
                    <table class="table table-sm">
                        <tr>
                            <th style="width: 40%">TV Archive</th>
                            <td>${formatBool(channel.tv_archive)}</td>
                        </tr>
                        <tr>
                            <th>Archive Duration</th>
                            <td>${channel.tv_archive_duration ? `${channel.tv_archive_duration} days` : '<span class="text-muted">-</span>'}</td>
                        </tr>
                        <tr>
                            <th>Active</th>
                            <td>${formatBool(channel.is_active)}</td>
                        </tr>
                        <tr>
                            <th>Visible</th>
                            <td>${formatBool(channel.is_visible)}</td>
                        </tr>
                    </table>
                </div>
            </div>

            <div class="row">
                <div class="col-12">
                    <h6 class="border-bottom pb-2">Metadata</h6>
                    <table class="table table-sm">
                        <tr>
                            <th style="width: 20%">Added (from provider)</th>
                            <td>${channel.added ? formatDate(channel.added * 1000) : '<span class="text-muted">Unknown</span>'}</td>
                        </tr>
                        <tr>
                            <th>Last Seen</th>
                            <td>${formatDate(channel.last_seen)}</td>
                        </tr>
                        <tr>
                            <th>Created At</th>
                            <td>${formatDate(channel.created_at)}</td>
                        </tr>
                        <tr>
                            <th>Updated At</th>
                            <td>${formatDate(channel.updated_at)}</td>
                        </tr>
                    </table>
                </div>
            </div>

            ${channel.direct_source ? `
            <div class="row">
                <div class="col-12">
                    <h6 class="border-bottom pb-2">Direct Source URL</h6>
                    <div class="input-group">
                        <input type="text" class="form-control form-control-sm" value="${escapeHtml(channel.direct_source)}" readonly>
                        <button class="btn btn-outline-secondary btn-sm" type="button" onclick="navigator.clipboard.writeText('${escapeHtml(channel.direct_source)}'); this.innerHTML='<i class=\\'bi bi-check\\'></i> Copied!';">
                            <i class="bi bi-clipboard"></i> Copy
                        </button>
                    </div>
                </div>
            </div>
            ` : ''}

            <div class="row mt-3">
                <div class="col-12">
                    <h6 class="border-bottom pb-2">Playback</h6>
                    <div class="btn-group" role="group">
                        <a class="btn btn-success" href="/player/${channel.account_id}/${channel.stream_id}" target="_blank" title="Play in browser">
                            <i class="bi bi-play-fill"></i> Play in Browser
                        </a>
                        <a class="btn btn-outline-success" href="/stream/${channel.account_id}/${channel.stream_id}.ts" target="_blank" title="Direct TS stream">
                            <i class="bi bi-download"></i> Direct TS
                        </a>
                        <a class="btn btn-outline-success" href="/stream/${channel.account_id}/${channel.stream_id}.m3u8" target="_blank" title="Direct HLS stream">
                            <i class="bi bi-download"></i> Direct HLS
                        </a>
                    </div>
                    <div class="mt-2">
                        <div class="input-group input-group-sm">
                            <span class="input-group-text">Proxy URL</span>
                            <input type="text" class="form-control" value="${window.location.origin}/stream/${channel.account_id}/${channel.stream_id}.ts" readonly>
                            <button class="btn btn-outline-secondary" type="button" onclick="navigator.clipboard.writeText('${window.location.origin}/stream/${channel.account_id}/${channel.stream_id}.ts'); this.innerHTML='<i class=\\'bi bi-check\\'></i>';">
                                <i class="bi bi-clipboard"></i>
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;
    } catch (error) {
        console.error('Error loading channel details:', error);
        contentDiv.innerHTML = `
            <div class="alert alert-danger">
                <i class="bi bi-exclamation-triangle-fill"></i>
                Error loading channel details: ${escapeHtml(error.message)}
            </div>
        `;
    }
}

async function hideChannel(accountId, channelName, button) {
    const originalHtml = button.innerHTML;

    try {
        button.disabled = true;
        button.innerHTML = '<span class="spinner-border spinner-border-sm" role="status"></span>';

        const createResponse = await fetch('/api/filters', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                account_id: parseInt(accountId, 10),
                name: `Hide: ${channelName}`,
                filter_type: 'channel_name',
                filter_action: 'blacklist',
                filter_value: channelName,
                enabled: true,
            }),
        });

        if (!createResponse.ok) {
            const errorData = await createResponse.json();
            throw new Error(errorData.error || 'Failed to create filter');
        }

        const row = button.closest('tr');
        if (row) {
            row.style.transition = 'opacity 0.3s ease-out';
            row.style.opacity = '0';
            setTimeout(() => row.remove(), 300);
        }

        loadedChannels -= 1;
        totalChannels -= 1;
        const countDisplay = document.getElementById('channelCount');
        if (countDisplay && totalChannels > 0) {
            countDisplay.innerHTML = formatChannelCount(loadedChannels, totalChannels);
        }

        showToast(`Channel "${channelName}" hidden`, 'success');
        loadActiveFilters(accountId);
    } catch (error) {
        console.error('Error hiding channel:', error);
        showToast(`Error: ${error.message}`, 'danger');
        button.innerHTML = originalHtml;
    } finally {
        button.disabled = false;
    }
}

function showToast(message, type = 'info') {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'toast-container position-fixed bottom-0 end-0 p-3';
        container.style.zIndex = '1080';
        document.body.appendChild(container);
    }

    const toastId = `toast-${Date.now()}`;
    const bgClass = type === 'success' ? 'bg-success'
        : type === 'danger' ? 'bg-danger'
            : type === 'warning' ? 'bg-warning text-dark' : 'bg-info';

    const toastHtml = `
        <div id="${toastId}" class="toast align-items-center ${bgClass} text-white border-0" role="alert" aria-live="assertive" aria-atomic="true">
            <div class="d-flex">
                <div class="toast-body">
                    ${escapeHtml(message)}
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
        </div>
    `;

    container.insertAdjacentHTML('beforeend', toastHtml);

    const toastElement = document.getElementById(toastId);
    const toast = new bootstrap.Toast(toastElement, { delay: 3000 });
    toast.show();

    toastElement.addEventListener('hidden.bs.toast', () => {
        toastElement.remove();
    });
}

async function loadActiveFilters(accountId) {
    try {
        if (accountId === 'all') {
            document.getElementById('activeFilters').innerHTML = '<p class="text-muted">Viewing all accounts - filters vary by account</p>';
        } else {
            const filtersResponse = await fetch(`/api/accounts/${accountId}/filters`);
            const filters = unwrapData(await filtersResponse.json());

            let filtersHtml = '';
            if (filters.length === 0) {
                filtersHtml = '<p class="text-muted">No filters configured</p>';
            } else {
                filtersHtml = '<ul class="list-group list-group-flush">';
                for (const filter of filters.filter((entry) => entry.enabled)) {
                    const badge = filter.filter_action === 'whitelist' ? 'success' : 'danger';
                    filtersHtml += `
                        <li class="list-group-item d-flex justify-content-between align-items-center">
                            <span>
                                <span class="badge bg-${badge}">${filter.filter_action}</span>
                                <strong>${filter.filter_type}:</strong> ${escapeHtml(filter.filter_value)}
                            </span>
                        </li>
                    `;
                }
                filtersHtml += '</ul>';
            }
            document.getElementById('activeFilters').innerHTML = filtersHtml;
        }
    } catch (error) {
        document.getElementById('activeFilters').innerHTML = '<p class="text-danger">Error loading filters</p>';
    }
}

loadAccounts();

document.addEventListener('DOMContentLoaded', () => {
    const loadPreviewBtn = document.getElementById('load-preview-btn');
    if (loadPreviewBtn) {
        loadPreviewBtn.addEventListener('click', () => loadPreview());
    }

    const downloadBtn = document.getElementById('download-playlist-btn');
    if (downloadBtn) {
        downloadBtn.addEventListener('click', () => downloadPlaylist());
    }

    const clearCategoryBtn = document.getElementById('clearCategoryFilterBtn');
    if (clearCategoryBtn) {
        clearCategoryBtn.addEventListener('click', () => clearCategoryFilter());
    }

    let searchTimeout = null;
    const channelSearchInput = document.getElementById('channelSearch');
    if (channelSearchInput) {
        channelSearchInput.addEventListener('input', () => {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                if (currentAccountId) {
                    loadPreview();
                }
            }, 300);
        });

        channelSearchInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && currentAccountId) {
                clearTimeout(searchTimeout);
                loadPreview();
            }
        });
    }

    const clearSearchBtn = document.getElementById('clearSearchBtn');
    if (clearSearchBtn) {
        clearSearchBtn.addEventListener('click', () => {
            const searchInput = document.getElementById('channelSearch');
            if (searchInput) {
                searchInput.value = '';
                if (currentAccountId) {
                    loadPreview();
                }
            }
        });
    }

    document.getElementById('previewResult').addEventListener('click', (e) => {
        const anyButton = e.target.closest('button, a.btn');

        const tagRuleButton = e.target.closest('button[data-action="create-tag-rule"]');
        if (tagRuleButton) {
            e.stopPropagation();
            createManualTagRule(tagRuleButton.dataset.channelName);
            return;
        }

        const hideChannelButton = e.target.closest('button[data-action="hide-channel"]');
        if (hideChannelButton) {
            e.stopPropagation();
            hideChannel(hideChannelButton.dataset.accountId, hideChannelButton.dataset.channelName, hideChannelButton);
            return;
        }

        const viewDetailsButton = e.target.closest('button[data-action="view-details"]');
        if (viewDetailsButton) {
            e.stopPropagation();
            showChannelDetails(viewDetailsButton.dataset.accountId, viewDetailsButton.dataset.streamId);
            return;
        }

        if (anyButton) {
            return;
        }

        const channelRow = e.target.closest('.channel-row');
        if (channelRow) {
            showChannelDetails(channelRow.dataset.accountId, channelRow.dataset.streamId);
        }
    });

    const testAccountSelect = document.getElementById('testAccountId');
    if (testAccountSelect) {
        testAccountSelect.addEventListener('change', () => {
            if (tagSelector) {
                tagSelector.clear();
            }
        });
    }

    initTagSelector();
});
