/**
 * Main dashboard (TODO 106): Tier-1 from /api/dashboard/summary, deferred sections in parallel.
 */
import { unwrapData } from '../lib/api_contract.js';
import { escapeHtml } from '../lib/escape_html.js';
import { parseUtcTimestamp } from '../lib/epg_datetime.js';

function formatRelativeTime(date) {
    const parsed = parseUtcTimestamp(date);
    if (!parsed || Number.isNaN(parsed.getTime())) return 'Unknown';

    const now = new Date();
    const diffMs = now - parsed;
    const diffSecs = Math.floor(diffMs / 1000);
    const diffMins = Math.floor(diffSecs / 60);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffSecs < 60) return 'just now';
    if (diffMins < 60) return `${diffMins} minute${diffMins > 1 ? 's' : ''} ago`;
    if (diffHours < 24) return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`;
    if (diffDays < 7) return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`;
    return parsed.toLocaleDateString();
}

function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / k ** i).toFixed(1))} ${sizes[i]}`;
}

function renderSyncAlerts(overview) {
    const scheduler = overview.scheduler || {};
    const accounts = overview.accounts || {};
    if (!scheduler.has_sync_issues) {
        return '';
    }

    const failedJobs = (scheduler.failed_jobs || [])
        .map((j) => `<li><strong>${escapeHtml(j.job)}</strong>: ${escapeHtml(j.last_error || 'Unknown error')}</li>`)
        .join('');
    const failedAccounts = (accounts.failed_sync_accounts || [])
        .map((a) => `<li><a href="/accounts">${escapeHtml(a.name)}</a></li>`)
        .join('');

    return `
        <div class="row mb-4">
            <div class="col-md-12">
                <div class="alert alert-danger">
                    <i class="bi bi-exclamation-octagon"></i>
                    <strong>Sync issues detected</strong>
                    ${failedJobs ? `<ul class="mb-1 mt-2">${failedJobs}</ul>` : ''}
                    ${failedAccounts ? `<div>Failed accounts (${accounts.failed_sync_count || 0}):</div><ul class="mb-0">${failedAccounts}</ul>` : ''}
                </div>
            </div>
        </div>
    `;
}

function renderPpvCard(ppv) {
    if (!ppv) {
        return '';
    }

    const events = ppv.events || {};
    const enrichment = ppv.enrichment || {};
    const upcoming24 = (events.upcoming_24h || 0).toLocaleString();
    const upcoming48 = (events.upcoming_48h || 0).toLocaleString();
    const withoutChannels = events.without_channels || 0;
    const channelLinks = (ppv.channel_links || 0).toLocaleString();
    const ppvChannels = (ppv.ppv_channels || 0).toLocaleString();
    const queued = enrichment.queued_count || 0;
    const noMatch = enrichment.no_match_count || 0;
    const recentlyEnriched = enrichment.recently_enriched_24h || 0;
    const hasIssues = Boolean(ppv.has_issues);
    const enrichmentOff = enrichment.enabled === false;

    let issueBadges = '';
    if (withoutChannels > 0) {
        issueBadges += `<span class="badge bg-warning text-dark me-1">${withoutChannels} unlinked (48h)</span>`;
    }
    if (noMatch > 0) {
        issueBadges += `<span class="badge bg-danger me-1">${noMatch} no match</span>`;
    }
    if (queued > 0) {
        issueBadges += `<span class="badge bg-info text-dark me-1">${queued.toLocaleString()} queued</span>`;
    }
    if (enrichmentOff && queued > 0) {
        issueBadges += `<span class="badge bg-secondary me-1">enrichment off</span>`;
    }

    return `
        <div class="row mb-4">
            <div class="col-md-12">
                <div class="card h-100 ${hasIssues ? 'border-warning' : ''}">
                    <div class="card-header d-flex justify-content-between align-items-center flex-wrap gap-2">
                        <h6 class="mb-0"><i class="bi bi-calendar-event"></i> Pay-Per-View</h6>
                        <div class="d-flex align-items-center gap-2 flex-wrap">
                            ${issueBadges}
                            <a href="/ppv" class="btn btn-sm btn-outline-primary">Manage PPV</a>
                        </div>
                    </div>
                    <div class="card-body">
                        <div class="row text-center g-3">
                            <div class="col-6 col-md-2">
                                <div class="h5 mb-0">${upcoming24}</div>
                                <small class="text-muted">Upcoming 24h</small>
                            </div>
                            <div class="col-6 col-md-2">
                                <div class="h5 mb-0">${upcoming48}</div>
                                <small class="text-muted">Upcoming 48h</small>
                            </div>
                            <div class="col-6 col-md-2">
                                <div class="h5 mb-0 ${withoutChannels > 0 ? 'text-warning' : ''}">${withoutChannels.toLocaleString()}</div>
                                <small class="text-muted">Unlinked events</small>
                            </div>
                            <div class="col-6 col-md-2">
                                <div class="h5 mb-0">${channelLinks}</div>
                                <small class="text-muted">Channel links</small>
                            </div>
                            <div class="col-6 col-md-2">
                                <div class="h5 mb-0">${ppvChannels}</div>
                                <small class="text-muted">PPV channels</small>
                            </div>
                            <div class="col-6 col-md-2">
                                <div class="h5 mb-0">${recentlyEnriched.toLocaleString()}</div>
                                <small class="text-muted">Enriched 24h</small>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;
}

