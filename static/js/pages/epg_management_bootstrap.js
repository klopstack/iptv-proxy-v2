/**
 * EPG management page: expose lib helpers to legacy classic script bundles.
 */
import {
    fetchAccounts,
    populateAccountSelect,
    populateAccountSelects,
} from '../lib/account_select.js';
import { debounce, escapeJsSingleQuoted } from '../lib/epg_dom_utils.js';
import { escapeHtml } from '../lib/escape_html.js';
import {
    formatLocalDate,
    formatLocalDateTime,
    formatLocalTime,
    formatProgramTimeRange,
    formatRelativeTime,
    parseUTCDateTime,
} from '../lib/epg_datetime.js';
import {
    getSourceTypeFieldVisibility,
    isLegacyProviderSource,
} from '../lib/epg_sources_helpers.js';
import { installEpgSyncProgressOnWindow } from '../lib/install_epg_sync_progress.js';
import {
    getRuleFormFieldVisibility,
    normalizeNameMappingKey,
    parseCountryCodes,
    ruleNeedsPattern,
    sortByPriority,
    validateNameMappingPreviewInput,
    validateRulePreviewInput,
} from '../lib/match_rules_helpers.js';

installEpgSyncProgressOnWindow();

Object.assign(window, {
    debounce,
    escapeJsSingleQuoted,
    escapeHtml,
    parseUTCDateTime,
    formatLocalTime,
    formatLocalDate,
    formatLocalDateTime,
    formatProgramTimeRange,
    formatRelativeTime,
    AccountSelect: {
        fetchAccounts,
        populateAccountSelect,
        populateAccountSelects,
    },
    getSourceTypeFieldVisibility,
    isLegacyProviderSource,
    getRuleFormFieldVisibility,
    normalizeNameMappingKey,
    parseCountryCodes,
    ruleNeedsPattern,
    sortByPriority,
    validateNameMappingPreviewInput,
    validateRulePreviewInput,
});
