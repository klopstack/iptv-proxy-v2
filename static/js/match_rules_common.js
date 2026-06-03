// ============================================================================
// Match Rules Common Utilities
// ============================================================================
// Note: accounts and matchTypes are declared globally in epg_common.js

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

async function loadAccounts() {
    try {
        const response = await fetch('/api/accounts');
        accounts = apiUnwrapData(response, await response.json());
    } catch (error) {
        console.error('Error loading accounts:', error);
    }
}

async function loadMatchTypes() {
    try {
        const response = await fetch('/api/epg-match-rules/match-types');
        const data = await response.json();
        matchTypes = data;
    } catch (error) {
        console.error('Error loading match types:', error);
    }
}

function populateExclusionAccountDropdown() {
    const select = document.getElementById('exclusion-account-filter');
    select.innerHTML = '<option value="">All accounts</option>';
    accounts.forEach(account => {
        select.innerHTML += `<option value="${account.id}">${escapeHtml(account.name)}</option>`;
    });
}

function populateRuleAccountDropdown() {
    const select = document.getElementById('rule-account-filter');
    select.innerHTML = '<option value="">All accounts</option>';
    accounts.forEach(account => {
        select.innerHTML += `<option value="${account.id}">${escapeHtml(account.name)}</option>`;
    });
}

function resetExclusionPreview() {
    document.getElementById('exclusion-preview-results').style.display = 'none';
    document.getElementById('exclusion-preview-error').style.display = 'none';
    document.getElementById('exclusion-preview-loading').style.display = 'none';
    document.getElementById('exclusion-preview-list').innerHTML = '';
    document.getElementById('exclusion-preview-count').textContent = '0';
    document.getElementById('exclusion-preview-more').style.display = 'none';
}

function resetRulePreview() {
    document.getElementById('rule-preview-results').style.display = 'none';
    document.getElementById('rule-preview-error').style.display = 'none';
    document.getElementById('rule-preview-loading').style.display = 'none';
    document.getElementById('rule-preview-list').innerHTML = '';
    document.getElementById('rule-preview-count').textContent = '0';
    document.getElementById('rule-preview-more').style.display = 'none';
}
