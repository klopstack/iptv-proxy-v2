/**
 * PPV enrichment API paths and fetch helpers.
 *
 * - /api/ppv-enrichment/config — editable settings (API key, enabled)
 * - /api/ppv-enrichment/settings — read-only rate-limit / batch info
 * - /api/ppv-enrichment/channels — PPV channel enrichment preview
 * - /api/ppv-epg/events — matched PPV events preview
 */

export const PPV_ENRICHMENT_CONFIG_URL = '/api/ppv-enrichment/config';
export const PPV_ENRICHMENT_SETTINGS_URL = '/api/ppv-enrichment/settings';
export const PPV_ENRICHMENT_CHANNELS_URL = '/api/ppv-enrichment/channels';
export const PPV_EPG_EVENTS_URL = '/api/ppv-epg/events';

/**
 * @param {Record<string, string|number|undefined|null>} [params]
 * @returns {string}
 */
export function buildPpvQueryString(params = {}) {
    const searchParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined && value !== null && value !== '') {
            searchParams.set(key, String(value));
        }
    });
    const query = searchParams.toString();
    return query ? `?${query}` : '';
}

/**
 * @returns {Promise<{ enabled: boolean, has_api_key: boolean, api_key_preview: string|null }>}
 */
export async function fetchPpvEnrichmentConfig() {
    const response = await fetch(PPV_ENRICHMENT_CONFIG_URL);
    if (!response.ok) {
        throw new Error('Failed to load PPV enrichment config');
    }
    const json = await response.json();
    return json.data ?? json;
}

/**
 * @param {{
 *   enabled?: boolean,
 *   apiKey?: string|null,
 *   siteUsername?: string,
 *   sitePassword?: string,
 *   sofascoreCalendarEnabled?: boolean,
 * }} options
 * Pass apiKey only when setting or clearing the key (empty string clears).
 * @returns {Promise<{ message: string }>}
 */
export async function savePpvEnrichmentConfig({
    enabled,
    apiKey,
    siteUsername,
    sitePassword,
    sofascoreCalendarEnabled,
} = {}) {
    const body = {};
    if (enabled !== undefined) {
        body.enabled = enabled;
    }
    if (apiKey !== undefined) {
        body.api_key = apiKey;
    }
    if (siteUsername !== undefined) {
        body.site_username = siteUsername;
    }
    if (sitePassword !== undefined) {
        body.site_password = sitePassword;
    }
    if (sofascoreCalendarEnabled !== undefined) {
        body.sofascore_calendar_enabled = sofascoreCalendarEnabled;
    }

    const response = await fetch(PPV_ENRICHMENT_CONFIG_URL, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });

    if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.error || 'Failed to save PPV enrichment config');
    }

    return response.json();
}

/**
 * @returns {Promise<object>}
 */
export async function fetchPpvEnrichmentSettings() {
    const response = await fetch(PPV_ENRICHMENT_SETTINGS_URL);
    if (!response.ok) {
        throw new Error('Failed to load PPV enrichment settings');
    }
    return response.json();
}

/**
 * @param {Record<string, string|number|undefined|null>} [params]
 * @returns {Promise<object>}
 */
export async function fetchPpvEvents(params = {}) {
    const response = await fetch(`${PPV_EPG_EVENTS_URL}${buildPpvQueryString(params)}`);
    if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.error || 'Failed to load PPV events');
    }
    return response.json();
}

/**
 * @param {number|string} eventId
 * @returns {Promise<object>}
 */
export async function fetchPpvEventDetail(eventId) {
    const response = await fetch(`${PPV_EPG_EVENTS_URL}/${eventId}`);
    if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.error || 'Failed to load PPV event detail');
    }
    return response.json();
}

/**
 * @param {Record<string, string|number|undefined|null>} [params]
 * @returns {Promise<object>}
 */
export async function fetchPpvEnrichmentChannels(params = {}) {
    const response = await fetch(`${PPV_ENRICHMENT_CHANNELS_URL}${buildPpvQueryString(params)}`);
    if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.error || 'Failed to load PPV enrichment channels');
    }
    return response.json();
}