function credentialBadgeClass(cred) {
    if (!cred.enabled) {
        return 'bg-secondary';
    }
    const active = cred.active_connections || 0;
    const max = cred.max_connections || 1;
    if (active >= max) {
        return 'bg-warning text-dark';
    }
    if (active > 0) {
        return 'bg-success';
    }
    return 'bg-light text-dark border';
}

function renderCredentialBadge(cred) {
    const active = cred.active_connections || 0;
    const max = cred.max_connections || 1;
    const label = cred.enabled ? `${escapeHtml(cred.username)} ${active}/${max}` : `${escapeHtml(cred.username)} (disabled)`;
    return `<span class="badge ${credentialBadgeClass(cred)} me-1 mb-1">${label}</span>`;
}

function renderStreamingCredentials(streams) {
    const accounts = streams.accounts || [];
    const activeStreams = streams.active_streams || [];
    const backend = streams.backend || 'ffmpeg';
    const sharedUpstream = streams.shared_upstream || 0;
    const subscribers = streams.subscribers || 0;
    const totalActive = streams.total_active_connections ?? streams.active_sessions ?? 0;
    const totalMax = streams.total_max_connections || 0;
    const available = streams.available_connections ?? Math.max(0, totalMax - totalActive);

    if (accounts.length === 0) {
        return '';
    }

    const accountBlocks = accounts.map((account) => {
        const creds = (account.credentials || []).map(renderCredentialBadge).join('');
        const inUse = account.total_active_connections || 0;
        const capacity = account.total_max_connections || 0;
        const disabledNote = account.enabled ? '' : ' <span class="badge bg-secondary">account disabled</span>';
        return `
            <div class="mb-3">
                <div class="d-flex justify-content-between align-items-center flex-wrap gap-2 mb-2">
                    <strong>${escapeHtml(account.name)}</strong>
                    <span class="text-muted small">${inUse}/${capacity} slots in use · ${account.available_connections ?? 0} free${disabledNote}</span>
                </div>
                <div>${creds || '<span class="text-muted small">No credentials configured</span>'}</div>
            </div>
        `;
    }).join('');

    let activeStreamsTable = '';
    if (activeStreams.length > 0) {
        const rows = activeStreams.map((stream) => `
            <tr>
                <td><code>${escapeHtml(stream.stream_id)}</code></td>
                <td>${escapeHtml(stream.credential_username || '—')}</td>
                <td>${escapeHtml(stream.account_name || '—')}</td>
                <td><code>${escapeHtml(stream.client_ip || '—')}</code></td>
                <td class="text-muted small">${escapeHtml(formatRelativeTime(stream.started_at))}</td>
            </tr>
        `).join('');
        activeStreamsTable = `
            <div class="table-responsive mt-3">
                <table class="table table-sm table-striped mb-0">
                    <thead>
                        <tr>
                            <th>Stream</th>
                            <th>Credential</th>
                            <th>Account</th>
                            <th>Client</th>
                            <th>Started</th>
                        </tr>
                    </thead>
                    <tbody>${rows}</tbody>
                </table>
            </div>
        `;
    } else {
        activeStreamsTable = '<p class="text-muted small mb-0 mt-3">No active streams right now.</p>';
    }

    let backendDetail = `<span class="text-muted small">Backend: ${escapeHtml(backend)}</span>`;
    if (backend === 'ffmpeg' && (sharedUpstream > 0 || subscribers > 0)) {
        backendDetail += `<span class="text-muted small"> · Shared upstream: ${sharedUpstream.toLocaleString()}`;
        if (subscribers > 0) {
            backendDetail += ` · Multiplex viewers: ${subscribers.toLocaleString()}`;
        }
        backendDetail += '</span>';
    }

    return `
        <div class="row mb-4">
            <div class="col-md-12">
                <div class="card h-100">
                    <div class="card-header d-flex justify-content-between align-items-center flex-wrap gap-2">
                        <h6 class="mb-0"><i class="bi bi-broadcast"></i> Stream credentials</h6>
                        <div class="d-flex align-items-center gap-2 flex-wrap">
                            <span class="badge bg-dark">${totalActive}/${totalMax} in use</span>
                            <span class="badge bg-secondary">${available} available</span>
                            <a href="/accounts" class="btn btn-sm btn-outline-primary">Manage accounts</a>
                        </div>
                    </div>
                    <div class="card-body">
                        ${accountBlocks}
                        ${activeStreamsTable}
                        <div class="mt-3">${backendDetail}</div>
                    </div>
                </div>
            </div>
        </div>
    `;
}

