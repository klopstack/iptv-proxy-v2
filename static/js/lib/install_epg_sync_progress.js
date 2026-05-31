import * as EpgProgress from './epg_sync_progress.js';
import { createEpgSyncPoller } from './epg_sync_progress_poll.js';

export function installEpgSyncProgressOnWindow() {
    const epgSyncPoller = createEpgSyncPoller();
    window.EpgSyncProgress = {
        ...EpgProgress,
        poller: epgSyncPoller,
        renderTable(container, sources, formatRelativeTime) {
            EpgProgress.renderEpgSourcesProgressTable(container, sources, formatRelativeTime);
        },
    };
}
