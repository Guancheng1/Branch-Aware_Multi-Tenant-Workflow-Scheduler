// Application state
let currentView = 'jobs';
let currentUserId = 'user-001';
let ws = null;
let uploadedFiles = [];

// API base URL
const API_BASE = window.location.origin + '/api/v1';

// Initialize application
document.addEventListener('DOMContentLoaded', () => {
    initializeApp();
});

function initializeApp() {
    // Get user ID
    const userIdInput = document.getElementById('userId');
    currentUserId = userIdInput.value || 'user-001';
    
    userIdInput.addEventListener('change', (e) => {
        currentUserId = e.target.value || 'user-001';
        // Reconnect WebSocket
        connectWebSocket();
        // Refresh current view
        refreshCurrentView();
    });
    
    // Initialize navigation
    initializeNavigation();
    
    // Initialize buttons
    initializeButtons();
    
    // Initialize upload
    initializeUpload();
    
    // Connect WebSocket
    connectWebSocket();
    
    // Load initial data
    refreshCurrentView();
    
    // Refresh statistics periodically
    setInterval(() => {
        if (currentView === 'stats') {
            loadSystemStats();
        }
    }, 5000);
}

// Navigation
function initializeNavigation() {
    const navButtons = document.querySelectorAll('.nav-btn');
    
    navButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            const view = btn.dataset.view;
            switchView(view);
        });
    });
}

function switchView(view) {
    // Update navigation state
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.view === view);
    });
    
    // Hide all views
    document.querySelectorAll('.view-container').forEach(v => {
        v.classList.add('hidden');
    });
    
    // Show target view
    const viewMap = {
        'jobs': 'jobsView',
        'workflows': 'workflowsView',
        'stats': 'statsView',
        'upload': 'uploadView'
    };
    
    const targetView = document.getElementById(viewMap[view]);
    if (targetView) {
        targetView.classList.remove('hidden');
    }
    
    // Update title
    const titles = {
        'jobs': { title: 'Task Management', desc: 'Manage and monitor your image processing tasks' },
        'workflows': { title: 'Workflow Management', desc: 'Create and manage DAG workflows' },
        'stats': { title: 'Statistics', desc: 'System status and performance metrics' },
        'upload': { title: 'Upload Image', desc: 'Upload WSI image files for processing' }
    };
    
    document.getElementById('viewTitle').textContent = titles[view].title;
    document.getElementById('viewDescription').textContent = titles[view].desc;
    
    // Update button visibility
    document.getElementById('createJobBtn').style.display = view === 'jobs' ? 'block' : 'none';
    
    currentView = view;
    
    // Load view data
    refreshCurrentView();
}

function refreshCurrentView() {
    switch (currentView) {
        case 'jobs':
            loadJobs();
            break;
        case 'workflows':
            loadWorkflows();
            break;
        case 'stats':
            loadSystemStats();
            break;
        case 'upload':
            renderUploadedFiles();
            break;
    }
}

// Initialize buttons
function initializeButtons() {
    document.getElementById('createJobBtn').addEventListener('click', () => {
        openModal('createJobModal');
    });
    
    document.getElementById('refreshBtn').addEventListener('click', () => {
        refreshCurrentView();
    });
}

// WebSocket connection
function connectWebSocket() {
    if (ws) {
        ws.close();
    }
    
    const wsUrl = `ws://${window.location.host}/ws/${currentUserId}`;
    ws = new WebSocket(wsUrl);
    
    ws.onopen = () => {
        console.log('WebSocket connected');
        updateConnectionStatus(true);
    };
    
    ws.onclose = () => {
        console.log('WebSocket disconnected');
        updateConnectionStatus(false);
        // Reconnect after 3 seconds
        setTimeout(connectWebSocket, 3000);
    };
    
    ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        updateConnectionStatus(false);
    };
    
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        handleWebSocketMessage(data);
    };
}

function updateConnectionStatus(connected) {
    const statusDot = document.getElementById('wsStatus');
    if (connected) {
        statusDot.classList.add('connected');
    } else {
        statusDot.classList.remove('connected');
    }
}

function handleWebSocketMessage(data) {
    if (data.type === 'job_update') {
        updateJobCard(data);
    } else if (data.type === 'workflow_update') {
        updateWorkflowCard(data);
    }
}

