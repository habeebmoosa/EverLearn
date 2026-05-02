/* ──────────────────────────────────────────────────────────────
   EverLearn — 3-Panel UI Logic
   ────────────────────────────────────────────────────────────── */

let currentSessionId = null;
let pollInterval = null;
let qualityChart = null;
let sourceCounter = 0;
let currentReportMarkdown = '';
let currentSessionData = null;
let currentSessionSources = []; // user-provided sources for the active session

// ──── Markdown Renderer ────

function renderMarkdown(md) {
    if (!md) return '<p>No report available.</p>';
    try {
        if (typeof marked !== 'undefined') {
            if (typeof marked.parse === 'function') { const r = marked.parse(md); if (r && r !== md) return r; }
            if (typeof marked === 'function') { const r = marked(md); if (r && r !== md) return r; }
        }
    } catch (e) { console.error('Marked error:', e); }
    // Fallback
    let h = md;
    h = h.replace(/```[\w]*\n([\s\S]*?)```/g, '<pre><code>$1</code></pre>');
    h = h.replace(/^#### (.+)$/gm, '<h4>$1</h4>');
    h = h.replace(/^### (.+)$/gm, '<h3>$1</h3>');
    h = h.replace(/^## (.+)$/gm, '<h2>$1</h2>');
    h = h.replace(/^# (.+)$/gm, '<h1>$1</h1>');
    h = h.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    h = h.replace(/\*(.+?)\*/g, '<em>$1</em>');
    h = h.replace(/`([^`]+)`/g, '<code>$1</code>');
    h = h.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>');
    h = h.replace(/^> (.+)$/gm, '<blockquote>$1</blockquote>');
    h = h.replace(/^- (.+)$/gm, '<li>$1</li>');
    h = h.replace(/((?:<li>.*<\/li>\n?)+)/g, '<ul>$1</ul>');
    h = h.replace(/\n\n(?!<)/g, '</p><p>');
    h = '<p>' + h + '</p>';
    h = h.replace(/<p>\s*<\/p>/g, '');
    h = h.replace(/<p>\s*(<h[1-4])/g, '$1');
    h = h.replace(/(<\/h[1-4]>)\s*<\/p>/g, '$1');
    h = h.replace(/<p>\s*(<ul|<pre|<blockquote)/g, '$1');
    h = h.replace(/(<\/ul>|<\/pre>|<\/blockquote>)\s*<\/p>/g, '$1');
    return h;
}

// ──── Panel Management ────

function showPanel(name) {
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    document.getElementById(`panel-${name}`).classList.add('active');
}

function showNewSession() {
    currentSessionId = null;
    if (pollInterval) { clearInterval(pollInterval); pollInterval = null; }
    showPanel('new');
    updateSidebarActive(null);
    document.getElementById('rp-sources').innerHTML = '<div class="rp-empty">Add sources when creating a session.</div>';
    document.getElementById('rp-metrics').innerHTML = '<div class="rp-empty">No metrics yet.</div>';
}

// ──── Sidebar Sessions ────

async function loadSidebarSessions() {
    try {
        const resp = await fetch('/api/research/sessions/list');
        const data = await resp.json();
        const container = document.getElementById('sidebar-sessions');
        if (!data.sessions || data.sessions.length === 0) {
            container.innerHTML = '<div class="rp-empty" style="padding:12px 8px;">No sessions yet.</div>';
            return;
        }
        container.innerHTML = data.sessions.sort((a, b) => new Date(b.created_at) - new Date(a.created_at)).map(s => `
            <div class="sb-item ${s.session_id === currentSessionId ? 'active' : ''}" onclick="loadSession('${s.session_id}')">
                <span class="sb-item-title">${esc(s.topic)}</span>
                <span class="sb-item-meta">
                    <span class="sb-dot ${s.status}"></span>
                    ${s.current_iteration}/${s.max_iterations} iters &middot; Score ${Math.round(s.best_score)}
                </span>
            </div>
        `).join('');
    } catch (e) { console.error('Sidebar load error:', e); }
}

function updateSidebarActive(id) {
    document.querySelectorAll('.sb-item').forEach(el => el.classList.remove('active'));
    if (id) {
        document.querySelectorAll('.sb-item').forEach(el => {
            if (el.getAttribute('onclick')?.includes(id)) el.classList.add('active');
        });
    }
}

// ──── Source Management ────

function addSource(type) {
    sourceCounter++;
    const container = document.getElementById('sources-container');
    const div = document.createElement('div');
    div.className = 'source-item';
    div.id = `source-${sourceCounter}`;
    const labels = { url: 'URL', text: 'TEXT', file: 'FILE' };
    if (type === 'file') {
        div.innerHTML = `<span class="source-type">${labels[type]}</span><input type="file" data-type="${type}" accept=".txt,.md,.pdf,.csv,.json,.docx"><button class="remove-btn" onclick="this.parentElement.remove()">×</button>`;
    } else if (type === 'text') {
        div.innerHTML = `<span class="source-type">${labels[type]}</span><textarea data-type="${type}" placeholder="Paste text..." rows="2"></textarea><button class="remove-btn" onclick="this.parentElement.remove()">×</button>`;
    } else {
        div.innerHTML = `<span class="source-type">${labels[type]}</span><input type="text" data-type="${type}" placeholder="https://example.com/article"><button class="remove-btn" onclick="this.parentElement.remove()">×</button>`;
    }
    container.appendChild(div);
}

function collectSources() {
    const sources = [];
    document.querySelectorAll('.source-item').forEach(item => {
        const input = item.querySelector('input[type="text"], textarea');
        const fileInput = item.querySelector('input[type="file"]');
        const type = (input || fileInput).dataset.type;
        if (type === 'file' && fileInput?.files.length > 0) {
            sources.push({ type: 'file', content: fileInput.files[0].name, label: fileInput.files[0].name, _file: fileInput.files[0] });
        } else if (input?.value.trim()) {
            sources.push({ type, content: input.value.trim(), label: null });
        }
    });
    return sources;
}

// ──── Start Learning ────

async function startResearch() {
    const topic = document.getElementById('topic').value.trim();
    if (!topic) { alert('Please enter a topic'); return; }

    const btn = document.getElementById('start-btn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span>Starting...';

    try {
        const sources = collectSources();
        const dataSources = [];
        for (const src of sources) {
            if (src.type === 'file' && src._file) {
                const fd = new FormData(); fd.append('file', src._file);
                const ur = await fetch('/api/research/upload', { method: 'POST', body: fd });
                const ud = await ur.json();
                if (ud.error) { alert(`File error: ${ud.error}`); continue; }
                dataSources.push({ type: 'file', content: ud.text, label: src.label || ud.file_name });
            } else {
                dataSources.push({ type: src.type, content: src.content, label: src.label });
            }
        }

        currentSessionSources = dataSources;
        const focusAreas = document.getElementById('focus-areas').value.trim();
        const depth = document.getElementById('depth').value;
        const maxIter = parseInt(document.getElementById('max-iterations').value) || 5;
        const webSearch = document.getElementById('web-search').checked;

        const resp = await fetch('/api/research/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                topic,
                data_sources: dataSources.length ? dataSources : null,
                config: { max_iterations: maxIter, depth, focus_areas: focusAreas ? focusAreas.split(',').map(s => s.trim()).filter(Boolean) : null, enable_web_search: webSearch },
            }),
        });
        if (!resp.ok) throw new Error('Failed to start');
        const data = await resp.json();
        currentSessionId = data.session_id;

        openSession(data.session_id, topic, data.max_iterations);
        loadSidebarSessions();
    } catch (err) {
        alert('Error: ' + err.message);
    } finally {
        btn.disabled = false;
        btn.innerHTML = 'Start Learning';
    }
}

// ──── Open / Load Session ────

function openSession(sessionId, topic, maxIter) {
    currentSessionId = sessionId;
    showPanel('session');
    updateSidebarActive(sessionId);

    document.getElementById('session-topic').textContent = topic || 'Loading...';
    document.getElementById('session-status').textContent = 'Running';
    document.getElementById('session-status').className = 'status-pill running';
    document.getElementById('session-actions').style.display = 'none';
    document.getElementById('progress-fill').style.width = '0%';
    document.getElementById('step-text').textContent = 'Starting...';
    document.getElementById('activity-feed').innerHTML = '<div class="feed-placeholder">Learning session starting...</div>';
    document.getElementById('feed-heading').style.display = 'none';
    document.getElementById('chart-heading').style.display = 'none';
    document.getElementById('chart-wrap').style.display = 'none';
    document.getElementById('report-section').style.display = 'none';
    ['m-score','m-iteration','m-kept','m-discarded','m-sources','m-duration'].forEach(id => document.getElementById(id).textContent = '--');

    updateRightPanelSources(currentSessionSources);
    document.getElementById('rp-metrics').innerHTML = '<div class="rp-empty">Waiting for data...</div>';

    startPolling();
}

async function loadSession(sessionId) {
    currentSessionId = sessionId;
    if (pollInterval) { clearInterval(pollInterval); pollInterval = null; }
    showPanel('session');
    updateSidebarActive(sessionId);

    // Reset all session state to prevent data bleeding between sessions
    currentSessionSources = [];
    currentReportMarkdown = '';
    currentSessionData = null;

    // Reset UI to clean loading state
    document.getElementById('session-topic').textContent = 'Loading...';
    document.getElementById('activity-feed').innerHTML = '<div class="feed-placeholder">Loading session...</div>';
    document.getElementById('rp-metrics').removeAttribute('data-metrics-fetched');
    document.getElementById('report-content').innerHTML = '';
    document.getElementById('report-section').style.display = 'none';
    document.getElementById('session-actions').style.display = 'none';
    document.getElementById('feed-heading').style.display = 'none';
    document.getElementById('chart-heading').style.display = 'none';
    document.getElementById('chart-wrap').style.display = 'none';
    document.getElementById('progress-track').style.display = '';
    document.getElementById('step-text').style.display = '';
    document.getElementById('progress-fill').style.width = '0%';
    document.getElementById('step-text').textContent = 'Loading...';
    ['m-score','m-iteration','m-kept','m-discarded','m-sources','m-duration'].forEach(id => document.getElementById(id).textContent = '--');
    document.getElementById('rp-sources').innerHTML = '<div class="rp-empty">Loading sources...</div>';
    document.getElementById('rp-metrics').innerHTML = '<div class="rp-empty">Loading metrics...</div>';
    if (qualityChart) { qualityChart.destroy(); qualityChart = null; }

    try {
        const resp = await fetch(`/api/research/${sessionId}`);
        if (currentSessionId !== sessionId) return; // user switched session during fetch
        const data = await resp.json();
        if (currentSessionId !== sessionId) return;
        currentSessionData = data;
        document.getElementById('session-topic').textContent = data.topic;

        // Restore user-provided data sources for the right panel
        currentSessionSources = (data.data_sources && data.data_sources.length) ? data.data_sources : [];

        if (data.status === 'running' || data.status === 'queued') {
            updateSessionUI(data);
            startPolling();
        } else {
            updateSessionUI(data);
            if (data.status === 'completed') {
                // If report is already in the response (from Langfuse cache), use it directly
                if (data.report) {
                    currentReportMarkdown = data.report;
                    document.getElementById('report-content').innerHTML = renderMarkdown(data.report);
                    document.getElementById('report-section').style.display = '';
                    document.getElementById('session-actions').style.display = 'flex';
                    reorderPanelForReport();
                } else {
                    await loadReport(sessionId, data);
                }
            }
        }
    } catch (e) { console.error('Load session error:', e); }
}

// ──── Polling ────

function startPolling() {
    if (pollInterval) clearInterval(pollInterval);
    pollInterval = setInterval(fetchProgress, 5000);
    fetchProgress();
}

async function fetchProgress() {
    const sessionId = currentSessionId;
    if (!sessionId) return;
    try {
        const resp = await fetch(`/api/research/${sessionId}`);
        if (currentSessionId !== sessionId) return; // user switched session during fetch
        if (!resp.ok) return;
        const data = await resp.json();
        if (currentSessionId !== sessionId) return;
        currentSessionData = data;
        updateSessionUI(data);

        if (data.status === 'completed' || data.status === 'failed') {
            clearInterval(pollInterval); pollInterval = null;
            if (data.status === 'completed') {
                setTimeout(() => {
                    if (currentSessionId === sessionId) loadReport(sessionId, data);
                }, 500);
            }
            loadSidebarSessions();
        }
    } catch (e) { console.error('Poll error:', e); }
}

// ──── Update Session UI ────

function updateSessionUI(data) {
    // Status
    document.getElementById('session-status').textContent = data.status;
    document.getElementById('session-status').className = `status-pill ${data.status}`;

    // Metrics
    const totalSources = data.iterations.reduce((sum, i) => sum + ((i.details || {}).total_sources || 0), 0);
    const totalDuration = data.iterations.reduce((sum, i) => sum + (i.duration_seconds || 0), 0);
    const kept = data.iterations.filter(i => i.kept).length;
    const discarded = data.iterations.filter(i => !i.kept).length;

    document.getElementById('m-score').textContent = Math.round(data.best_score);
    document.getElementById('m-iteration').textContent = `${data.current_iteration}/${data.max_iterations}`;
    document.getElementById('m-kept').textContent = kept;
    document.getElementById('m-discarded').textContent = discarded;
    document.getElementById('m-sources').textContent = totalSources;
    document.getElementById('m-duration').textContent = formatDuration(totalDuration);

    // Progress
    const pct = data.max_iterations > 0 ? Math.round((data.current_iteration / data.max_iterations) * 100) : 0;
    document.getElementById('progress-fill').style.width = `${pct}%`;
    document.getElementById('step-text').textContent = data.current_step || '';

    if (data.status === 'completed' || data.status === 'failed') {
        document.getElementById('progress-track').style.display = 'none';
        document.getElementById('step-text').style.display = 'none';
    } else {
        document.getElementById('progress-track').style.display = '';
        document.getElementById('step-text').style.display = '';
    }

    // Activity feed
    buildActivityFeed(data.iterations);
    if (data.iterations.length > 0) {
        document.getElementById('feed-heading').style.display = '';
    }

    // Chart
    if (data.iterations.length > 0) {
        document.getElementById('chart-heading').style.display = '';
        document.getElementById('chart-wrap').style.display = '';
        buildChart(data.iterations);
    }

    // Right panel sources from iteration details
    updateRightPanelFromIterations(data.iterations);

    // Right panel metrics
    updateRightPanelMetrics(data);

    // Show download buttons if completed
    document.getElementById('session-actions').style.display = (data.status === 'completed') ? 'flex' : 'none';
}

function buildActivityFeed(iterations) {
    const feed = document.getElementById('activity-feed');
    if (!iterations.length) { feed.innerHTML = '<div class="feed-placeholder">Waiting for first iteration...</div>'; return; }

    feed.innerHTML = iterations.map(iter => {
        const d = iter.details || {};
        const queries = (d.search_queries || []).slice(0, 3);
        const srcCount = d.total_sources || 0;
        const icon = iter.kept ? 'kept' : 'discarded';
        const symbol = iter.kept ? '+' : '×';

        // Rubric breakdown from evaluator
        const evalData = iter.evaluation || {};
        const breakdown = evalData.scoring_breakdown || null;
        const gaps = (evalData.remaining_gaps || []).slice(0, 3);
        const prevScore = evalData.previous_score != null ? evalData.previous_score : null;

        let rubricHtml = '';
        if (breakdown) {
            const dims = Object.entries(breakdown);
            rubricHtml = `
            <details class="rubric-details">
                <summary class="rubric-toggle">Rubric Breakdown <span class="rubric-delta">${prevScore != null ? (iter.quality_score - prevScore >= 0 ? '+' : '') + Math.round(iter.quality_score - prevScore) + ' vs prev' : ''}</span></summary>
                <div class="rubric-grid">
                    ${dims.map(([dim, scores]) => {
                        const newVal = scores.new ?? scores.score ?? '-';
                        const prevVal = scores.prev ?? '-';
                        const delta = (typeof newVal === 'number' && typeof prevVal === 'number') ? newVal - prevVal : null;
                        const deltaClass = delta === null ? '' : delta > 0 ? 'pos' : delta < 0 ? 'neg' : 'neu';
                        return `<div class="rubric-row">
                            <span class="rubric-dim">${dim.replace(/_/g,' ')}</span>
                            <span class="rubric-scores">
                                <span class="rubric-new">${newVal}/10</span>
                                ${prevVal !== '-' ? `<span class="rubric-prev">(prev ${prevVal})</span>` : ''}
                                ${delta !== null ? `<span class="rubric-delta-sm ${deltaClass}">${delta >= 0 ? '+' : ''}${delta}</span>` : ''}
                            </span>
                        </div>`;
                    }).join('')}
                </div>
                ${gaps.length ? `<div class="rubric-gaps"><span class="rubric-gap-label">Gaps:</span> ${gaps.map(g => `<span class="rubric-gap-item">${esc(g)}</span>`).join('')}</div>` : ''}
            </details>`;
        }

        return `
        <div class="feed-item">
            <div class="feed-icon ${icon}">${symbol}</div>
            <div class="feed-body">
                <div class="feed-title">Iteration #${iter.iteration} — ${iter.kept ? 'Kept' : 'Discarded'}</div>
                <div class="feed-detail">${esc(iter.summary || '')}</div>
                <div class="feed-tags">
                    <span class="feed-tag score">Score ${Math.round(iter.quality_score)}</span>
                    ${iter.duration_seconds ? `<span class="feed-tag time">${formatDuration(iter.duration_seconds)}</span>` : ''}
                    ${srcCount ? `<span class="feed-tag">${srcCount} sources</span>` : ''}
                    ${queries.length ? `<span class="feed-tag">${queries.length} queries</span>` : ''}
                </div>
                ${queries.length ? `<div class="feed-detail" style="margin-top:4px;">Queries: ${queries.map(q => `"${esc(q)}"`).join(', ')}</div>` : ''}
                ${rubricHtml}
            </div>
        </div>`;
    }).join('');

    feed.scrollTop = feed.scrollHeight;
}


function buildChart(iterations) {
    const canvas = document.getElementById('quality-chart');
    if (qualityChart) { qualityChart.destroy(); qualityChart = null; }
    qualityChart = new Chart(canvas.getContext('2d'), {
        type: 'line',
        data: {
            labels: iterations.map(i => `#${i.iteration}`),
            datasets: [{
                label: 'Quality Score',
                data: iterations.map(i => i.quality_score),
                borderColor: '#9c27b0',
                backgroundColor: 'rgba(156,39,176,0.08)',
                fill: true,
                tension: 0.3,
                pointRadius: 6,
                pointBackgroundColor: iterations.map(i => i.kept ? '#10b981' : '#ef4444'),
                pointBorderColor: iterations.map(i => i.kept ? '#10b981' : '#ef4444'),
                pointBorderWidth: 2,
            }],
        },
        options: {
            responsive: true,
            scales: {
                y: { beginAtZero: true, max: 100, title: { display: true, text: 'Score' } },
                x: { title: { display: true, text: 'Iteration' } },
            },
            plugins: { legend: { display: false } },
        },
    });
}

