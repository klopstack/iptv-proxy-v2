import { describe, expect, it } from 'vitest';
import {
    accountCredentialsUrl,
    accountPath,
    accountPpvVisibilityUrl,
    accountXmltvEpgSourceUrl,
    ppvVisibilityOptionsUrl,
} from '../lib/account_api.js';

describe('accountPath', () => {
    it('builds base account URL', () => {
        expect(accountPath(5)).toBe('/api/accounts/5');
    });

    it('builds sub-resource URLs', () => {
        expect(accountPath(5, 'sync/status')).toBe('/api/accounts/5/sync/status');
        expect(accountPath(5, '/ppv-visibility')).toBe('/api/accounts/5/ppv-visibility');
    });
});

describe('account sub-resource URLs', () => {
    it('ppv visibility', () => {
        expect(accountPpvVisibilityUrl(12)).toBe('/api/accounts/12/ppv-visibility');
    });

    it('xmltv epg source', () => {
        expect(accountXmltvEpgSourceUrl(3)).toBe('/api/accounts/3/xmltv-epg-source');
        expect(accountXmltvEpgSourceUrl(3, { sync: true })).toBe(
            '/api/accounts/3/xmltv-epg-source?sync=true',
        );
    });

    it('credentials', () => {
        expect(accountCredentialsUrl(1)).toBe('/api/accounts/1/credentials');
        expect(accountCredentialsUrl(1, 9)).toBe('/api/accounts/1/credentials/9');
    });

    it('ppv visibility options', () => {
        expect(ppvVisibilityOptionsUrl()).toBe('/api/ppv-visibility-options');
    });
});
