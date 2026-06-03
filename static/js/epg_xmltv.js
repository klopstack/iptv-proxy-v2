// ============================================================================
// XMLTV Grabbers
// ============================================================================

let xmltvGrabbers = [];

async function loadXmltvGrabbers() {
    const container = document.getElementById('xmltv-grabbers-list');
    
    try {
        const response = await fetch('/api/xmltv/grabbers');
        xmltvGrabbers = await response.json();
        
        if (xmltvGrabbers.length === 0) {
            container.innerHTML = `
                <div class="alert alert-warning">
                    <i class="bi bi-exclamation-triangle"></i> No XMLTV grabbers found.
                    <p class="small mb-0 mt-2">Make sure the XMLTV utilities are installed in the Docker container.</p>
                </div>
            `;
            return;
        }
        
        let html = '<div class="table-responsive"><table class="table table-striped table-sm">';
        html += '<thead><tr><th>Grabber</th><th>Description</th><th>Capabilities</th><th>Actions</th></tr></thead><tbody>';
        
        for (const grabber of xmltvGrabbers) {
            const caps = (grabber.capabilities || []).slice(0, 3).join(', ');
            const grabberNameJs = escapeJsSingleQuoted(grabber.name);
            html += `
                <tr>
                    <td><code>${escapeHtml(grabber.name)}</code></td>
                    <td>${escapeHtml(grabber.description || '-')}</td>
                    <td><small class="text-muted">${escapeHtml(caps)}</small></td>
                    <td>
                        <div class="btn-group btn-group-sm">
                            <button class="btn btn-outline-info" onclick="viewGrabberChannels('${grabberNameJs}')" title="List Channels">
                                <i class="bi bi-list"></i>
                            </button>
                            <button class="btn btn-outline-primary" onclick="quickCreateGrabberSource('${grabberNameJs}')" title="Create Source">
                                <i class="bi bi-plus"></i>
                            </button>
                        </div>
                    </td>
                </tr>
            `;
        }
        
        html += '</tbody></table></div>';
        container.innerHTML = html;
        
    } catch (error) {
        container.innerHTML = `<div class="alert alert-danger">Error loading grabbers: ${escapeHtml(error.message)}</div>`;
    }
}

async function populateGrabberSelect() {
    const select = document.getElementById('grabberSelect');
    
    if (xmltvGrabbers.length === 0) {
        try {
            const response = await fetch('/api/xmltv/grabbers');
            xmltvGrabbers = await response.json();
        } catch (error) {
            console.error('Error loading grabbers:', error);
            return;
        }
    }
    
    select.innerHTML = '<option value="">Select a grabber...</option>';
    for (const grabber of xmltvGrabbers) {
        const option = document.createElement('option');
        option.value = grabber.name;
        option.textContent = `${grabber.name} - ${grabber.description || 'No description'}`;
        select.appendChild(option);
    }
}

async function loadXmltvConfigs() {
    const container = document.getElementById('xmltv-configs-list');
    
    try {
        const response = await fetch('/api/xmltv/configs');
        const data = await response.json();
        const configs = data.configs || [];
        
        if (configs.length === 0) {
            container.innerHTML = '<div class="text-center text-muted py-3">No saved configurations</div>';
            return;
        }
        
        let html = '<div class="list-group">';
        for (const config of configs) {
            html += `
                <div class="list-group-item d-flex justify-content-between align-items-center">
                    <div>
                        <strong>${escapeHtml(config.name)}</strong>
                        <br><small class="text-muted">Modified: ${formatLocalDateTime(config.modified)}</small>
                    </div>
                    <button class="btn btn-outline-danger btn-sm" onclick="deleteXmltvConfig('${escapeJsSingleQuoted(config.name)}')">
                        <i class="bi bi-trash"></i>
                    </button>
                </div>
            `;
        }
        html += '</div>';
        container.innerHTML = html;
        
    } catch (error) {
        container.innerHTML = `<div class="alert alert-danger">Error: ${escapeHtml(error.message)}</div>`;
    }
}

async function deleteXmltvConfig(configName) {
    if (!confirm(`Delete configuration "${configName}"?`)) return;
    
    try {
        const response = await fetch(`/api/xmltv/configs/${configName}`, { method: 'DELETE' });
        if (response.ok) {
            loadXmltvConfigs();
            alert('✓ Configuration deleted');
        } else {
            const error = await response.json();
            alert('Error: ' + (error.error || 'Failed to delete'));
        }
    } catch (error) {
        alert('Error: ' + error.message);
    }
}

async function testGrabber() {
    const grabberName = document.getElementById('grabberSelect').value;
    const configName = document.getElementById('grabberConfigName').value;
    const resultDiv = document.getElementById('grabberTestResult');
    
    if (!grabberName) {
        alert('Please select a grabber first');
        return;
    }
    
    const btn = document.getElementById('testGrabberBtn');
    const originalHtml = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Testing...';
    resultDiv.style.display = 'block';
    resultDiv.innerHTML = '<div class="alert alert-info">Testing grabber, please wait...</div>';
    
    try {
        const response = await fetch(`/api/xmltv/grabbers/${grabberName}/test`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ config_name: configName || null })
        });
        const result = await response.json();
        
        if (result.success) {
            resultDiv.innerHTML = `
                <div class="alert alert-success">
                    <i class="bi bi-check-circle"></i> Test passed!
                    <br>Channels: ${result.channels}, Programs: ${result.programs}
                </div>
            `;
        } else {
            resultDiv.innerHTML = `
                <div class="alert alert-danger">
                    <i class="bi bi-x-circle"></i> Test failed: ${escapeHtml(result.message)}
                </div>
            `;
        }
    } catch (error) {
        resultDiv.innerHTML = `<div class="alert alert-danger">Error: ${escapeHtml(error.message)}</div>`;
    } finally {
        btn.disabled = false;
        btn.innerHTML = originalHtml;
    }
}

async function viewGrabberChannels(grabberName) {
    alert(`Loading channels from ${grabberName}... This may take a moment.`);
    
    try {
        const response = await fetch(`/api/xmltv/grabbers/${grabberName}/channels`);
        const data = await response.json();
        
        if (data.error) {
            alert('Error: ' + data.error);
            return;
        }
        
        const channels = data.channels || [];
        let msg = `Found ${channels.length} channels:\n\n`;
        msg += channels.slice(0, 20).map(c => `${c.id}: ${c.name}`).join('\n');
        if (channels.length > 20) {
            msg += `\n... and ${channels.length - 20} more`;
        }
        alert(msg);
    } catch (error) {
        alert('Error: ' + error.message);
    }
}

function quickCreateGrabberSource(grabberName) {
    document.getElementById('sourceId').value = '';
    document.getElementById('sourceForm').reset();
    document.getElementById('sourceType').value = 'xmltv_grabber';
    document.getElementById('sourceName').value = `XMLTV - ${grabberName}`;
    onSourceTypeChange();
    
    setTimeout(() => {
        document.getElementById('grabberSelect').value = grabberName;
    }, 100);
    
    document.getElementById('sourceModalLabel').textContent = 'Add EPG Source';
    if (sourceModal) sourceModal.show();
}
