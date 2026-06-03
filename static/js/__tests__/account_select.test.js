// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
    fetchAccounts,
    populateAccountSelect,
    populateAccountSelects,
} from '../lib/account_select.js';

describe('fetchAccounts', () => {
    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it('returns account array on success', async () => {
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
            ok: true,
            json: async () => [{ id: 1, name: 'Main' }],
        }));

        await expect(fetchAccounts()).resolves.toEqual([{ id: 1, name: 'Main' }]);
    });

    it('throws when response is not an array', async () => {
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
            ok: true,
            json: async () => ({ error: 'nope' }),
        }));

        await expect(fetchAccounts()).rejects.toThrow('nope');
    });
});

describe('populateAccountSelect', () => {
    it('fills options using textContent (safe)', () => {
        document.body.innerHTML = '<select id="acct"><option value="">All</option></select>';
        const select = document.getElementById('acct');

        populateAccountSelect(select, [
            { id: 2, name: 'Sports <HD>' },
            { id: 3, name: 'News' },
        ], { preserveFirstOption: true });

        expect(select.options.length).toBe(3);
        expect(select.options[0].value).toBe('');
        expect(select.options[1].textContent).toBe('Sports <HD>');
        expect(select.options[1].value).toBe('2');
    });
});

describe('populateAccountSelects', () => {
    it('updates multiple elements by id', () => {
        document.body.innerHTML = `
            <select id="a"></select>
            <select id="b"></select>
        `;

        populateAccountSelects(['a', 'b'], [{ id: 1, name: 'One' }]);

        expect(document.getElementById('a').options.length).toBe(1);
        expect(document.getElementById('b').options[0].textContent).toBe('One');
    });
});
