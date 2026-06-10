/**
 * Xtream credentials admin page (ESM).
 * Exposes edit/delete handlers on window for inline table buttons.
 */
import { fetchAccounts, populateAccountSelect } from '../lib/account_select.js';
import { escapeHtml } from '../lib/escape_html.js';

/** IANA zones offered in the credential PPV rename timezone select. */
export const PPV_RENAME_TIMEZONE_OPTIONS = [
    'America/New_York',
    'America/Chicago',
    'America/Denver',
    'America/Los_Angeles',
    'America/Phoenix',
    'Europe/London',
    'Europe/Paris',
    'Europe/Berlin',
    'Australia/Sydney',
    'UTC',
];

let deleteCredentialId = null;

const ACCOUNT_PLACEHOLDER = '-- Select Account --';
const PLAYLIST_PLACEHOLDER = '-- Select Playlist Config --';

function getAccountSelect() {
    return document.getElementById('credential-account-id');
}

function setSelectError(select, message) {
    if (!select) {
        return;
    }
    select.innerHTML = `<option value="">${escapeHtml(message)}</option>`;
}

async function loadAccounts() {
    const select = getAccountSelect();
    try {
        const loadedAccounts = await fetchAccounts();
        populateAccountSelect(select, loadedAccounts, { placeholder: ACCOUNT_PLACEHOLDER });
    } catch (error) {
        console.error('Error loading accounts:', error);
        setSelectError(select, `Error loading accounts: ${error.message}`);
    }
}

async function loadPlaylistConfigs() {
    const select = document.getElementById('credential-playlist-config-id');
    try {
        const response = await fetch('/api/playlist-configs');
        const configs = await response.json();

        if (!response.ok || !Array.isArray(configs)) {
            const message = (configs && typeof configs === 'object' && configs.error) || 'Invalid playlist configs response';
            throw new Error(message);
        }

        select.innerHTML = `<option value="">${escapeHtml(PLAYLIST_PLACEHOLDER)}</option>` +
            configs.map((config) => `<option value="${config.id}">${escapeHtml(config.name)}</option>`).join('');
    } catch (error) {
        console.error('Error loading playlist configs:', error);
        setSelectError(select, `Error loading playlist configs: ${error.message}`);
    }
}

function loadCredentials() {
    fetch('/api/xtream-credentials')
        .then((response) => response.json())
        .then((credentials) => {
            displayCredentials(credentials);
            document.getElementById('loading-spinner').style.display = 'none';
            document.getElementById('credentials-container').style.display = 'block';
        })
        .catch((error) => {
            console.error('Error loading credentials:', error);
            showError('Failed to load credentials');
        });
}

function displayCredentials(credentials) {
    const tbody = document.getElementById('credentials-list');
    const noCredsDiv = document.getElementById('no-credentials');

    if (credentials.length === 0) {
        tbody.innerHTML = '';
        noCredsDiv.style.display = 'block';
        return;
    }

    noCredsDiv.style.display = 'none';
    tbody.innerHTML = credentials.map((cred) => {
        const source = cred.account_id
            ? `Account #${cred.account_id}`
            : `Playlist Config #${cred.playlist_config_id}`;

        const statusBadge = cred.enabled
            ? '<span class="badge bg-success">Enabled</span>'
            : '<span class="badge bg-secondary">Disabled</span>';

        const filtersBadge = cred.use_filters
            ? '<span class="badge bg-info">Yes</span>'
            : '<span class="badge bg-secondary">No</span>';

        const collapseBadge = cred.collapse_duplicates
            ? '<span class="badge bg-warning">Yes</span>'
            : '<span class="badge bg-secondary">No</span>';

        return `
            <tr>
                <td><code>${escapeHtml(cred.username)}</code></td>
                <td>${source}</td>
                <td>${filtersBadge}</td>
                <td>${collapseBadge}</td>
                <td>${statusBadge}</td>
                <td>${escapeHtml(cred.description || '')}</td>
                <td>
                    <button class="btn btn-sm btn-outline-primary" onclick="editCredential(${cred.id})">
                        <i class="bi bi-pencil"></i> Edit
                    </button>
                    <button class="btn btn-sm btn-outline-danger" onclick="deleteCredential(${cred.id}, '${escapeHtml(cred.username)}')">
                        <i class="bi bi-trash"></i> Delete
                    </button>
                </td>
            </tr>
        `;
    }).join('');
}

function saveCredential() {
    const id = document.getElementById('credential-id').value;
    const username = document.getElementById('credential-username').value.trim();
    const password = document.getElementById('credential-password').value.trim();
    const sourceType = document.querySelector('input[name="source-type"]:checked').value;
    const accountId = sourceType === 'account' ? document.getElementById('credential-account-id').value : null;
    const playlistConfigId = sourceType === 'playlist' ? document.getElementById('credential-playlist-config-id').value : null;
    const useFilters = document.getElementById('credential-use-filters').checked;
    const collapseDuplicates = document.getElementById('credential-collapse-duplicates').checked;
    const enabled = document.getElementById('credential-enabled').checked;
    const description = document.getElementById('credential-description').value.trim();
    const ppvRenameTimezone = document.getElementById('credential-ppv-rename-timezone').value.trim();
    const preferredLanguages = document.getElementById('credential-preferred-languages').value.trim();
    const languageFallback = document.getElementById('credential-language-fallback').value;

    if (!username) {
        showFormError('Username is required');
        return;
    }

    if (!id && !password) {
        showFormError('Password is required for new credentials');
        return;
    }

    if (!accountId && !playlistConfigId) {
        showFormError('Please select an account or playlist config');
        return;
    }

    const data = {
        username,
        account_id: accountId ? parseInt(accountId, 10) : null,
        playlist_config_id: playlistConfigId ? parseInt(playlistConfigId, 10) : null,
        use_filters: useFilters,
        collapse_duplicates: collapseDuplicates,
        enabled,
        description,
        ppv_rename_timezone: ppvRenameTimezone || null,
        preferred_languages: preferredLanguages || 'en',
        language_fallback: languageFallback,
    };

    if (password) {
        data.password = password;
    }

    const method = id ? 'PUT' : 'POST';
    const url = id ? `/api/xtream-credentials/${id}` : '/api/xtream-credentials';

    fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
    })
        .then((response) => {
            if (!response.ok) {
                return response.json().then((err) => Promise.reject(err));
            }
            return response.json();
        })
        .then(() => {
            bootstrap.Modal.getInstance(document.getElementById('addCredentialModal')).hide();
            loadCredentials();
            showSuccess(id ? 'Credential updated successfully' : 'Credential created successfully');
        })
        .catch((error) => {
            showFormError(error.error || 'Failed to save credential');
        });
}