function renderMemoryCard(memory) {
    if (!memory) {
        return '';
    }

    const process = memory.process || {};
    const caches = memory.caches || {};
    const calendar = caches.calendar || {};
    const iptv = caches.iptv || {};
    const streams = caches.streams || {};

    const rss = process.rss_bytes ? formatBytes(process.rss_bytes) : 'n/a';
    const calendarTotal = (calendar.total_entries || 0).toLocaleString();
    const calendarValid = (calendar.valid_entries || 0).toLocaleString();
    const calendarEvents = (calendar.total_events || 0).toLocaleString();
    const iptvLive = (iptv.live_entries || 0).toLocaleString();
    const iptvExpired = (iptv.expired_entries || 0).toLocaleString();
    const activeStreams = (streams.active_streams || 0).toLocaleString();
    const subscribers = (streams.total_subscribers || 0).toLocaleString();

    return `
        <div class="row mb-4">
            <div class="col-md-12">
                <div class="card h-100">
                    <div class="card-header d-flex justify-content-between align-items-center flex-wrap gap-2">
                        <h6 class="mb-0"><i class="bi bi-memory"></i> Memory &amp; Caches</h6>
                        <span class="badge bg-dark">Worker RSS: ${rss}</span>
                    </div>
                    <div class="card-body">
                        <div class="row text-center g-3">
                            <div class="col-6 col-md-3">
                                <div class="h5 mb-0">${calendarValid} / ${calendarTotal}</div>
                                <small class="text-muted">Calendar cache (valid/total)</small>
                            </div>
                            <div class="col-6 col-md-3">
                                <div class="h5 mb-0">${calendarEvents}</div>
                                <small class="text-muted">Cached calendar events</small>
                            </div>
                            <div class="col-6 col-md-3">
                                <div class="h5 mb-0">${iptvLive} <span class="text-muted">/ ${iptvExpired} exp</span></div>
                                <small class="text-muted">IPTV cache (live/expired)</small>
                            </div>
                            <div class="col-6 col-md-3">
                                <div class="h5 mb-0">${activeStreams}${subscribers !== '0' ? ` · ${subscribers}` : ''}</div>
                                <small class="text-muted">Active streams${subscribers !== '0' ? ' · viewers' : ''}</small>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;
}

function renderTier1(summary) {
    const health = summary.channel_health || {};
    const byStatus = health.by_status || {};
    const streams = summary.streams || {};
    const downCount = byStatus.down || 0;
    const healthHref = downCount > 0 ? '/channel-health?status=down' : '/channel-health';

    const healthy = (byStatus.healthy || 0).toLocaleString();
    const degraded = (byStatus.degraded || 0).toLocaleString();
    const down = downCount.toLocaleString();
    const unknown = (byStatus.unknown || 0).toLocaleString();
    const total = (health.total || 0).toLocaleString();

    const activeSessions = (streams.active_sessions || 0).toLocaleString();
    const totalActive = streams.total_active_connections ?? streams.active_sessions ?? 0;
    const totalMax = streams.total_max_connections || 0;
    const available = streams.available_connections ?? Math.max(0, totalMax - totalActive);
    const subscribers = streams.subscribers || 0;

    return `
        ${renderSyncAlerts(summary.overview || {})}
        <div class="row mb-4">
            <div class="col-md-4 mb-3">
                <div class="card h-100 ${downCount > 0 ? 'border-danger' : ''}">
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <h6 class="mb-0"><i class="bi bi-heart-pulse"></i> Channel Health</h6>
                        <a href="${healthHref}" class="btn btn-sm btn-outline-primary">Details</a>
                    </div>
                    <div class="card-body">
                        <div class="row text-center g-2">
                            <div class="col-4">
                                <div class="h5 mb-0 text-success">${healthy}</div>
                                <small class="text-muted">Healthy</small>
                            </div>
                            <div class="col-4">
                                <div class="h5 mb-0 text-warning">${degraded}</div>
                                <small class="text-muted">Degraded</small>
                            </div>
                            <div class="col-4">
                                <div class="h5 mb-0 text-danger">${down}</div>
                                <small class="text-muted">Down</small>
                            </div>
                            <div class="col-6">
                                <div class="h6 mb-0">${unknown}</div>
                                <small class="text-muted">Unknown</small>
                            </div>
                            <div class="col-6">
                                <div class="h6 mb-0">${total}</div>
                                <small class="text-muted">In playlist</small>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            <div class="col-md-4 mb-3">
                <div class="card bg-dark text-white h-100">
                    <div class="card-body">
                        <h6 class="card-subtitle mb-2 opacity-75">Connection slots</h6>
                        <h2 class="card-title mb-1">${totalActive.toLocaleString()} / ${totalMax.toLocaleString()}</h2>
                        <small class="opacity-75">${available.toLocaleString()} available across upstream credentials</small>
                    </div>
                </div>
            </div>
            <div class="col-md-4 mb-3">
                <div class="card bg-secondary text-white h-100">
                    <div class="card-body">
                        <h6 class="card-subtitle mb-2 opacity-75">Active sessions</h6>
                        <h2 class="card-title mb-1">${activeSessions}</h2>
                        <small class="opacity-75">Proxied client streams</small>
                        ${subscribers > 0 ? `<br><small class="opacity-75">Multiplex viewers: ${subscribers.toLocaleString()}</small>` : ''}
                    </div>
                </div>
            </div>
        </div>
        ${renderStreamingCredentials(streams)}
        ${renderPpvCard(summary.ppv)}
        ${renderMemoryCard(summary.memory)}
    `;
}

function renderOverviewCards(stats) {
    return `
        <div class="row mb-4" id="dashboard-overview-cards">
            <div class="col-md-3 mb-3">
                <div class="card bg-primary text-white h-100">
                    <div class="card-body">
                        <h6 class="card-subtitle mb-2 opacity-75">Accounts</h6>
                        <h2 class="card-title mb-0">${stats.accounts.enabled} / ${stats.accounts.total}</h2>
                        <small class="opacity-75">${stats.accounts.synced} synced</small>
                    </div>
                </div>
            </div>
            <div class="col-md-3 mb-3">
                <div class="card bg-success text-white h-100">
                    <div class="card-body">
                        <h6 class="card-subtitle mb-2 opacity-75">Channels</h6>
                        <h2 class="card-title mb-0">${stats.channels.visible.toLocaleString()}</h2>
                        <small class="opacity-75">${stats.channels.total.toLocaleString()} total, ${stats.channels.ppv} PPV</small>
                    </div>
                </div>
            </div>
            <div class="col-md-3 mb-3">
                <div class="card bg-info text-white h-100">
                    <div class="card-body">
                        <h6 class="card-subtitle mb-2 opacity-75">EPG Data</h6>
                        <h2 class="card-title mb-0">${stats.epg.programs.toLocaleString()}</h2>
                        <small class="opacity-75">${stats.epg.coverage.percentage}% coverage, ${stats.epg.sources.enabled} sources</small>
                    </div>
                </div>
            </div>
            <div class="col-md-3 mb-3">
                <div class="card bg-warning text-dark h-100">
                    <div class="card-body">
                        <h6 class="card-subtitle mb-2">Tags</h6>
                        <h2 class="card-title mb-0">${stats.tags.total}</h2>
                        <small>${stats.tags.tagged_channels.toLocaleString()} tagged channels</small>
                    </div>
                </div>
            </div>
        </div>
    `;
}

function renderSchedulerCard(stats) {
    const scheduler = stats.scheduler;
    if (!scheduler) {
        return '';
    }
    if (scheduler.running) {
        const lastAccountSync = scheduler.last_syncs?.accounts
            ? formatRelativeTime(scheduler.last_syncs.accounts)
            : 'Never';
        const lastEpgSync = scheduler.last_syncs?.epg
            ? formatRelativeTime(scheduler.last_syncs.epg)
            : 'Never';
        return `
            <div class="row mb-4">
                <div class="col-md-12">
                    <div class="card border-success">
                        <div class="card-header bg-success text-white d-flex justify-content-between align-items-center">
                            <h6 class="mb-0"><i class="bi bi-arrow-repeat"></i> Scheduler Status</h6>
                            <span class="badge bg-light text-success"><i class="bi bi-check-circle"></i> Running</span>
                        </div>
                        <div class="card-body">
                            <div class="row">
                                <div class="col-md-6">
                                    <strong>Accounts Sync:</strong> Every ${scheduler.intervals.accounts}h
                                    <br><small class="text-muted">Last: ${lastAccountSync}</small>
                                </div>
                                <div class="col-md-6">
                                    <strong>EPG Sync:</strong> Every ${scheduler.intervals.epg}h
                                    <br><small class="text-muted">Last: ${lastEpgSync}</small>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }
    return `
        <div class="row mb-4">
            <div class="col-md-12">
                <div class="alert alert-warning">
                    <i class="bi bi-exclamation-triangle"></i>
                    <strong>Scheduler Not Running</strong> —
                    Automatic syncs are disabled. Go to <a href="/settings">Settings</a> to enable.
                </div>
            </div>
        </div>
    `;
}

