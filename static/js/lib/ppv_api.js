/**
 * PPV enrichment API paths and fetch helpers.
 *
 * - /api/ppv-enrichment/config — editable settings (API key, enabled)
 * - /api/ppv-enrichment/settings — read-only rate-limit / batch info
 */

export const PPV_ENRICHMENT_CONFIG_URL = '/api/ppv-enrichment/config';
export const PPV_ENRICHMENT_SETTINGS_URL = '/api/ppv-enrichment/settings';

/**
 * @returns {Promise<{ enabled: boolean, has_api_key: boolean, api_key_preview: string|null }>}
 */
export async function fetchPpvEnrichmentConfig() {
    const response = await fetch(PPV_ENRICHMENT_CONFIG_URL);
    if (!response.ok) {
        throw new Error('Failed to load PPV enrichment config');
    }
    return response.json();
}

/**
 * @param {{ enabled?: boolean, apiKey?: string|null }} options
 * Pass apiKey only when setting or clearing the key (empty string clears).
 * @returns {Promise<{ message: string }>}
 */
export async function savePpvEnrichmentConfig({ enabled, apiKey } = {}) {
    const body = {};
    if (enabled !== undefined) {
        body.enabled = enabled;
    }
    if (apiKey !== undefined) {
        body.api_key = apiKey;
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
