/**
 * Attach EPG sync progress helpers to window for legacy classic scripts.
 */
import * as EpgProgress from './epg_sync_progress.js';
import { createEpgSyncPoller } from './epg_sync_progress_poll.js';

/**
 * @returns {typeof EpgProgress & { poller: ReturnType<typeof createEpgSyncPoller>, renderTable: Function }}
 */
export function installEpgSyncProgressOnWindow() {
    const epgSyncPoller = createEpgSyncPoller();
    window.EpgSyncProgress = {
        ...EpgProgress,
        poller: epgSyncPoller,
        renderTable(container, sources, formatRelativeTime) {
            EpgProgress.renderEpgSourcesProgressTable(container, sources, formatRelativeTime);
        },
    };
    return window.EpgSyncProgress;
}
