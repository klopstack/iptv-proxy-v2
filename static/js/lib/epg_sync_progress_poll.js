/**
 * Poll GET /api/sync/epg/status while any source is syncing.
 */

const DEFAULT_POLL_MS = 5000;

/**
 * @param {{ intervalMs?: number }} [options]
 */
export function createEpgSyncPoller(options = {}) {
    const pollMs = options.intervalMs ?? DEFAULT_POLL_MS;
    let timer = null;
    const subscribers = new Set();

    async function pollOnce() {
        try {
            const response = await fetch('/api/sync/epg/status');
            if (!response.ok) return null;
            const data = await response.json();
            const sources = data.sources || [];
            subscribers.forEach((cb) => {
                try {
                    cb(sources, data);
                } catch (err) {
                    console.error('EPG sync progress callback error:', err);
                }
            });

            const anyRunning = sources.some((s) => s.sync_in_progress);
            if (anyRunning) {
                if (!timer) {
                    timer = setInterval(pollOnce, pollMs);
                }
            } else if (timer) {
                clearInterval(timer);
                timer = null;
            }
            return data;
        } catch (err) {
            console.error('EPG progress poll failed', err);
            return null;
        }
    }

    function start(callback) {
        if (callback) {
            subscribers.add(callback);
        }
        return pollOnce();
    }

    function stop(callback) {
        if (callback) {
            subscribers.delete(callback);
        }
        if (subscribers.size === 0 && timer) {
            clearInterval(timer);
            timer = null;
        }
    }

    function stopAll() {
        subscribers.clear();
        if (timer) {
            clearInterval(timer);
            timer = null;
        }
    }

    if (typeof window !== 'undefined') {
        window.addEventListener('pagehide', stopAll);
    }

    return {
        pollMs,
        pollOnce,
        start,
        stop,
        stopAll,
    };
}
