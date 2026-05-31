import { describe, expect, it, beforeEach, afterEach, vi } from 'vitest';
import { installEpgSyncProgressOnWindow } from '../lib/install_epg_sync_progress.js';

describe('installEpgSyncProgressOnWindow', () => {
    const original = globalThis.window?.EpgSyncProgress;

    beforeEach(() => {
        globalThis.window = {
            addEventListener: vi.fn(),
            removeEventListener: vi.fn(),
        };
    });

    afterEach(() => {
        if (original === undefined) {
            delete globalThis.window.EpgSyncProgress;
        } else {
            globalThis.window.EpgSyncProgress = original;
        }
    });

    it('installs EpgSyncProgress with poller and renderTable', () => {
        const api = installEpgSyncProgressOnWindow();
        expect(globalThis.window.EpgSyncProgress).toBe(api);
        expect(api.poller).toBeDefined();
        expect(typeof api.poller.start).toBe('function');
        expect(typeof api.renderTable).toBe('function');
        expect(typeof api.renderEpgSourcesProgressTable).toBe('function');
        expect(typeof api.indexSourcesById).toBe('function');
    });
});
