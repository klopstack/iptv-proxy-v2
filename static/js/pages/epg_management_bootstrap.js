/**
 * EPG management page: expose lib helpers to legacy classic script bundles.
 */
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
import {
    getRuleFormFieldVisibility,
    normalizeNameMappingKey,
    parseCountryCodes,
    ruleNeedsPattern,
    sortByPriority,
    validateNameMappingPreviewInput,
    validateRulePreviewInput,
} from '../lib/match_rules_helpers.js';
import { installEpgSyncProgressOnWindow } from '../lib/install_epg_sync_progress.js';

installEpgSyncProgressOnWindow();

Object.assign(window, {
    parseUTCDateTime,
    formatLocalTime,
    formatLocalDate,
    formatLocalDateTime,
    formatProgramTimeRange,
    formatRelativeTime,
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
