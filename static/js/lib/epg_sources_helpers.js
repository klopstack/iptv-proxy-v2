/**
 * Pure helpers for EPG source management UI.
 */

/**
 * Field visibility map for the add/edit source modal.
 * @param {string} sourceType
 * @returns {{
 *   xmltvUrlFields: boolean,
 *   sdFields: boolean,
 *   grabberFields: boolean,
 *   ppvFields: boolean,
 * }}
 */
export function getSourceTypeFieldVisibility(sourceType) {
    return {
        xmltvUrlFields: sourceType === 'xmltv_url',
        sdFields: sourceType === 'schedules_direct',
        grabberFields: sourceType === 'xmltv_grabber',
        ppvFields: sourceType === 'ppv_events',
    };
}

/**
 * Existing DB rows may still use the removed provider source type.
 * @param {{ source_type?: string }} source
 * @returns {boolean}
 */
export function isLegacyProviderSource(source) {
    return source?.source_type === 'provider';
}

/**
 * @param {{ source_type?: string, account_id?: number, account_name?: string, url?: string, xmltv_grabber?: string }} source
 * @returns {string}
 */
export function buildSourceInfoLabel(source) {
    if (source.source_type === 'provider') {
        return source.account_name || `Account ${source.account_id}`;
    }
    if (source.source_type === 'xmltv_url') {
        const url = source.url || 'No URL';
        return url.length > 40 ? `${url.substring(0, 40)}...` : url;
    }
    if (source.source_type === 'schedules_direct') {
        return 'SD';
    }
    if (source.source_type === 'xmltv_grabber') {
        return source.xmltv_grabber || 'Grabber';
    }

    return '-';
}