// Task management
async function loadJobs() {
    try {
        const response = await fetch(`${API_BASE}/jobs`, {
            headers: { 'X-User-ID': currentUserId }
        });
        
        const jobs = await response.json();
        renderJobs(jobs);
        
        // Subscribe to all task updates
        jobs.forEach(job => {
            subscribeToJob(job.job_id);
        });
    } catch (error) {
        console.error('Error loading jobs:', error);
        showError('Failed to load tasks');
    }
}

function renderJobs(jobs) {
    const grid = document.getElementById('jobsGrid');
    
    if (jobs.length === 0) {
        grid.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">📋</div>
                <h3>No tasks yet</h3>
                <p>Click "Create Task" button to start</p>
            </div>
        `;
        return;
    }
    
    // Sort by creation time in descending order
    jobs.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
    
    grid.innerHTML = jobs.map(job => createJobCard(job)).join('');
}

function createJobCard(job) {
    const statusClass = job.status.toLowerCase();
    const statusText = {
        'PENDING': 'Pending',
        'RUNNING': 'Running',
        'SUCCEEDED': 'Succeeded',
        'FAILED': 'Failed',
        'CANCELLED': 'Cancelled'
    }[job.status] || job.status;
    
    const typeText = {
        'cell_segmentation': 'Cell Segmentation',
        'tissue_mask': 'Tissue Mask'
    }[job.job_type] || job.job_type;
    
    return `
        <div class="job-card" data-job-id="${job.job_id}" onclick="showJobDetail('${job.job_id}')">
            <div class="job-card-header">
                <div class="job-type">${typeText}</div>
                <span class="job-status ${statusClass}">${statusText}</span>
            </div>
            
            <div class="job-id">ID: ${job.job_id.substring(0, 8)}...</div>
            
            <div class="job-branch">
                <span>🌿</span>
                <span>${job.branch}</span>
            </div>
            
            ${job.status === 'RUNNING' || job.progress_percent > 0 ? `
                <div class="job-progress">
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: ${job.progress_percent}%"></div>
                    </div>
                    <div class="progress-text">
                        <span>${Math.round(job.progress_percent)}%</span>
                        <span>${job.tiles_processed}/${job.tiles_total} tiles</span>
                    </div>
                </div>
            ` : ''}
            
            ${job.current_message ? `
                <div class="job-message">${job.current_message}</div>
            ` : ''}
            
            ${job.error ? `
                <div class="job-message" style="color: var(--error-color);">
                    ❌ ${job.error}
                </div>
            ` : ''}
        </div>
    `;
}

function updateJobCard(jobData) {
    const card = document.querySelector(`[data-job-id="${jobData.job_id}"]`);
    if (!card) return;
    
    // Update progress bar
    const progressFill = card.querySelector('.progress-fill');
    if (progressFill) {
        progressFill.style.width = `${jobData.progress_percent}%`;
    }
    
    // Update progress text
    const progressText = card.querySelector('.progress-text');
    if (progressText) {
        progressText.innerHTML = `
            <span>${Math.round(jobData.progress_percent)}%</span>
            <span>${jobData.tiles_processed}/${jobData.tiles_total} tiles</span>
        `;
    }
    
    // Update status
    const statusBadge = card.querySelector('.job-status');
    if (statusBadge) {
        const statusClass = jobData.status.toLowerCase();
        const statusText = {
            'PENDING': 'Pending',
            'RUNNING': 'Running',
            'SUCCEEDED': 'Succeeded',
            'FAILED': 'Failed'
        }[jobData.status] || jobData.status;
        
        statusBadge.className = `job-status ${statusClass}`;
        statusBadge.textContent = statusText;
    }
    
    // Update message
    const messageDiv = card.querySelector('.job-message');
    if (messageDiv && jobData.current_message) {
        messageDiv.textContent = jobData.current_message;
    }
}

function subscribeToJob(jobId) {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
            action: 'subscribe_job',
            job_id: jobId
        }));
    }
}

async function showJobDetail(jobId) {
    try {
        const response = await fetch(`${API_BASE}/jobs/${jobId}`, {
            headers: { 'X-User-ID': currentUserId }
        });
        
        const job = await response.json();
        renderJobDetail(job);
        openModal('jobDetailModal');
    } catch (error) {
        console.error('Error loading job detail:', error);
        showError('Failed to load task details');
    }
}

function renderJobDetail(job) {
    const content = document.getElementById('jobDetailContent');
    
    const statusClass = job.status.toLowerCase();
    const statusText = {
        'PENDING': 'Pending',
        'RUNNING': 'Running',
        'SUCCEEDED': 'Succeeded',
        'FAILED': 'Failed',
        'CANCELLED': 'Cancelled'
    }[job.status] || job.status;
    
    content.innerHTML = `
        <div style="margin-bottom: 1.5rem;">
            <h4>Basic Information</h4>
            <div style="display: grid; gap: 0.75rem; margin-top: 1rem;">
                <div><strong>Task ID:</strong> ${job.job_id}</div>
                <div><strong>Status:</strong> <span class="job-status ${statusClass}">${statusText}</span></div>
                <div><strong>Type:</strong> ${job.job_type}</div>
                <div><strong>Branch:</strong> ${job.branch}</div>
                <div><strong>Image Path:</strong> <code>${job.image_path}</code></div>
            </div>
        </div>
        
        ${job.progress_percent > 0 ? `
            <div style="margin-bottom: 1.5rem;">
                <h4>Progress</h4>
                <div class="job-progress" style="margin-top: 1rem;">
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: ${job.progress_percent}%"></div>
                    </div>
                    <div class="progress-text">
                        <span>${Math.round(job.progress_percent)}%</span>
                        <span>${job.tiles_processed}/${job.tiles_total} tiles</span>
                    </div>
                </div>
                ${job.current_message ? `<div class="job-message" style="margin-top: 1rem;">${job.current_message}</div>` : ''}
            </div>
        ` : ''}
        
        ${job.result_path ? `
            <div style="margin-bottom: 1.5rem;">
                <h4>Results</h4>
                <div style="margin-top: 1rem;">
                    <button class="btn btn-primary" onclick="viewJobResults('${job.job_id}', '${job.user_id}'); event.stopPropagation();">
                        View Results
                    </button>
                </div>
            </div>
        ` : ''}
        
        ${job.error ? `
            <div style="margin-bottom: 1.5rem;">
                <h4>Error</h4>
                <div class="job-message" style="color: var(--error-color); margin-top: 1rem;">
                    ${job.error}
                </div>
            </div>
        ` : ''}
        
        ${job.status === 'PENDING' ? `
            <div style="margin-top: 1.5rem;">
                <button class="btn btn-danger" onclick="cancelJob('${job.job_id}')">
                    Cancel Task
                </button>
            </div>
        ` : ''}
    `;
}

async function cancelJob(jobId) {
    if (!confirm('Are you sure you want to cancel this task?')) return;
    
    try {
        await fetch(`${API_BASE}/jobs/${jobId}`, {
            method: 'DELETE',
            headers: { 'X-User-ID': currentUserId }
        });
        
        closeModal('jobDetailModal');
        loadJobs();
        showSuccess('Task cancelled');
    } catch (error) {
        console.error('Error cancelling job:', error);
        showError('Failed to cancel task');
    }
}

// Create task
async function submitJob() {
    const jobType = document.getElementById('jobType').value;
    const branch = document.getElementById('jobBranch').value;
    const imagePath = document.getElementById('jobImagePath').value;
    const tileSize = parseInt(document.getElementById('jobTileSize').value);
    const overlap = parseInt(document.getElementById('jobOverlap').value);
    
    if (!branch || !imagePath) {
        showError('Please fill in all required fields');
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/jobs`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-User-ID': currentUserId
            },
            body: JSON.stringify({
                job_type: jobType,
                branch: branch,
                image_path: imagePath,
                parameters: {
                    tile_size: tileSize,
                    overlap: overlap
                }
            })
        });
        
        if (response.ok) {
            closeModal('createJobModal');
            loadJobs();
            showSuccess('Task created successfully');
        } else {
            throw new Error('Failed to create job');
        }
    } catch (error) {
        console.error('Error creating job:', error);
        showError('Failed to create task');
    }
}