async function loadOverviewStatsDeferred() {
    try {
        const response = await fetch('/api/overview/stats');
        const stats = unwrapData(await response.json());
        const container = document.getElementById('dashboard-deferred');
        if (!container) return;
        container.insertAdjacentHTML('afterbegin', renderOverviewCards(stats) + renderSchedulerCard(stats));
    } catch (error) {
        console.error('Error loading overview stats:', error);
    }
}

async function loadTagPlaylistsDeferred() {
    const container = document.getElementById('dashboard-deferred');
    if (!container) return;
    try {
        const response = await fetch('/api/playlist-configs');
        const playlists = await response.json();
        if (!Array.isArray(playlists) || playlists.length === 0) {
            return;
        }

        let rows = '';
        for (const playlist of playlists) {
            const tagBadges = playlist.include_tags.slice(0, 3)
                .map((t) => `<span class="badge bg-primary me-1">${escapeHtml(t)}</span>`)
                .join('');
            const moreTags = playlist.include_tags.length > 3
                ? `<span class="badge bg-secondary">+${playlist.include_tags.length - 3} more</span>`
                : '';
            const playlistUrl = `/playlist/config/${playlist.slug}.m3u`;
            rows += `
                <tr>
                    <td>
                        <strong>${escapeHtml(playlist.name)}</strong>
                        ${!playlist.enabled ? '<span class="badge bg-secondary ms-1">Disabled</span>' : ''}
                    </td>
                    <td>${tagBadges}${moreTags}</td>
                    <td>
                        <div class="btn-group btn-group-sm">
                            <a href="${playlistUrl}" target="_blank" class="btn btn-outline-success" title="Download playlist">
                                <i class="bi bi-download"></i>
                            </a>
                            <button type="button" class="btn btn-outline-secondary dashboard-copy-url" data-url="${escapeHtml(`${window.location.origin}${playlistUrl}`)}" title="Copy URL">
                                <i class="bi bi-clipboard"></i>
                            </button>
                        </div>
                    </td>
                </tr>
            `;
        }

        container.insertAdjacentHTML('beforeend', `
            <div class="row mt-4">
                <div class="col-md-12">
                    <div class="card">
                        <div class="card-header bg-info text-white d-flex justify-content-between align-items-center">
                            <h5 class="mb-0"><i class="bi bi-collection-play"></i> Tag Playlists</h5>
                            <a href="/rulesets#playlists" class="btn btn-sm btn-light"><i class="bi bi-gear"></i> Manage</a>
                        </div>
                        <div class="card-body">
                            <div class="table-responsive">
                                <table class="table table-sm table-hover mb-0">
                                    <thead><tr><th>Name</th><th>Tags</th><th>Actions</th></tr></thead>
                                    <tbody>${rows}</tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `);
        container.querySelectorAll('.dashboard-copy-url').forEach((btn) => {
            btn.addEventListener('click', () => copyToClipboard(btn.dataset.url));
        });
    } catch (error) {
        console.error('Error loading tag playlists:', error);
    }
}