async function loadReport(sessionId, data) {
    try {
        const resp = await fetch(`/api/research/${sessionId}/report`);
        if (currentSessionId !== sessionId) return; // user switched session during fetch
        const rd = await resp.json();
        if (currentSessionId !== sessionId) return;
        const report = rd.report || data?.report || 'No report available.';
        currentReportMarkdown = report;
        document.getElementById('report-content').innerHTML = renderMarkdown(report);
        document.getElementById('report-section').style.display = '';
        document.getElementById('session-actions').style.display = 'flex';
        reorderPanelForReport();
    } catch (e) { console.error('Report load error:', e); }
}

function reorderPanelForReport() {
    const panel = document.getElementById('panel-session');
    const report = document.getElementById('report-section');
    const feedHeading = document.getElementById('feed-heading');
    // Move report before iteration results heading and feed
    panel.insertBefore(report, feedHeading);
}

// ──── Right Panel ────

function updateRightPanelSources(dataSources) {
    const el = document.getElementById('rp-sources');
    if (!dataSources || !dataSources.length) {
        el.innerHTML = '<div class="rp-empty">No user sources provided.</div>';
        return;
    }
    el.innerHTML = dataSources.map(s => {
        const t = s.type || 'text';
        const label = s.label || s.content || '';
        const isUrl = t === 'url';
        return `<div class="rp-src-item">
            <span class="rp-src-type ${t}">${t}</span>
            <div class="rp-src-body">
                <div class="rp-src-title">${esc(label.substring(0, 60))}</div>
                ${isUrl ? `<div class="rp-src-url"><a href="${esc(s.content)}" target="_blank">${esc(s.content.substring(0, 50))}</a></div>` : ''}
            </div>
        </div>`;
    }).join('');
}

