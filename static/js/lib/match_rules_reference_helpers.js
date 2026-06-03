/**
 * Pure helpers for match rules reference documentation UI.
 */

/**
 * @param {{ match_types: Array<{ value: string, description: string }>, actions: Array<{ value: string, description: string }>, sources: Array<{ value: string, description: string }>, exclusion_types: Array<{ value: string, description: string }> }} data
 * @returns {string}
 */
export function buildMatchRulesReferenceHtml(data) {
    let html = '<div class="row">';

    html += '<div class="col-md-4 mb-4">';
    html += '<div class="card h-100"><div class="card-header"><h5 class="mb-0">Match Types</h5></div>';
    html += '<div class="card-body"><dl>';
    data.match_types.forEach((t) => {
        html += `<dt><code>${t.value}</code></dt><dd class="mb-3">${t.description}</dd>`;
    });
    html += '</dl></div></div></div>';

    html += '<div class="col-md-4 mb-4">';
    html += '<div class="card h-100"><div class="card-header"><h5 class="mb-0">Actions</h5></div>';
    html += '<div class="card-body"><dl>';
    data.actions.forEach((a) => {
        html += `<dt><code>${a.value}</code></dt><dd class="mb-3">${a.description}</dd>`;
    });
    html += '</dl></div></div></div>';

    html += '<div class="col-md-4 mb-4">';
    html += '<div class="card h-100"><div class="card-header"><h5 class="mb-0">Source Fields</h5></div>';
    html += '<div class="card-body"><dl>';
    data.sources.forEach((s) => {
        html += `<dt><code>${s.value}</code></dt><dd class="mb-3">${s.description}</dd>`;
    });
    html += '</dl></div></div></div>';

    html += '</div>';

    html += '<div class="row"><div class="col-12">';
    html += '<div class="card"><div class="card-header"><h5 class="mb-0">Exclusion Pattern Types</h5></div>';
    html += '<div class="card-body"><dl class="row">';
    data.exclusion_types.forEach((e) => {
        html += `<dt class="col-sm-3"><code>${e.value}</code></dt><dd class="col-sm-9">${e.description}</dd>`;
    });
    html += '</dl></div></div></div></div>';

    return html;
}