// Workflow management
async function loadWorkflows() {
    try {
        const response = await fetch(`${API_BASE}/workflows`, {
            headers: { 'X-User-ID': currentUserId }
        });
        
        const workflows = await response.json();
        renderWorkflows(workflows);
    } catch (error) {
        console.error('Error loading workflows:', error);
        showError('Failed to load workflows');
    }
}

function renderWorkflows(workflows) {
    const grid = document.getElementById('workflowsGrid');
    
    if (workflows.length === 0) {
        grid.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">🔄</div>
                <h3>No workflows yet</h3>
                <p>Workflows can combine multiple tasks into a DAG</p>
            </div>
        `;
        return;
    }
    
    grid.innerHTML = workflows.map(wf => `
        <div class="job-card">
            <div class="job-card-header">
                <div class="job-type">Workflow</div>
                <span class="job-status ${wf.status.toLowerCase()}">${wf.status}</span>
            </div>
            <h3>${wf.name}</h3>
            <p style="color: var(--text-muted); font-size: 0.875rem;">${wf.description || ''}</p>
            <div style="margin-top: 1rem;">
                <strong>${wf.nodes.length}</strong> nodes
                <strong style="margin-left: 1rem;">${wf.job_ids.length}</strong> tasks
            </div>
            <div class="job-progress" style="margin-top: 1rem;">
                <div class="progress-bar">
                    <div class="progress-fill" style="width: ${wf.progress_percent}%"></div>
                </div>
                <div class="progress-text">
                    <span>${Math.round(wf.progress_percent)}%</span>
                </div>
            </div>
        </div>
    `).join('');
}

// Statistics
async function loadSystemStats() {
    try {
        const response = await fetch(`${API_BASE}/stats/system`);
        const stats = await response.json();
        renderSystemStats(stats);
    } catch (error) {
        console.error('Error loading system stats:', error);
    }
}

function renderSystemStats(stats) {
    document.getElementById('statActiveUsers').textContent = stats.active_users;
    document.getElementById('statMaxUsers').textContent = `Max ${stats.max_active_users} users`;
    
    document.getElementById('statActiveWorkers').textContent = stats.active_workers;
    document.getElementById('statMaxWorkers').textContent = `Max ${stats.max_workers} workers`;
    
    document.getElementById('statQueueDepth').textContent = stats.queue_depth;
    
    document.getElementById('statTotalJobs').textContent = stats.total_jobs_processed;
    document.getElementById('statAvgLatency').textContent = 
        `Average latency: ${stats.average_job_latency_seconds.toFixed(2)}s`;
    
    // Render branch queue chart
    renderBranchQueueChart(stats.per_branch_queue_depth);
}

function renderBranchQueueChart(branchData) {
    const chart = document.getElementById('branchQueueChart');
    
    if (Object.keys(branchData).length === 0) {
        chart.innerHTML = '<p style="color: var(--text-muted);">No data</p>';
        return;
    }
    
    const maxDepth = Math.max(...Object.values(branchData));
    
    chart.innerHTML = Object.entries(branchData).map(([branch, depth]) => `
        <div style="margin-bottom: 1rem;">
            <div style="display: flex; justify-content: space-between; margin-bottom: 0.5rem;">
                <span style="font-weight: 500;">${branch}</span>
                <span style="color: var(--text-muted);">${depth}</span>
            </div>
            <div class="progress-bar">
                <div class="progress-fill" style="width: ${(depth / maxDepth) * 100}%"></div>
            </div>
        </div>
    `).join('');
}

// File upload
function initializeUpload() {
    const uploadArea = document.getElementById('uploadArea');
    const fileInput = document.getElementById('fileInput');
    
    // Drag and drop upload
    uploadArea.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadArea.classList.add('drag-over');
    });
    
    uploadArea.addEventListener('dragleave', () => {
        uploadArea.classList.remove('drag-over');
    });
    
    uploadArea.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadArea.classList.remove('drag-over');
        
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            handleFileUpload(files[0]);
        }
    });
    
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            handleFileUpload(e.target.files[0]);
        }
    });
}

async function handleFileUpload(file) {
    const formData = new FormData();
    formData.append('file', file);
    
    try {
        const response = await fetch(`${API_BASE}/upload`, {
            method: 'POST',
            headers: {
                'X-User-ID': currentUserId
            },
            body: formData
        });
        
        const result = await response.json();
        
        uploadedFiles.push(result);
        renderUploadedFiles();
        showSuccess('File uploaded successfully');
        
        // Auto-fill the create task form
        document.getElementById('jobImagePath').value = result.path;
    } catch (error) {
        console.error('Error uploading file:', error);
        showError('File upload failed');
    }
}

function renderUploadedFiles() {
    const list = document.getElementById('uploadList');
    
    if (uploadedFiles.length === 0) {
        list.innerHTML = '';
        return;
    }
    
    list.innerHTML = uploadedFiles.map(file => `
        <div class="upload-item">
            <div class="upload-item-info">
                <div class="upload-item-name">${file.filename}</div>
                <div class="upload-item-size">${formatFileSize(file.size)}</div>
                <div class="upload-item-path">${file.path}</div>
            </div>
            <button class="btn btn-secondary btn-sm" onclick="copyToClipboard('${file.path}')">
                Copy Path
            </button>
        </div>
    `).join('');
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        showSuccess('Path copied');
    });
}

// Modal
function openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.add('active');
    }
}

function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.remove('active');
    }
}

// Notification
function showSuccess(message) {
    // Simple notification implementation
    alert(message);
}

function showError(message) {
    alert('Error: ' + message);
}

// View task results
async function viewJobResults(jobId, userId) {
    try {
        // Build result path
        const resultsBaseUrl = `/results/${userId}/${jobId}`;
        const jsonUrl = `${resultsBaseUrl}/segmentation_results.json`;
        const imageUrl = `${resultsBaseUrl}/visualization.jpg`;
        
        // Check if results file exists
        const jsonResponse = await fetch(jsonUrl);
        if (!jsonResponse.ok) {
            showError('Results file does not exist or is inaccessible');
            return;
        }
        
        const results = await jsonResponse.json();
        
        // Display results modal
        renderResultsView(results, imageUrl, jsonUrl, userId, jobId);
        openModal('resultsModal');
    } catch (error) {
        console.error('Error loading results:', error);
        showError('Failed to load results: ' + error.message);
    }
}

function renderResultsView(results, imageUrl, jsonUrl, userId, jobId) {
    const content = document.getElementById('resultsContent');
    
    content.innerHTML = `
        <div style="margin-bottom: 1.5rem;">
            <h4>Segmentation Statistics</h4>
            <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 1rem; margin-top: 1rem;">
                <div class="stat-card">
                    <div class="stat-label">Image Size</div>
                    <div class="stat-value">${results.image_width} × ${results.image_height}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Detected Cells</div>
                    <div class="stat-value">${results.total_cells}</div>
                </div>
            </div>
        </div>
        
        <div style="margin-bottom: 1.5rem;">
            <h4>Visualization Result</h4>
            <div style="margin-top: 1rem; text-align: center; background: #f5f5f5; padding: 1rem; border-radius: 8px;">
                <img src="${imageUrl}" 
                     alt="Segmentation Result" 
                     style="max-width: 100%; height: auto; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);"
                     onerror="this.parentElement.innerHTML='<p style=color:var(--text-muted)>Failed to load image or does not exist</p>'">
            </div>
        </div>
        
        <div style="margin-bottom: 1.5rem;">
            <h4>Cell Details (First 10)</h4>
            <div style="max-height: 300px; overflow-y: auto; margin-top: 1rem; border: 1px solid var(--border-color); border-radius: 8px;">
                <table style="width: 100%; border-collapse: collapse;">
                    <thead style="position: sticky; top: 0; background: var(--bg-primary); z-index: 1;">
                        <tr style="border-bottom: 2px solid var(--border-color);">
                            <th style="padding: 0.75rem; text-align: left;">ID</th>
                            <th style="padding: 0.75rem; text-align: left;">Label</th>
                            <th style="padding: 0.75rem; text-align: right;">Area</th>
                            <th style="padding: 0.75rem; text-align: right;">Centroid</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${results.cells.slice(0, 10).map(cell => `
                            <tr style="border-bottom: 1px solid var(--border-color);">
                                <td style="padding: 0.75rem;">${cell.id}</td>
                                <td style="padding: 0.75rem;">${cell.label}</td>
                                <td style="padding: 0.75rem; text-align: right;">${Math.round(cell.area)}</td>
                                <td style="padding: 0.75rem; text-align: right; font-family: monospace; font-size: 0.875rem;">
                                    (${Math.round(cell.centroid[0])}, ${Math.round(cell.centroid[1])})
                                </td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
            ${results.cells.length > 10 ? `<p style="margin-top: 0.5rem; color: var(--text-muted); font-size: 0.875rem;">Showing first 10 of ${results.cells.length} cells</p>` : ''}
        </div>
        
        <div style="margin-top: 1.5rem; display: flex; gap: 0.5rem;">
            <a href="${imageUrl}" download="visualization.jpg" class="btn btn-secondary">
                📥 Download Image
            </a>
            <a href="${jsonUrl}" download="segmentation_results.json" class="btn btn-secondary">
                📥 Download JSON
            </a>
        </div>
    `;
}