function updateRightPanelFromIterations(iterations) {
    const el = document.getElementById('rp-sources');
    // Collect all unique web sources from all iterations
    const allSources = [];
    const seen = new Set();
    iterations.forEach(iter => {
        const d = iter.details || {};
        (d.sources_collected || []).forEach(s => {
            const key = s.url || s.title;
            // Skip non-web sources (file:// paths, user-provided file names)
            if (s.url && s.url.startsWith('file://')) return;
            if (s.type === 'user_text' || s.type === 'file') return;
            if (key && !seen.has(key)) {
                seen.add(key);
                allSources.push(s);
            }
        });
    });

    if (!allSources.length && !currentSessionSources.length) {
        el.innerHTML = '<div class="rp-empty">No sources collected yet.</div>';
        return;
    }

    let html = '';
    // User-provided first
    if (currentSessionSources.length) {
        html += '<div style="font-size:10px;font-weight:600;text-transform:uppercase;color:var(--text-secondary);padding:4px 0 4px;">User Provided</div>';
        currentSessionSources.forEach(s => {
            const t = s.type || 'text';
            html += `<div class="rp-src-item"><span class="rp-src-type ${t}">${t}</span><div class="rp-src-body"><div class="rp-src-title">${esc((s.label || s.content || '').substring(0, 50))}</div></div></div>`;
        });
    }
    // Web sources
    if (allSources.length) {
        html += '<div style="font-size:10px;font-weight:600;text-transform:uppercase;color:var(--text-secondary);padding:8px 0 4px;">Collected (Web)</div>';
        allSources.slice(0, 30).forEach(s => {
            const title = s.title || new URL(s.url || 'https://x.com').hostname;
            html += `<div class="rp-src-item"><span class="rp-src-type web">web</span><div class="rp-src-body"><div class="rp-src-title">${esc(title.substring(0, 50))}</div>${s.url ? `<div class="rp-src-url"><a href="${esc(s.url)}" target="_blank">${esc(s.url.substring(0, 45))}</a></div>` : ''}</div></div>`;
        });
    }
    el.innerHTML = html;
}

