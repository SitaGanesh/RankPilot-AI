(() => {
  const pollEvery = 1500;
  const maxPollFailures = 5;
  class ApiError extends Error {
    constructor(message, status) {
      super(message);
      this.status = status;
    }
  }
  const api = (path, options = {}) => fetch(path, { headers: { 'Content-Type': 'application/json' }, ...options }).then(async response => {
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new ApiError(body.detail || body.error || `Request failed (${response.status})`, response.status);
    return body;
  });
  const escapeHtml = value => String(value ?? '').replace(/[&<>'"]/g, char => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', "'":'&#39;', '"':'&quot;' }[char]));
  const setError = (id, message) => { const node = document.getElementById(id); if (node) node.textContent = message || ''; };

  const form = document.getElementById('audit-form');
  if (form) {
    form.addEventListener('submit', async event => {
      event.preventDefault();
      const input = document.getElementById('audit-url');
      const button = form.querySelector('button');
      let url = input.value.trim();
      if (url && !/^https?:\/\//i.test(url)) url = `https://${url}`;
      button.disabled = true;
      button.querySelector('span').textContent = 'Checking URL...';
      setError('form-error', '');
      try {
        const audit = await api('/api/audits/', { method: 'POST', body: JSON.stringify({ url }) });
        window.location.href = `/audits/${audit.id}/`;
      } catch (error) {
        setError('form-error', error.message);
        button.disabled = false;
        button.querySelector('span').textContent = 'Evaluate page';
      }
    });
  }

  const shell = document.querySelector('[data-audit-id]');
  if (!shell) return;
  const auditId = shell.dataset.auditId;
  const stageOrder = ['coordinator', 'collector', 'specialized_agent', 'finding_validator', 'scoring', 'aggregator', 'comparison', 'final_audit_llm', 'output_validator', 'report_builder'];
  const stageLabels = { coordinator:'Coordinator', collector:'Data collector', specialized_agent:'Specialized agent', finding_validator:'Finding validator', scoring:'Scoring', aggregator:'Aggregator', comparison:'Comparison', final_audit_llm:'Final Audit LLM', output_validator:'Output validator', report_builder:'Report builder' };
  let selectedAgent = null;
  let reportData = null;
  let agentShown = false;
  let reportShown = false;
  let pollFailures = 0;
  const agentStates = new Map();

  const agentButton = agentId => Array.from(document.querySelectorAll('.run-agent'))
    .find(button => button.dataset.agentId === agentId);
  const applyAgentState = agentId => {
    const button = agentButton(agentId);
    if (!button) return;
    const state = agentStates.get(agentId) || {};
    button.classList.toggle('is-agent-active', Boolean(state.running || state.selected));
    button.disabled = Boolean(state.running);
    button.querySelector('span').innerHTML = state.running ? '...' : '&#8594;';
  };

  const renderStepper = events => {
    const byStage = {};
    events.forEach(event => { byStage[event.stage] = event; });
    document.getElementById('stepper').innerHTML = stageOrder.map(stage => {
      const event = byStage[stage] || { status:'pending', message:'Waiting' };
      return `<div class="step is-${escapeHtml(event.status)}"><span>${escapeHtml(stageLabels[stage] || stage)}</span><strong>${escapeHtml(event.status)}</strong></div>`;
    }).join('');
    const latest = events[events.length - 1];
    if (latest) document.getElementById('stage-message').textContent = latest.message;
  };

  const loadAgents = async () => {
    if (agentShown) return;
    const agents = await api('/api/agents/');
    document.getElementById('agent-list').innerHTML = agents.map(agent => `<article class="agent-card"><p class="panel-kicker">${escapeHtml(agent.version)}</p><h3>${escapeHtml(agent.name)}</h3><p>${escapeHtml(agent.scope)}</p><button class="btn btn-outline-dark run-agent" data-agent-id="${escapeHtml(agent.id)}" type="button">Run evaluation <span aria-hidden="true">&#8594;</span></button></article>`).join('');
    agents.forEach(agent => agentStates.set(agent.id, { running: false, selected: false }));
    document.querySelectorAll('.run-agent').forEach(button => button.addEventListener('click', () => startAgent(button.dataset.agentId)));
    document.getElementById('agent-panel').classList.remove('is-hidden');
    agentShown = true;
  };

  const renderReport = report => {
    reportData = report;
    const score = report.score || {};
    document.getElementById('score-value').textContent = Number(score.percent || 0).toFixed(1);
    document.getElementById('score-points').textContent = `${Number(score.earned || 0).toFixed(1)} of ${Number(score.applicable_weight || 0).toFixed(1)} applicable points earned`;
    document.getElementById('coverage-value').textContent = `${Number(report.coverage || score.coverage_percent || 0).toFixed(1)}%`;
    document.getElementById('coverage-note').textContent = `${Number(score.applicable_weight || 0).toFixed(1)} applicable points`;
    const comparison = report.comparison || {};
    document.getElementById('delta-value').textContent = `${Number(comparison.delta || 0) >= 0 ? '+' : ''}${Number(comparison.delta || 0).toFixed(1)} pts`;
    document.getElementById('delta-note').textContent = comparison.previous_run_id ? 'Compared with previous run' : 'No previous run yet';
    const narrative = report.final_audit || {};
    const card = (title, values) => `<article class="narrative-card"><p class="panel-kicker">${title}</p><ul>${(values || []).length ? values.map(value => `<li>${escapeHtml(value)}</li>`).join('') : '<li>Nothing recorded yet.</li>'}</ul></article>`;
    document.getElementById('narrative').innerHTML = `${card('WHAT IS WORKING', narrative.strengths)}${card('WHAT NEEDS ATTENTION', narrative.weaknesses)}${card('QUICK WINS', narrative.quick_wins)}`;
    const safeChart = src => typeof src === 'string' && /^data:image\/png;base64,[A-Za-z0-9+/=]+$/.test(src);
    document.getElementById('charts').innerHTML = Object.entries(report.charts || {})
      .filter(([, src]) => safeChart(src))
      .map(([name, src]) => `<figure><img src="${escapeHtml(src)}" alt="${escapeHtml(name.replaceAll('_', ' '))} chart"></figure>`).join('');
    const findings = (report.agents || []).flatMap(agent => agent.findings || []);
    document.getElementById('finding-count').textContent = `${findings.length} checks`;
    document.getElementById('findings-table').innerHTML = findings.map(finding => `<article class="finding-row"><div class="finding-status status-${escapeHtml(finding.status)}">${escapeHtml(finding.status)}</div><div><strong>${escapeHtml(finding.title)}</strong><p>${escapeHtml(finding.recommendation)}</p></div><div class="muted-label">${Number(finding.weight || 0)} pts</div></article>`).join('');
    const unknown = (report.agents || []).flatMap(agent => agent.checks_unknown || []);
    if (unknown.length) { document.getElementById('unknown-section').classList.remove('is-hidden'); document.getElementById('unknown-list').innerHTML = unknown.map(item => `<li>${escapeHtml(item)}</li>`).join(''); }
    document.getElementById('report-panel').classList.remove('is-hidden');
    const state = agentStates.get(selectedAgent) || {};
    state.running = false;
    state.selected = true;
    agentStates.set(selectedAgent, state);
    applyAgentState(selectedAgent);
    reportShown = true;
  };

  const startAgent = async agentId => {
    if (selectedAgent && selectedAgent !== agentId) {
      const previousState = agentStates.get(selectedAgent);
      if (previousState && !previousState.running) {
        previousState.selected = false;
        applyAgentState(selectedAgent);
      }
    }
    selectedAgent = agentId;
    reportShown = false;
    agentStates.set(agentId, { running: true, selected: true });
    applyAgentState(agentId);
    try { await api(`/api/audits/${auditId}/agents/${encodeURIComponent(agentId)}/run/`, { method: 'POST' }); await poll(); }
    catch (error) {
      const state = agentStates.get(agentId) || {};
      state.running = false;
      state.selected = false;
      agentStates.set(agentId, state);
      applyAgentState(agentId);
      setError('page-error', error.message);
    }
  };

  const poll = async () => {
    try {
      const status = await api(`/api/audits/${auditId}/`);
      pollFailures = 0;
      document.getElementById('audit-url-label').textContent = status.url;
      document.getElementById('audit-status').textContent = status.status;
      renderStepper(status.stage_events || []);
      if ((status.status === 'collected' || status.status === 'completed') && !selectedAgent) await loadAgents();
      if (status.status === 'completed' && selectedAgent && !reportShown) renderReport(await api(`/api/audits/${auditId}/report/?agent_id=${encodeURIComponent(selectedAgent)}`));
      if (status.status === 'failed') setError('page-error', 'The audit stopped before a report was ready. Check the stage messages above.');
      if (!reportShown && status.status !== 'failed') window.setTimeout(poll, pollEvery);
    } catch (error) {
      pollFailures += 1;
      setError('page-error', error.message);
      if (error.status === 404 || pollFailures >= maxPollFailures) return;
      window.setTimeout(poll, Math.min(pollEvery * (2 ** pollFailures), 15000));
    }
  };
  document.getElementById('download-report').addEventListener('click', () => { if (!reportData) return; const blob = new Blob([JSON.stringify(reportData, null, 2)], { type:'application/json' }); const link = document.createElement('a'); link.href = URL.createObjectURL(blob); link.download = `seo-audit-${auditId}.json`; link.click(); URL.revokeObjectURL(link.href); });
  poll();
})();