async function loadImageCacheDeferred() {
    const container = document.getElementById('dashboard-deferred');
    if (!container) return;
    try {
        const response = await fetch('/api/image-cache/stats');
        const cacheStats = await response.json();
        const hitRate = cacheStats.total_fetches > 0
            ? ((cacheStats.total_hits / cacheStats.total_fetches) * 100).toFixed(1)
            : 0;

        container.insertAdjacentHTML('beforeend', `
            <div class="row mt-4">
                <div class="col-md-12">
                    <div class="card">
                        <div class="card-header bg-success text-white d-flex justify-content-between align-items-center">
                            <h5 class="mb-0"><i class="bi bi-image"></i> Image Cache</h5>
                            <a href="/settings#image-cache" class="btn btn-sm btn-light"><i class="bi bi-gear"></i> Manage</a>
                        </div>
                        <div class="card-body">
                            <div class="row text-center">
                                <div class="col-md-3 col-6 mb-2">
                                    <div class="h4 mb-0 text-primary">${cacheStats.cached_images.toLocaleString()}</div>
                                    <small class="text-muted">Cached Images</small>
                                </div>
                                <div class="col-md-3 col-6 mb-2">
                                    <div class="h4 mb-0 text-info">${formatBytes(cacheStats.total_size_bytes)}</div>
                                    <small class="text-muted">Cache Size</small>
                                </div>
                                <div class="col-md-3 col-6 mb-2">
                                    <div class="h4 mb-0 text-success">${hitRate}%</div>
                                    <small class="text-muted">Hit Rate</small>
                                </div>
                                <div class="col-md-3 col-6 mb-2">
                                    <div class="h4 mb-0 text-warning">${cacheStats.total_hits.toLocaleString()}</div>
                                    <small class="text-muted">Cache Hits</small>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `);
    } catch (error) {
        console.error('Error loading image cache stats:', error);
    }
}