function updateRightPanelMetrics(data) {
    const el = document.getElementById('rp-metrics');
    const totalDuration = data.iterations.reduce((s, i) => s + (i.duration_seconds || 0), 0);
    const totalSources = data.iterations.reduce((s, i) => s + ((i.details || {}).total_sources || 0), 0);
    const totalQueries = data.iterations.reduce((s, i) => s + ((i.details || {}).search_queries || []).length, 0);

    const metrics = [
        ['Status', data.status],
        ['Best Score', `${Math.round(data.best_score)} / 100`],
        ['Iterations', `${data.iterations.length} / ${data.max_iterations}`],
        ['Total Sources', totalSources],
        ['Total Queries', totalQueries],
        ['Total Duration', formatDuration(totalDuration)],
    ];

    el.innerHTML = metrics.map(([k, v]) =>
        `<div class="rp-metric-item"><span class="rp-metric-key">${k}</span><span class="rp-metric-val">${v}</span></div>`
    ).join('');

    // Fetch Langfuse metrics only once when completed (not during polling)
    if (currentSessionId && data.status === 'completed' && !el.dataset.metricsFetched) {
        el.dataset.metricsFetched = 'true';
        fetchLangfuseMetrics(currentSessionId);
    }
}

async function fetchLangfuseMetrics(sessionId) {
    try {
        const resp = await fetch(`/api/research/${sessionId}/metrics`);
        if (currentSessionId !== sessionId) return; // user switched session during fetch
        const data = await resp.json();
        if (currentSessionId !== sessionId) return;
        if (!data.metrics || data.error) return;

        const m = data.metrics;
        const el = document.getElementById('rp-metrics');
        // Append Langfuse metrics below existing ones
        const lmHtml = [
            m.total_tokens ? ['Total Tokens', m.total_tokens.toLocaleString()] : null,
            m.total_input_tokens ? ['Input Tokens', m.total_input_tokens.toLocaleString()] : null,
            m.total_output_tokens ? ['Output Tokens', m.total_output_tokens.toLocaleString()] : null,
            m.total_cost_usd ? ['Est. Cost', `$${m.total_cost_usd.toFixed(4)}`] : null,
            m.total_latency_ms ? ['Latency', `${(m.total_latency_ms / 1000).toFixed(1)}s`] : null,
            m.llm_calls ? ['LLM Calls', m.llm_calls] : null,
            m.models_used?.length ? ['Models', m.models_used.join(', ')] : null,
        ].filter(Boolean);

        if (lmHtml.length) {
            el.innerHTML += '<div style="font-size:10px;font-weight:600;text-transform:uppercase;color:var(--text-secondary);padding:8px 0 4px;margin-top:4px;border-top:1px solid var(--border);">Langfuse</div>';
            el.innerHTML += lmHtml.map(([k, v]) =>
                `<div class="rp-metric-item"><span class="rp-metric-key">${k}</span><span class="rp-metric-val">${v}</span></div>`
            ).join('');
        }
    } catch (e) { /* Langfuse metrics are optional */ }
}

