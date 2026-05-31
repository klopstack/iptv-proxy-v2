/**
 * PPV page: expose account and PPV API helpers to legacy inline scripts.
 */
import * as AccountApi from '../lib/account_api.js';
import * as PpvApi from '../lib/ppv_api.js';

window.AccountApi = AccountApi;
window.PpvApi = PpvApi;
