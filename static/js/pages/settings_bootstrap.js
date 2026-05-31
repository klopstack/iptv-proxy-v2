import { installEpgSyncProgressOnWindow } from '../lib/install_epg_sync_progress.js';
import * as PpvApi from '../lib/ppv_api.js';

installEpgSyncProgressOnWindow();
window.PpvApi = PpvApi;
