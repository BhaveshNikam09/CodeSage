
// Global variables
let currentResults = null;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    setupEventListeners();
    updateEditorStats();
});

function setupEventListeners() {
    // File upload
    document.getElementById('fileInput').addEventListener('change', handleFileUpload);
    
    // Code input stats
    document.getElementById('codeInput').addEventListener('input', updateEditorStats);
}

function updateEditorStats() {
    const code = document.getElementById('codeInput').value;
    const lines = code.split('\n').length;
    const chars = code.length;
    
    document.getElementById('lineCount').textContent = `${lines} lines`;
    document.getElementById('charCount').textContent = `${chars} characters`;
}

function loadSample() {
    const sample = `import os

DATABASE_PASSWORD = "admin123"

def divide_numbers(a, b):
    return a / b

def run_command(cmd):
    os.system(f"echo {cmd}")

def process_items(items):
    for i in range(len(items)):
        print(items[i])

def risky_eval(user_input):
    return eval(user_input)

def load_file(path):
    f = open(path, 'r')
    data = f.read()
    return data`;
    
    document.getElementById('codeInput').value = sample;
    updateEditorStats();
}

async function handleFileUpload(event) {
    const file = event.target.files[0];
    if (!file) return;
    
    const formData = new FormData();
    formData.append('file', file);
    
    try {
        const response = await fetch('/upload', {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        
        if (data.code) {
            document.getElementById('codeInput').value = data.code;
            updateEditorStats();
        } else {
            alert(data.error || 'Failed to upload file');
        }
    } catch (error) {
        alert('Upload failed: ' + error.message);
    }
}

async function analyzeCode() {
    const code = document.getElementById('codeInput').value.trim();
    
    if (!code) {
        alert('Please enter some code to analyze!');
        return;
    }
    
    // Show loading
    document.getElementById('loadingOverlay').style.display = 'flex';
    
    try {
        const response = await fetch('/api/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code })
        });
        
        const result = await response.json();
        
        if (result.success) {
            currentResults = result.data;
            displayResults(result.data);
        } else {
            alert('Analysis failed: ' + result.message);
        }
    } catch (error) {
        alert('Error: ' + error.message);
    } finally {
        document.getElementById('loadingOverlay').style.display = 'none';
    }
}

function displayResults(data) {
    const container = document.getElementById('results');
    const stats = data.statistics;
    const summary = data.summary;
    const issues = data.issues;
    
    let html = `
        <div class="score-card">
            <div style="font-size: 1rem; opacity: 0.9;">Code Quality Score</div>
            <div class="score-value">${summary.score}</div>
            <div style="font-size: 1.125rem; margin-top: 0.5rem;">${getStatusText(summary.status)}</div>
        </div>
        
        <div class="stats-grid">
            <div class="stat-card critical">
                <div class="stat-value">${stats.critical}</div>
                <div class="stat-label">Critical</div>
            </div>
            <div class="stat-card high">
                <div class="stat-value">${stats.high}</div>
                <div class="stat-label">High</div>
            </div>
            <div class="stat-card medium">
                <div class="stat-value">${stats.medium}</div>
                <div class="stat-label">Medium</div>
            </div>
            <div class="stat-card low">
                <div class="stat-value">${stats.low}</div>
                <div class="stat-label">Low</div>
            </div>
        </div>
    `;
    
    if (issues.length > 0) {
        html += '<div class="issues-section"><h3 class="section-title">🐛 Issues Found</h3>';
        
        // Sort by severity
        const sorted = issues.sort((a, b) => {
            const order = { critical: 0, high: 1, medium: 2, low: 3 };
            return order[a.severity] - order[b.severity];
        });
        
        sorted.forEach(issue => {
            html += `
                <div class="issue-card ${issue.severity}">
                    <div class="issue-header">
                        <div class="issue-title">Line ${issue.line}: ${issue.message}</div>
                        <span class="issue-badge ${issue.severity}">${issue.severity.toUpperCase()}</span>
                    </div>
                    ${issue.code_snippet ? `<div class="issue-code">${escapeHtml(issue.code_snippet)}</div>` : ''}
                    <div class="issue-fix">
                        <span>💡</span>
                        <span>${issue.fix}</span>
                    </div>
                </div>
            `;
        });
        
        html += '</div>';
    } else {
        html += `
            <div class="empty-state">
                <svg width="64" height="64" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
                </svg>
                <h3>Perfect Code!</h3>
                <p>No issues detected. Great work!</p>
            </div>
        `;
    }
    
    container.innerHTML = html;
    document.querySelector('.export-btn').style.display = 'flex';
}

function getStatusText(status) {
    const map = {
        'pass': '✅ Excellent',
        'warning': '⚠️ Needs Attention',
        'critical': '🚨 Critical Issues'
    };
    return map[status] || status;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function exportReport() {
    if (!currentResults) return;
    
    const json = JSON.stringify(currentResults, null, 2);
    const blob = new Blob([json], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'codesage-report.json';
    a.click();
}