function renderQuickActions() {
    return `
        <div class="row mt-4">
            <div class="col-md-12">
                <h3>Quick Actions</h3>
                <div class="list-group">
                    <a href="/accounts" class="list-group-item list-group-item-action">
                        <i class="bi bi-plus-circle"></i> Manage Accounts
                    </a>
                    <a href="/channel-health" class="list-group-item list-group-item-action">
                        <i class="bi bi-heart-pulse"></i> Channel Health
                    </a>
                    <a href="/ppv" class="list-group-item list-group-item-action">
                        <i class="bi bi-calendar-event"></i> PPV Management
                    </a>
                    <a href="/filters" class="list-group-item list-group-item-action">
                        <i class="bi bi-funnel-fill"></i> Manage Filters
                    </a>
                    <a href="/rulesets" class="list-group-item list-group-item-action">
                        <i class="bi bi-tags-fill"></i> Manage Tags &amp; Rulesets
                    </a>
                    <a href="/rulesets#playlists" class="list-group-item list-group-item-action">
                        <i class="bi bi-collection-play"></i> Tag Playlists
                    </a>
                    <a href="/settings" class="list-group-item list-group-item-action">
                        <i class="bi bi-gear-fill"></i> Settings &amp; Scheduler
                    </a>
                    <a href="/preview" class="list-group-item list-group-item-action">
                        <i class="bi bi-play-circle"></i> Test Playlists
                    </a>
                </div>
            </div>
        </div>
    `;
}