// ──── Downloads ────

function downloadReport() {
    if (!currentReportMarkdown) return;
    const topic = document.getElementById('session-topic').textContent || 'EverLearn Report';
    const filename = topic.replace(/[^a-zA-Z0-9 ]/g, '').replace(/\s+/g, '_').substring(0, 50);
    const renderedHtml = renderMarkdown(currentReportMarkdown);
    const fullHtml = `<div style="font-family:Georgia,'Times New Roman',serif;color:#222;line-height:1.75;font-size:13px;max-width:680px;margin:0 auto;word-wrap:break-word;">
        <style>h1{font-size:22px;margin:20px 0 10px;padding-bottom:6px;border-bottom:2px solid #9c27b0;color:#222;font-weight:700}h2{font-size:17px;margin:18px 0 8px;color:#9c27b0;font-weight:700}h3{font-size:14px;margin:14px 0 6px;color:#333;font-weight:700}p{margin-bottom:8px;font-size:13px;line-height:1.75}ul,ol{margin:6px 0 10px 20px;font-size:13px}li{margin-bottom:3px;line-height:1.6}blockquote{border-left:3px solid #CE93D8;padding:6px 12px;margin:8px 0;color:#555;font-style:italic;background:#f8f8fc}code{background:#f0f0f0;padding:1px 4px;border-radius:3px;font-size:12px;font-family:monospace}pre{background:#f5f5f5;color:#333;padding:10px;border-radius:4px;white-space:pre-wrap;word-wrap:break-word;margin:8px 0;font-size:11px;border:1px solid #ddd}pre code{background:transparent;padding:0}table{width:100%;border-collapse:collapse;margin:8px 0;font-size:12px}th,td{border:1px solid #ddd;padding:5px 8px;text-align:left}th{background:#f0f2f6;font-weight:600}strong{font-weight:700}a{color:#9c27b0;text-decoration:none}</style>
        ${renderedHtml}</div>`;
    html2pdf().set({
        margin: [12,12,12,12], filename: `${filename}_report.pdf`,
        image: { type: 'jpeg', quality: 0.98 },
        html2canvas: { scale: 2, useCORS: true, logging: false },
        jsPDF: { unit: 'mm', format: 'a4', orientation: 'portrait' },
        pagebreak: { mode: ['css', 'legacy'] },
    }).from(fullHtml).save();
}

function downloadMarkdown() {
    if (!currentReportMarkdown) return;
    const topic = document.getElementById('session-topic').textContent || 'EverLearn Report';
    const filename = topic.replace(/[^a-zA-Z0-9 ]/g, '').replace(/\s+/g, '_').substring(0, 50);
    const blob = new Blob([currentReportMarkdown], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = `${filename}_report.md`;
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

// ──── Utilities ────

function formatDuration(seconds) {
    if (!seconds || seconds <= 0) return '0s';
    if (seconds < 60) return `${Math.round(seconds)}s`;
    const m = Math.floor(seconds / 60), s = Math.round(seconds % 60);
    return `${m}m ${s}s`;
}

function esc(text) {
    const d = document.createElement('div'); d.textContent = text || ''; return d.innerHTML;
}

// Depth ↔ iterations sync
document.getElementById('depth').addEventListener('change', function() {
    document.getElementById('max-iterations').value = { quick: 2, standard: 5, deep: 10 }[this.value] || 5;
});

// ──── Init ────
loadSidebarSessions();
