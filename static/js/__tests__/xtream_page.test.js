// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { PPV_RENAME_TIMEZONE_OPTIONS } from '../pages/xtream_page.js';

describe('PPV_RENAME_TIMEZONE_OPTIONS', () => {
    it('includes common IANA zones used by the credential modal', () => {
        expect(PPV_RENAME_TIMEZONE_OPTIONS).toContain('America/New_York');
        expect(PPV_RENAME_TIMEZONE_OPTIONS).toContain('America/Chicago');
        expect(PPV_RENAME_TIMEZONE_OPTIONS).toContain('UTC');
        expect(PPV_RENAME_TIMEZONE_OPTIONS).toHaveLength(10);
    });
});