function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        const toast = document.createElement('div');
        toast.className = 'position-fixed bottom-0 end-0 p-3';
        toast.style.zIndex = '9999';
        toast.innerHTML = `
            <div class="toast show" role="alert">
                <div class="toast-body bg-success text-white rounded">
                    <i class="bi bi-check-circle"></i> URL copied to clipboard!
                </div>
            </div>
        `;
        document.body.appendChild(toast);
        setTimeout(() => toast.remove(), 2000);
    }).catch((err) => {
        alert(`Failed to copy: ${err.message}`);
    });
}

async function loadDashboard() {
    const content = document.getElementById('dashboard-content');
    if (!content) return;

    try {
        const response = await fetch('/api/dashboard/summary');
        const summary = unwrapData(await response.json());

        content.innerHTML = `
            <div id="dashboard-tier1">${renderTier1(summary)}</div>
            <div id="dashboard-deferred">
                <div class="row mb-3">
                    <div class="col-md-12">
                        <div class="text-muted small"><span class="spinner-border spinner-border-sm me-1"></span> Loading overview…</div>
                    </div>
                </div>
            </div>
            ${renderQuickActions()}
        `;

        const deferred = document.getElementById('dashboard-deferred');
        const loadingRow = deferred?.querySelector('.row.mb-3');

        await Promise.all([
            loadOverviewStatsDeferred(),
            loadTagPlaylistsDeferred(),
            loadImageCacheDeferred(),
        ]);

        if (loadingRow) {
            loadingRow.remove();
        }
    } catch (error) {
        content.innerHTML = `
            <div class="alert alert-danger">
                <i class="bi bi-exclamation-triangle"></i> Error loading dashboard: ${escapeHtml(error.message)}
            </div>
        `;
    }
}

loadDashboard();
