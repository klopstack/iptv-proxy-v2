import { describe, expect, it } from 'vitest';
import {
    formatProgressDetail,
    getPhaseBadgeClass,
    indexSourcesById,
    isLiveSyncStatus,
    PHASE_LABEL,
    renderSourceRowStatusHtml,
} from '../lib/epg_sync_progress.js';

describe('formatProgressDetail', () => {
    it('uses progress message when present', () => {
        expect(
            formatProgressDetail({
                progress: { message: 'Downloading guide' },
            })
        ).toBe('Downloading guide');
    });

    it('falls back to last_sync_message on error', () => {
        expect(
            formatProgressDetail({
                sync_phase: 'error',
                last_sync_message: 'HTTP 500',
                progress: {},
            })
        ).toBe('HTTP 500');
    });

    it('formats programme counters', () => {
        const detail = formatProgressDetail({
            progress: {
                programmes_parsed: 1200,
                programmes_total_estimate: 5000,
                programs_added: 40,
            },
        });
        expect(detail).toContain('1200');
        expect(detail).toContain('5000');
        expect(detail).toContain('+40 added');
    });
});

describe('getPhaseBadgeClass', () => {
    it('uses primary while in progress', () => {
        expect(getPhaseBadgeClass({ sync_in_progress: true, sync_phase: 'fetching' })).toBe('bg-primary');
    });

    it('uses danger for error phase', () => {
        expect(getPhaseBadgeClass({ sync_in_progress: false, sync_phase: 'error' })).toBe('bg-danger');
    });

    it('uses secondary for skipped phase', () => {
        expect(getPhaseBadgeClass({ sync_in_progress: false, sync_phase: 'skipped' })).toBe('bg-secondary');
    });
});

describe('isLiveSyncStatus', () => {
    it('is true for active phases', () => {
        expect(isLiveSyncStatus({ sync_in_progress: false, sync_phase: 'programs' })).toBe(true);
    });

    it('is false for idle', () => {
        expect(isLiveSyncStatus({ sync_in_progress: false, sync_phase: 'idle' })).toBe(false);
    });
});

describe('renderSourceRowStatusHtml', () => {
    it('includes phase label and detail', () => {
        const html = renderSourceRowStatusHtml({
            sync_phase: 'fetching',
            sync_in_progress: true,
            progress: { message: 'test' },
        });
        expect(html).toContain(PHASE_LABEL.fetching);
        expect(html).toContain('test');
        expect(html).toContain('spinner-border');
    });
});

describe('indexSourcesById', () => {
    it('maps source_id to row', () => {
        const map = indexSourcesById([
            { source_id: 1, sync_phase: 'queued' },
            { source_id: 2, sync_phase: 'idle' },
        ]);
        expect(map[1].sync_phase).toBe('queued');
        expect(map[2].sync_phase).toBe('idle');
    });
});
