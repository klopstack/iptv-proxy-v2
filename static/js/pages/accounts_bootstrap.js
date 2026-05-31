/**
 * Accounts page: expose account API helpers to legacy inline scripts.
 */
import * as AccountApi from '../lib/account_api.js';

window.AccountApi = AccountApi;