function editCredential(id) {
    fetch('/api/xtream-credentials')
        .then((response) => response.json())
        .then((credentials) => {
            const cred = credentials.find((c) => c.id === id);
            if (!cred) {
                return;
            }

            document.getElementById('credential-id').value = cred.id;
            document.getElementById('credential-username').value = cred.username;
            document.getElementById('credential-password').value = '';
            document.getElementById('credential-password').required = false;
            document.getElementById('password-required-indicator').style.display = 'none';
            document.getElementById('password-help-text').textContent = 'Leave blank to keep existing password';
            document.getElementById('credential-use-filters').checked = cred.use_filters;
            document.getElementById('credential-collapse-duplicates').checked = cred.collapse_duplicates;
            document.getElementById('credential-enabled').checked = cred.enabled;
            document.getElementById('credential-description').value = cred.description || '';
            document.getElementById('credential-ppv-rename-timezone').value = cred.ppv_rename_timezone || '';
            const langs = Array.isArray(cred.preferred_languages)
                ? cred.preferred_languages.join(', ')
                : (cred.preferred_languages || 'en');
            document.getElementById('credential-preferred-languages').value = langs;
            document.getElementById('credential-language-fallback').value = cred.language_fallback || 'unknown';

            if (cred.account_id) {
                document.getElementById('source-account').checked = true;
                document.getElementById('account-select-group').style.display = 'block';
                document.getElementById('playlist-select-group').style.display = 'none';
                document.getElementById('credential-account-id').value = cred.account_id;
            } else {
                document.getElementById('source-playlist').checked = true;
                document.getElementById('account-select-group').style.display = 'none';
                document.getElementById('playlist-select-group').style.display = 'block';
                document.getElementById('credential-playlist-config-id').value = cred.playlist_config_id;
            }

            document.getElementById('modalTitle').textContent = 'Edit Xtream Credential';
            new bootstrap.Modal(document.getElementById('addCredentialModal')).show();
        });
}

function deleteCredential(id, username) {
    deleteCredentialId = id;
    document.getElementById('delete-username').textContent = username;
    new bootstrap.Modal(document.getElementById('deleteModal')).show();
}

function confirmDelete() {
    fetch(`/api/xtream-credentials/${deleteCredentialId}`, { method: 'DELETE' })
        .then(() => {
            bootstrap.Modal.getInstance(document.getElementById('deleteModal')).hide();
            loadCredentials();
            showSuccess('Credential deleted successfully');
        })
        .catch((error) => {
            console.error('Error deleting credential:', error);
            showError('Failed to delete credential');
        });
}

function showFormError(message) {
    const errorDiv = document.getElementById('form-error');
    errorDiv.textContent = message;
    errorDiv.style.display = 'block';
}

function showSuccess(message) {
    alert(message);
}

function showError(message) {
    alert(`Error: ${message}`);
}

function initXtreamPage() {
    if (!document.getElementById('credential-form')) {
        return;
    }

    const serverUrl = window.location.origin;
    document.getElementById('server-url').textContent = serverUrl;
    document.getElementById('server-url-instructions').textContent = serverUrl;

    loadCredentials();
    loadAccounts();
    loadPlaylistConfigs();

    document.getElementById('save-credential-btn').addEventListener('click', saveCredential);
    document.getElementById('confirm-delete-btn').addEventListener('click', confirmDelete);

    document.querySelectorAll('input[name="source-type"]').forEach((radio) => {
        radio.addEventListener('change', function onSourceTypeChange() {
            const isAccount = this.value === 'account';
            document.getElementById('account-select-group').style.display = isAccount ? 'block' : 'none';
            document.getElementById('playlist-select-group').style.display = isAccount ? 'none' : 'block';
        });
    });

    const credentialModal = document.getElementById('addCredentialModal');
    credentialModal.addEventListener('shown.bs.modal', () => {
        loadAccounts();
    });

    credentialModal.addEventListener('hidden.bs.modal', () => {
        document.getElementById('credential-form').reset();
        document.getElementById('credential-id').value = '';
        document.getElementById('form-error').style.display = 'none';
        document.getElementById('modalTitle').textContent = 'Add Xtream Credential';
        document.getElementById('credential-password').required = true;
        document.getElementById('password-required-indicator').style.display = '';
        document.getElementById('password-help-text').textContent = 'Use a unique password different from your provider';
        document.getElementById('credential-ppv-rename-timezone').value = '';
    });
}

const xtreamPageExports = {
    editCredential,
    deleteCredential,
};

Object.assign(window, xtreamPageExports);

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initXtreamPage);
} else {
    initXtreamPage();
}

export { xtreamPageExports };
