import { describe, expect, it } from 'vitest';
import {
    buildAssignedAccountsBadgeHtml,
    formatAssignedAccountsTitle,
} from '../lib/match_rules_rulesets_helpers.js';

describe('formatAssignedAccountsTitle', () => {
    it('joins account names', () => {
        expect(
            formatAssignedAccountsTitle([{ name: 'Main' }, { name: 'Backup' }]),
        ).toBe('Main, Backup');
    });
});

describe('buildAssignedAccountsBadgeHtml', () => {
    it('returns empty string when no assignments', () => {
        expect(buildAssignedAccountsBadgeHtml([])).toBe('');
    });

    it('includes account count and title', () => {
        const html = buildAssignedAccountsBadgeHtml([{ name: 'Main' }]);
        expect(html).toContain('1 account');
        expect(html).toContain('title="Assigned to: Main"');
    });

    it('uses plural label for multiple accounts', () => {
        const html = buildAssignedAccountsBadgeHtml([{ name: 'A' }, { name: 'B' }]);
        expect(html).toContain('2 accounts');
    });
});
