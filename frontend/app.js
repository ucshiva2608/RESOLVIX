/**
 * ARES — Autonomous Response Engineering System
 * Frontend Client Application & Real-time SSE Controller
 */

// Application State
const state = {
  incidentId: null,
  scenario: null,
  currentStage: 'IDLE',
  status: 'HEALTHY',
  tokens: {
    balance: 10000,
    totalUsed: 0,
    agentUsage: {}
  },
  postmortemData: null,
  replanCount: 0,
  activeApproval: null
};

// Stage mapping to flowchart node IDs
const STAGE_NODES = {
  'DETECTION': 'node-DETECTION',
  'TELEMETRY_COLLECTION': 'node-TELEMETRY_COLLECTION',
  'COMPETING_HYPOTHESES': 'node-COMPETING_HYPOTHESES',
  'RUNBOOK_SEARCH': 'node-RUNBOOK_SEARCH',
  'ROOT_CAUSE_ANALYSIS': 'node-ROOT_CAUSE_ANALYSIS',
  'RECOVERY_PLANNING': 'node-RECOVERY_PLANNING',
  'HUMAN_APPROVAL': 'node-HUMAN_APPROVAL',
  'REMEDIATION': 'node-REMEDIATION',
  'POST_REMEDIATION_VERIFICATION': 'node-POST_REMEDIATION_VERIFICATION',
  'POSTMORTEM': 'node-POSTMORTEM'
};

const STAGE_ORDER = [
  'DETECTION',
  'TELEMETRY_COLLECTION',
  'COMPETING_HYPOTHESES',
  'RUNBOOK_SEARCH',
  'ROOT_CAUSE_ANALYSIS',
  'RECOVERY_PLANNING',
  'HUMAN_APPROVAL',
  'REMEDIATION',
  'POST_REMEDIATION_VERIFICATION',
  'POSTMORTEM'
];

// Initialize on DOM load
document.addEventListener('DOMContentLoaded', () => {
  initSSE();
  fetchInitialStatus();
});

// =============================================================================
// SERVER-SENT EVENTS (SSE) STREAM
// =============================================================================

function initSSE() {
  const eventSource = new EventSource('/api/events');

  eventSource.onopen = () => {
    console.log('[ARES SSE] Connected to real-time event stream.');
  };

  eventSource.onerror = (err) => {
    console.warn('[ARES SSE] Disconnected. Reconnecting in 3s...', err);
  };

  // Dispatch all backend events
  const eventTypes = [
    'connected', 'incident_detected', 'agent_started', 'agent_completed',
    'evidence_collected', 'hypotheses_generated', 'runbook_found',
    'root_cause_found', 'plan_created', 'approval_required',
    'approval_received', 'approval_rejected', 'execution_started',
    'execution_progress', 'execution_completed', 'execution_blocked',
    'verification_completed', 'verification_failed', 'replanning_started',
    'incident_resolved', 'incident_escalated', 'postmortem_generated',
    'token_exhausted', 'system_reset'
  ];

  eventTypes.forEach(type => {
    eventSource.addEventListener(type, (e) => {
      try {
        const payload = JSON.parse(e.data);
        handleWorkflowEvent(type, payload);
      } catch (err) {
        console.error(`Error parsing SSE event ${type}:`, err);
      }
    });
  });
}

// =============================================================================
// WORKFLOW EVENT HANDLER
// =============================================================================

function handleWorkflowEvent(type, data) {
  console.log(`[EVENT] ${type}:`, data);

  switch (type) {
    case 'incident_detected':
      onIncidentDetected(data);
      break;

    case 'agent_started':
      onAgentStarted(data);
      break;

    case 'agent_completed':
      onAgentCompleted(data);
      break;

    case 'evidence_collected':
      renderEvidence(data.evidence);
      updateTelemetryUI(data.telemetry);
      break;

    case 'hypotheses_generated':
      renderHypotheses(data.hypotheses);
      break;

    case 'runbook_found':
      appendTimeline(`Knowledge Agent matched runbook ${data.runbook_id}: ${data.title}`);
      break;

    case 'root_cause_found':
      renderRootCause(data.root_cause);
      break;

    case 'plan_created':
      updateActionPlanUI(data.plan);
      break;

    case 'approval_required':
      showApprovalGate(data);
      break;

    case 'approval_received':
      hideApprovalGate();
      appendTimeline(`✓ Human approval granted for ${data.approved_action} by ${data.approved_by}`);
      break;

    case 'approval_rejected':
      hideApprovalGate();
      appendTimeline(`✕ Human approval rejected for incident ${data.incident_id}`);
      break;

    case 'execution_started':
      updateActivityBox(
        '⚙️',
        'REMEDIATING CLUSTER',
        `ARES Execution Agent is applying safe simulation tool: ${data.action}()`,
        `Risk Level: ${data.risk_level}`,
        'Post-remediation verification against SLAs'
      );
      break;

    case 'execution_progress':
      appendTimeline(`⚙️ [${data.progress}%] ${data.step}`);
      break;

    case 'execution_completed':
      appendTimeline(`✓ Tool ${data.action}() executed successfully.`);
      if (data.result && data.result.telemetry) {
        updateTelemetryUI(data.result.telemetry);
      }
      break;

    case 'execution_blocked':
      appendTimeline(`🚨 CRITICAL SAFETY BLOCK: ${data.reason}`);
      break;

    case 'verification_completed':
      onVerificationSuccess(data);
      break;

    case 'verification_failed':
      onVerificationFailed(data);
      break;

    case 'replanning_started':
      onReplanningStarted(data);
      break;

    case 'incident_resolved':
      onIncidentResolved(data);
      break;

    case 'incident_escalated':
      onIncidentEscalated(data);
      break;

    case 'postmortem_generated':
      state.postmortemData = data.postmortem;
      document.getElementById('btn-view-postmortem').style.display = 'inline-flex';
      break;

    case 'token_exhausted':
      showTokenWarning(data);
      break;

    case 'system_reset':
      onSystemReset(data);
      break;
  }
}

// =============================================================================
// STAGE & FLOWCHART VISUALIZATIONS
// =============================================================================

function onIncidentDetected(data) {
  state.incidentId = data.incident_id;
  state.scenario = data.scenario;
  state.status = 'ACTIVE';

  // Update header badges
  const statusPill = document.getElementById('system-status-pill');
  statusPill.className = 'status-pill status-critical';
  document.getElementById('system-status-text').innerText = 'INCIDENT ACTIVE';

  document.getElementById('header-incident-id').innerText = data.incident_id;
  const sevPill = document.getElementById('header-severity-pill');
  sevPill.style.display = 'inline-block';
  document.getElementById('header-severity-text').innerText = data.severity;

  // Flowchart: Mark Detection Running
  setFlowNodeState('DETECTION', 'running');
  appendTimeline(`🔴 Incident detected: ${data.title} (${data.incident_id})`);

  // Update "What is ARES doing now?"
  updateActivityBox(
    '🔍',
    'STAGE 1: INCIDENT DETECTION',
    `ARES detected anomalous signals in cluster: ${data.title}`,
    `Symptoms: DB Saturation, elevated error rate`,
    'Observability Agent collecting telemetry and logs'
  );

  // Update Before Box
  if (data.initial_symptoms) {
    document.getElementById('before-metric-db').innerText = data.initial_symptoms.db_connections || '99/100';
    document.getElementById('before-metric-error').innerText = data.initial_symptoms.api_error_rate || '62.4%';
    document.getElementById('before-metric-resp').innerText = data.initial_symptoms.response_time || '7800 ms';
    document.getElementById('before-metric-latency').innerText = data.initial_symptoms.query_latency || '7600 ms';
  }

  // Hide postmortem button and verified box until new resolution
  document.getElementById('btn-view-postmortem').style.display = 'none';
  document.getElementById('ares-verified-box').style.display = 'none';
  document.getElementById('replan-banner').style.display = 'none';
}

function onAgentStarted(data) {
  state.currentStage = data.stage;
  setFlowNodeState(data.stage, 'running');

  // Update Activity Box based on stage
  const stageActivities = {
    'TELEMETRY_COLLECTION': {
      icon: '🔍',
      stage: 'OBSERVABILITY AGENT',
      obj: 'Collecting cluster metrics, error logs, and recent deployment commits.',
      ev: 'PostgreSQL connection status, Envoy ingress HTTP status codes',
      next: 'Investigation Agent evaluating failure modes'
    },
    'COMPETING_HYPOTHESES': {
      icon: '💡',
      stage: 'INVESTIGATION AGENT',
      obj: 'Generating 3 competing hypotheses with supporting and contradicting evidence.',
      ev: 'Correlating connection saturation against traffic volume',
      next: 'Knowledge Agent searching verified SRE runbooks'
    },
    'RUNBOOK_SEARCH': {
      icon: '📚',
      stage: 'KNOWLEDGE AGENT',
      obj: 'Searching verified SRE runbook catalog for matching remediation procedures.',
      ev: 'Query: connection pool exhaustion deadlock postgresql',
      next: 'Root Cause Agent evidence matrix synthesis'
    },
    'ROOT_CAUSE_ANALYSIS': {
      icon: '🎯',
      stage: 'ROOT CAUSE AGENT',
      obj: 'Weighing evidence matrix to determine decisive root cause with transparent confidence.',
      ev: 'Deadlock PIDs, unclosed client transactions, zero hardware defects',
      next: 'Planner Agent calculating blast radius and risk'
    },
    'RECOVERY_PLANNING': {
      icon: '🛠️',
      stage: 'PLANNER AGENT',
      obj: 'Formulating structured recovery procedure and evaluating safety blast radius.',
      ev: 'Target recovery SLA: <1.0% error rate, <35 connections',
      next: 'Human Approval Gate enforcement'
    },
    'REMEDIATION': {
      icon: '⚙️',
      stage: 'EXECUTION AGENT',
      obj: 'Executing approved safe remediation simulation tool.',
      ev: 'Allowlist compliance checked, token budget verified',
      next: 'Verification Agent diffing Before vs After telemetry'
    },
    'POST_REMEDIATION_VERIFICATION': {
      icon: '🔎',
      stage: 'VERIFICATION AGENT',
      obj: 'Comparing Before vs After metrics to verify SLA recovery.',
      ev: 'Evaluating error rate < 1.0% and connection health',
      next: 'Incident closure or autonomous replanning'
    },
    'POSTMORTEM': {
      icon: '📋',
      stage: 'POSTMORTEM AGENT',
      obj: 'Compiling SRE retrospective report, timeline, and corrective action items.',
      ev: 'Full incident trajectory, token accounting, and audit logs',
      next: 'Incident closed. SRE mission complete.'
    }
  };

  const act = stageActivities[data.stage];
  if (act) {
    updateActivityBox(act.icon, act.stage, act.obj, act.ev, act.next);
  }
}

function onAgentCompleted(data) {
  setFlowNodeState(data.stage, 'completed');
  appendTimeline(`✓ ${data.agent_name} completed (${data.tokens_used} tokens). Remaining: ${data.tokens_remaining}`);

  // Update token display
  updateTokenUI(data.tokens_remaining, data.total_tokens_consumed);
}

function setFlowNodeState(stage, stateType) {
  const nodeId = STAGE_NODES[stage];
  if (!nodeId) return;

  const nodeEl = document.getElementById(nodeId);
  if (!nodeEl) return;

  // Clear existing classes
  nodeEl.classList.remove('state-running', 'state-completed', 'state-paused', 'state-failed');

  const stateTextEl = nodeEl.querySelector('.node-state');

  if (stateType === 'running') {
    nodeEl.classList.add('state-running');
    if (stateTextEl) stateTextEl.innerText = '● Running';
  } else if (stateType === 'completed') {
    nodeEl.classList.add('state-completed');
    if (stateTextEl) stateTextEl.innerText = '✓ Completed';
  } else if (stateType === 'paused') {
    nodeEl.classList.add('state-paused');
    if (stateTextEl) stateTextEl.innerText = '⏸ Gate Paused';
  } else if (stateType === 'failed') {
    nodeEl.classList.add('state-failed');
    if (stateTextEl) stateTextEl.innerText = '✕ Failed';
  }

  // Light up prior connectors
  const stageIdx = STAGE_ORDER.indexOf(stage);
  if (stageIdx > 0) {
    const connEl = document.getElementById(`conn-${stageIdx}`);
    if (connEl) connEl.classList.add('active');
  }
}

function updateActivityBox(icon, stage, obj, ev, next) {
  document.getElementById('activity-icon').innerText = icon;
  document.getElementById('current-stage-tag').innerText = `STAGE: ${stage}`;
  document.getElementById('activity-objective').innerText = obj;
  document.getElementById('act-evidence-val').innerText = `• ${ev}`;
  document.getElementById('act-next-step').innerText = `• ${next}`;
}

// =============================================================================
// HUMAN APPROVAL GATE (Section 17)
// =============================================================================

function showApprovalGate(data) {
  state.activeApproval = data;
  setFlowNodeState('HUMAN_APPROVAL', 'paused');

  document.getElementById('approval-gate-panel').style.display = 'block';
  document.getElementById('appr-problem').innerText = data.problem || 'Database Connection Pool Saturation';
  document.getElementById('appr-action').innerText = `${data.proposed_action}()`;
  document.getElementById('appr-reason').innerHTML = `<b>Blast Radius Analysis:</b> ${data.risk_reason}`;
  document.getElementById('approval-risk-badge').innerText = `RISK: 🔴 ${data.risk_level}`;

  if (data.expected_recovery) {
    const expBox = document.getElementById('appr-expected-metrics');
    expBox.innerHTML = Object.entries(data.expected_recovery)
      .map(([k, v]) => `<span>${k}: <b>${v}</b></span>`)
      .join('');
  }

  updateActivityBox(
    '⏸️',
    'HUMAN APPROVAL GATE ENFORCED',
    `ARES paused execution. Proposed action '${data.proposed_action}' carries HIGH risk and requires human operator signoff.`,
    `Problem: ${data.problem}`,
    'Awaiting operator decision: [Approve & Execute] or [Reject]'
  );

  appendTimeline(`⏸️ Human approval gate reached. Operator signoff required for '${data.proposed_action}'.`);

  // Scroll to gate smoothly
  document.getElementById('approval-gate-panel').scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function hideApprovalGate() {
  document.getElementById('approval-gate-panel').style.display = 'none';
  state.activeApproval = null;
}

async function submitApproval() {
  if (!state.incidentId) return;
  try {
    const res = await fetch(`/api/incidents/${state.incidentId}/approve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ approved_by: 'SRE Commander (Human Operator)' })
    });
    const result = await res.json();
    appendTimeline(`✓ Approval submitted. ARES resuming remediation pipeline.`);
  } catch (err) {
    alert('Error submitting approval: ' + err.message);
  }
}

async function rejectApproval() {
  if (!state.incidentId) return;
  const reason = prompt('Please enter reason for rejecting remediation plan:', 'Operator manual override');
  if (!reason) return;

  try {
    await fetch(`/api/incidents/${state.incidentId}/reject`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason })
    });
  } catch (err) {
    alert('Error rejecting plan: ' + err.message);
  }
}

// =============================================================================
// VERIFICATION & RECOVERY (Section 20, 21 & 45)
// =============================================================================

function onVerificationSuccess(data) {
  setFlowNodeState('POST_REMEDIATION_VERIFICATION', 'completed');
  setFlowNodeState('POSTMORTEM', 'completed');

  // Update header status
  const statusPill = document.getElementById('system-status-pill');
  statusPill.className = 'status-pill status-healthy';
  document.getElementById('system-status-text').innerText = 'RECOVERY VERIFIED';

  document.getElementById('recovery-status-pill').innerText = '🟢 RECOVERY VERIFIED';
  document.getElementById('recovery-status-pill').className = 'recovery-status-pill text-neon-green';

  // Update After Box
  if (data.after) {
    document.getElementById('after-metric-db').innerText = data.after.db_connections || '24 / 100';
    document.getElementById('after-metric-error').innerText = data.after.api_error_rate || '0.4%';
    document.getElementById('after-metric-resp').innerText = data.after.response_time || '190 ms';
    document.getElementById('after-metric-latency').innerText = data.after.query_latency || '180 ms';
  }

  // Populate Section 45 Verified Message Box
  const verBox = document.getElementById('ares-verified-box');
  verBox.style.display = 'block';
  document.getElementById('verif-box-id').innerText = data.incident_id;
  document.getElementById('verif-box-error').innerText = `${data.before.api_error_rate || '62.4%'} → ${data.after.api_error_rate || '0.4%'}`;
  document.getElementById('verif-box-conn').innerText = `${data.before.db_connections || '99/100'} → ${data.after.db_connections || '24/100'}`;
  document.getElementById('verif-box-replans').innerText = state.replanCount;

  appendTimeline(`🟢 Post-remediation verification PASSED. Target SLA restored.`);
}

function onVerificationFailed(data) {
  setFlowNodeState('POST_REMEDIATION_VERIFICATION', 'failed');
  state.replanCount++;

  const banner = document.getElementById('replan-banner');
  banner.style.display = 'flex';
  document.getElementById('replan-desc').innerText = data.reason || 'SLA criteria not satisfied.';
  document.getElementById('replan-badge-count').innerText = `Attempt ${state.replanCount} / 3`;

  appendTimeline(`🔴 Verification FAILED: ${data.reason}. Initiating replanning loop...`);

  // Update After Box showing still-degraded metrics
  if (data.after) {
    document.getElementById('after-metric-db').innerText = data.after.db_connections;
    document.getElementById('after-metric-error').innerText = data.after.api_error_rate;
    document.getElementById('after-metric-resp').innerText = data.after.response_time;
    document.getElementById('after-metric-latency').innerText = data.after.query_latency;
  }
}

function onReplanningStarted(data) {
  appendTimeline(`🔄 Replanning attempt ${data.attempt}/3: Formulating revised strategy.`);
  updateActivityBox(
    '🔄',
    'AUTONOMOUS REPLANNING',
    `Initial remediation did not clear the fault. ARES is re-evaluating lingering failure signals.`,
    `Failure reason: ${data.reason}`,
    'Escalating to comprehensive remediation action'
  );
}

function onIncidentResolved(data) {
  appendTimeline(`🏁 Incident ${data.incident_id} marked as RESOLVED. Total computation: ${data.total_tokens} tokens.`);
  document.getElementById('verif-box-tokens').innerText = data.total_tokens;
}

function onIncidentEscalated(data) {
  alert('CRITICAL ESCALATION: ' + data.message);
  appendTimeline(`🚨 ESCALATION REQUIRED: Maximum replanning attempts exceeded. Paging human SRE.`);
}

// =============================================================================
// EVIDENCE & HYPOTHESES RENDERING
// =============================================================================

function renderEvidence(evidenceList) {
  const tbody = document.getElementById('evidence-tbody');
  const countBadge = document.getElementById('evidence-count-badge');
  if (!evidenceList || evidenceList.length === 0) {
    tbody.innerHTML = '<tr><td colspan="4" class="text-muted">No evidence collected.</td></tr>';
    countBadge.innerText = '0 Items';
    return;
  }

  countBadge.innerText = `${evidenceList.length} Items`;
  tbody.innerHTML = evidenceList.map(item => `
    <tr>
      <td><b>${item.metric_name}</b><br><small class="text-muted">${item.source}</small></td>
      <td class="font-mono">${item.value}</td>
      <td><span class="badge-${item.status.toLowerCase()}">${item.status}</span></td>
      <td><b class="${item.support_level === 'HIGH' ? 'text-neon-cyan' : ''}">${item.support_level}</b></td>
    </tr>
  `).join('');
}

function renderHypotheses(hypothesesList) {
  const container = document.getElementById('hypotheses-container');
  if (!hypothesesList || hypothesesList.length === 0) {
    container.innerHTML = '<div class="text-muted text-center py-4">No hypotheses generated.</div>';
    return;
  }

  container.innerHTML = hypothesesList.map(h => `
    <div class="hypothesis-item ${h.selected ? 'selected' : ''}">
      <div class="hyp-header">
        <span class="hyp-rank-title">#${h.rank} ${h.title}</span>
        <span class="hyp-confidence ${h.confidence >= 0.8 ? 'conf-high' : (h.confidence >= 0.3 ? 'conf-med' : 'conf-low')}">
          Confidence: ${h.confidence_percent}%
        </span>
      </div>
      <p style="font-size: 11px; color: #94a3b8; margin-bottom: 4px;">${h.description}</p>
      <div class="hyp-evidence-list">
        ${(h.supporting_evidence || []).map(e => `<span class="ev-supp">${e}</span>`).join('')}
        ${(h.contradicting_evidence || []).map(e => `<span class="ev-contra">${e}</span>`).join('')}
      </div>
    </div>
  `).join('');
}

function renderRootCause(rc) {
  if (!rc) return;
  document.getElementById('root-cause-title').innerText = rc.title;
  document.getElementById('root-cause-explanation').innerText = rc.explanation;
  document.getElementById('root-cause-confidence').innerText = `Confidence: ${rc.confidence_percent}%`;
  document.getElementById('verif-box-rc').innerText = rc.title;

  const altList = document.getElementById('alternatives-list');
  if (rc.alternatives_considered && rc.alternatives_considered.length > 0) {
    altList.innerHTML = rc.alternatives_considered.map(alt => `
      <div class="alt-item">
        <span><b>${alt.title}</b> (${alt.confidence})</span>
        <span class="text-muted">${alt.reason_rejected}</span>
      </div>
    `).join('');
  }
}

function updateActionPlanUI(plan) {
  if (!plan) return;
  document.getElementById('diff-action-name').innerText = `${plan.proposed_action}()`;
  document.getElementById('verif-box-action').innerText = plan.proposed_action;
}

// =============================================================================
// TELEMETRY & TOKEN UI UPDATES
// =============================================================================

function updateTelemetryUI(telem) {
  if (!telem) return;

  // DB Connections
  const dbVal = `${telem.db_connections}/${telem.max_db_connections}`;
  document.getElementById('telem-val-db').innerText = dbVal;
  const dbPct = Math.min(100, Math.round((telem.db_connections / telem.max_db_connections) * 100));
  const dbBar = document.getElementById('telem-bar-db');
  dbBar.style.width = `${dbPct}%`;
  dbBar.className = dbPct > 80 ? 'telem-bar-fill telem-bar-red' : 'telem-bar-fill';

  // API Error Rate
  const errVal = `${telem.api_error_rate}%`;
  document.getElementById('telem-val-err').innerText = errVal;
  const errBar = document.getElementById('telem-bar-err');
  errBar.style.width = `${Math.min(100, telem.api_error_rate)}%`;

  // Latencies
  document.getElementById('telem-val-resp').innerText = `${telem.response_time} ms`;
  document.getElementById('telem-bar-resp').style.width = `${Math.min(100, (telem.response_time / 8000) * 100)}%`;

  document.getElementById('telem-val-query').innerText = `${telem.query_latency} ms`;
  document.getElementById('telem-bar-query').style.width = `${Math.min(100, (telem.query_latency / 8000) * 100)}%`;

  // Services status
  if (telem.services) {
    const apiSvc = telem.services['api-gateway'];
    if (apiSvc) {
      document.getElementById('svc-api').innerHTML = `API Gateway: <b class="${apiSvc.status === 'HEALTHY' ? 'text-neon-green' : 'text-neon-red'}">${apiSvc.status}</b>`;
    }
    const dbSvc = telem.services['postgresql-primary'];
    if (dbSvc) {
      document.getElementById('svc-db').innerHTML = `PostgreSQL: <b class="${dbSvc.status === 'HEALTHY' ? 'text-neon-green' : 'text-neon-red'}">${dbSvc.status}</b>`;
    }
  }
  document.getElementById('svc-version-val').innerText = telem.deployment_version || 'v2.4.1';
}

function updateTokenUI(balance, totalUsed) {
  document.getElementById('header-token-bal').innerText = Number(balance).toLocaleString();
  document.getElementById('token-balance-val').innerText = Number(balance).toLocaleString();
  document.getElementById('token-consumed-val').innerText = Number(totalUsed).toLocaleString();
  document.getElementById('token-est-rem').innerText = Number(balance).toLocaleString();

  const pct = Math.max(0, Math.min(100, (balance / 10000) * 100));
  const progBar = document.getElementById('token-progress-bar');
  progBar.style.width = `${pct}%`;
  if (pct < 10) {
    progBar.style.background = 'var(--neon-red)';
  } else if (pct < 30) {
    progBar.style.background = 'var(--neon-amber)';
  }

  // Update agent breakdown if data available
  fetchTokens();
}

async function fetchTokens() {
  try {
    const res = await fetch('/api/tokens');
    const data = await res.json();
    if (data.agent_usage) {
      const au = data.agent_usage;
      setAgentBar('at-bar-obs', 'at-val-obs', au['Observability Agent'] || 0, 200);
      setAgentBar('at-bar-inv', 'at-val-inv', au['Investigation Agent'] || 0, 100);
      setAgentBar('at-bar-know', 'at-val-know', au['Knowledge Agent'] || 0, 60);
      setAgentBar('at-bar-rc', 'at-val-rc', au['Root Cause Agent'] || 0, 120);
      setAgentBar('at-bar-plan', 'at-val-plan', au['Planner Agent'] || 0, 160);
      setAgentBar('at-bar-exec', 'at-val-exec', au['Execution Agent'] || 0, 150);
      setAgentBar('at-bar-ver', 'at-val-ver', au['Verification Agent'] || 0, 100);
      setAgentBar('at-bar-post', 'at-val-post', au['Postmortem Agent'] || 0, 100);
    }
  } catch (err) {
    console.warn('Error fetching tokens:', err);
  }
}

function setAgentBar(barId, valId, val, maxExpected) {
  const bar = document.getElementById(barId);
  const text = document.getElementById(valId);
  if (bar) bar.style.width = `${Math.min(100, (val / maxExpected) * 100)}%`;
  if (text) text.innerText = val;
}

function showTokenWarning(data) {
  const box = document.getElementById('token-warning-box');
  box.style.display = 'flex';
  appendTimeline(`⚠️ TOKEN EXHAUSTED: Operation ${data.operation} requires ${data.required} tokens. Available: ${data.available}. Execution halted.`);
}

// =============================================================================
// ACTIONS: INJECT FAILURE, DEMO MODE, RESET
// =============================================================================

async function startAresDemo() {
  try {
    appendTimeline(`⚡ Launching one-click ARES hackathon demonstration...`);
    const res = await fetch('/api/demo/start', { method: 'POST' });
    const data = await res.json();
    console.log('Demo started:', data);
  } catch (err) {
    alert('Error starting demo: ' + err.message);
  }
}

async function injectFailure(scenario) {
  const simFailOnce = document.getElementById('toggle-sim-fail').checked;
  try {
    appendTimeline(`🔴 Injecting failure scenario: ${scenario}...`);
    const res = await fetch('/api/incidents/inject', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        scenario,
        simulate_verification_failure: simFailOnce
      })
    });
    const data = await res.json();
    console.log('Failure injected:', data);
  } catch (err) {
    alert('Error injecting failure: ' + err.message);
  }
}

async function resetSystem() {
  try {
    const res = await fetch('/api/system/reset', { method: 'POST' });
    const data = await res.json();
    onSystemReset(data);
    appendTimeline(`🔄 System reset to baseline HEALTHY state. Tokens restored to 10,000.`);
  } catch (err) {
    alert('Error resetting system: ' + err.message);
  }
}

function onSystemReset(data) {
  state.incidentId = null;
  state.scenario = null;
  state.currentStage = 'IDLE';
  state.status = 'HEALTHY';
  state.replanCount = 0;

  // Reset header
  const statusPill = document.getElementById('system-status-pill');
  statusPill.className = 'status-pill status-healthy';
  document.getElementById('system-status-text').innerText = 'SYSTEM HEALTHY';
  document.getElementById('header-incident-id').innerText = 'NO ACTIVE INCIDENT';
  document.getElementById('header-severity-pill').style.display = 'none';

  // Reset flowchart nodes
  STAGE_ORDER.forEach((stage, idx) => {
    const node = document.getElementById(STAGE_NODES[stage]);
    if (node) {
      node.className = 'flow-node';
      const stateEl = node.querySelector('.node-state');
      if (stateEl) stateEl.innerText = '○ Pending';
    }
    const conn = document.getElementById(`conn-${idx}`);
    if (conn) conn.className = 'flow-connector';
  });

  // Reset boxes
  document.getElementById('approval-gate-panel').style.display = 'none';
  document.getElementById('ares-verified-box').style.display = 'none';
  document.getElementById('replan-banner').style.display = 'none';
  document.getElementById('btn-view-postmortem').style.display = 'none';
  document.getElementById('token-warning-box').style.display = 'none';

  // Reset telemetry
  if (data.telemetry) updateTelemetryUI(data.telemetry);
  updateTokenUI(10000, 0);

  // Reset activity box
  updateActivityBox(
    '🧠',
    'IDLE MONITORING',
    'Cluster is healthy. Baseline monitoring active. Awaiting failure injection or anomaly trigger.',
    'All microservices reporting HTTP 200 OK',
    'Continuous background telemetry ingestion'
  );

  // Clear tables
  renderEvidence([]);
  renderHypotheses([]);
  document.getElementById('root-cause-title').innerText = 'Awaiting root cause determination...';
  document.getElementById('root-cause-explanation').innerText = 'Investigation agent will weigh evidence matrix to isolate the decisive failure mechanism.';
  document.getElementById('alternatives-list').innerHTML = '<div class="text-muted">No hypotheses evaluated yet.</div>';

  // Reset Before vs After
  document.getElementById('before-metric-db').innerText = '24 / 100';
  document.getElementById('before-metric-error').innerText = '0.2%';
  document.getElementById('before-metric-resp').innerText = '185 ms';
  document.getElementById('before-metric-latency').innerText = '180 ms';

  document.getElementById('after-metric-db').innerText = '—';
  document.getElementById('after-metric-error').innerText = '—';
  document.getElementById('after-metric-resp').innerText = '—';
  document.getElementById('after-metric-latency').innerText = '—';
  document.getElementById('diff-action-name').innerText = 'restart_database()';
  document.getElementById('recovery-status-pill').innerText = 'Baseline Monitoring';
  document.getElementById('recovery-status-pill').className = 'recovery-status-pill';
}

async function addTokens(amount = 5000) {
  try {
    const res = await fetch('/api/tokens/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ amount })
    });
    const data = await res.json();
    updateTokenUI(data.balance, data.total_used);
    document.getElementById('token-warning-box').style.display = 'none';
    appendTimeline(`⚡ Added ${amount} tokens to computation budget.`);
  } catch (err) {
    alert('Error adding tokens: ' + err.message);
  }
}

// =============================================================================
// TIMELINE HELPER
// =============================================================================

function appendTimeline(msg) {
  const container = document.getElementById('timeline-list');
  const empty = container.querySelector('.timeline-empty');
  if (empty) empty.remove();

  const now = new Date();
  const timeStr = now.toTimeString().split(' ')[0];

  const item = document.createElement('div');
  item.className = 'timeline-item';
  item.innerHTML = `
    <span class="timeline-time">${timeStr}</span>
    <span class="timeline-msg">${msg}</span>
  `;

  container.prepend(item);
}

function scrollToEvidence() {
  document.getElementById('evidence-section').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// =============================================================================
// MODALS LOGIC
// =============================================================================

async function openPostmortemModal() {
  if (!state.incidentId && !state.postmortemData) {
    alert('No completed incident postmortem available yet.');
    return;
  }

  let pm = state.postmortemData;
  if (!pm && state.incidentId) {
    try {
      const res = await fetch(`/api/incidents/${state.incidentId}/postmortem`);
      pm = await res.json();
    } catch (err) {
      console.warn('Error fetching postmortem:', err);
    }
  }

  if (!pm) {
    alert('Postmortem report not ready yet. Wait for incident resolution.');
    return;
  }

  const container = document.getElementById('postmortem-content');
  container.innerHTML = `
    <div class="pm-section">
      <div class="pm-heading">1. Incident Overview</div>
      <p><b>Incident ID:</b> ${pm.incident_id} | <b>Severity:</b> ${pm.severity} | <b>Status:</b> ${pm.final_status}</p>
      <p style="margin-top: 6px;">${pm.summary}</p>
    </div>

    <div class="pm-section">
      <div class="pm-heading">2. Root Cause Analysis</div>
      <p><b>Primary Cause:</b> ${pm.root_cause} (Confidence: ${pm.confidence_percent}%)</p>
      <p style="margin-top: 4px; color: #cbd5e1;">${pm.root_cause_details}</p>
      <p style="margin-top: 4px; font-size: 11px; color: #94a3b8;"><b>Runbook Used:</b> ${pm.runbook_used || 'DB-POOL-003'}</p>
    </div>

    <div class="pm-section">
      <div class="pm-heading">3. Remediation & Verification</div>
      <p><b>Executed Action:</b> <code>${pm.remediation_executed}</code> | <b>Risk Level:</b> ${pm.risk_assessment}</p>
      <p><b>Approval:</b> ${pm.human_approval ? pm.human_approval.approved_by || 'Human SRE' : 'Policy Gate'}</p>
      <div style="margin-top: 8px; background: rgba(0,0,0,0.3); padding: 8px; border-radius: 6px; font-family: monospace;">
        Before Error Rate: ${pm.before_metrics ? pm.before_metrics.api_error_rate : '62.4%'} → After: ${pm.after_metrics ? pm.after_metrics.api_error_rate : '0.4%'}<br>
        Before DB Connections: ${pm.before_metrics ? pm.before_metrics.db_connections : '99/100'} → After: ${pm.after_metrics ? pm.after_metrics.db_connections : '24/100'}
      </div>
    </div>

    <div class="pm-section">
      <div class="pm-heading">4. Corrective Action Items & Lessons Learned</div>
      <ul style="padding-left: 18px; color: #cbd5e1;">
        ${(pm.lessons_learned || []).map(item => `<li>${item}</li>`).join('')}
      </ul>
    </div>
  `;

  document.getElementById('modal-postmortem').style.display = 'flex';
}

function closePostmortemModal() {
  document.getElementById('modal-postmortem').style.display = 'none';
}

function downloadPostmortem(format) {
  const pm = state.postmortemData;
  if (!pm) return;

  let content = '';
  let filename = `postmortem-${pm.incident_id || 'ares'}`;
  let mimeType = 'text/plain';

  if (format === 'json') {
    content = JSON.stringify(pm, null, 2);
    filename += '.json';
    mimeType = 'application/json';
  } else {
    content = `# SRE Incident Postmortem: ${pm.title}\n\n` +
      `**Incident ID:** ${pm.incident_id}\n` +
      `**Severity:** ${pm.severity}\n` +
      `**Final Status:** ${pm.final_status}\n\n` +
      `## Summary\n${pm.summary}\n\n` +
      `## Root Cause\n**${pm.root_cause}** (Confidence: ${pm.confidence_percent}%)\n\n${pm.root_cause_details}\n\n` +
      `## Remediation Executed\nAction: \`${pm.remediation_executed}\`\nRisk: ${pm.risk_assessment}\n\n` +
      `## Corrective Actions & Lessons Learned\n` +
      (pm.lessons_learned || []).map(l => `- ${l}`).join('\n');
    filename += '.md';
    mimeType = 'text/markdown';
  }

  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

async function openTokenModal() {
  try {
    const res = await fetch('/api/tokens/transactions');
    const txs = await res.json();
    const tbody = document.getElementById('token-tx-tbody');

    if (!txs || txs.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" class="text-muted text-center py-4">No token transactions recorded yet.</td></tr>';
    } else {
      tbody.innerHTML = txs.map(tx => `
        <tr>
          <td class="font-mono text-muted">${tx.timestamp ? tx.timestamp.split('T')[1].split('.')[0] : 'N/A'}</td>
          <td><b>${tx.agent_name}</b></td>
          <td>${tx.operation}</td>
          <td class="font-mono ${tx.tokens_used > 0 ? 'text-neon-amber' : 'text-neon-green'}">${tx.tokens_used}</td>
          <td class="font-mono">${tx.tokens_remaining}</td>
          <td><span class="badge-completed">${tx.status}</span></td>
        </tr>
      `).join('');
    }
  } catch (err) {
    console.warn('Error fetching token history:', err);
  }

  document.getElementById('modal-token-history').style.display = 'flex';
}

function closeTokenModal() {
  document.getElementById('modal-token-history').style.display = 'none';
}

async function openAuditModal() {
  try {
    const res = await fetch('/api/audit-logs');
    const logs = await res.json();
    const tbody = document.getElementById('audit-tbody');

    if (!logs || logs.length === 0) {
      tbody.innerHTML = '<tr><td colspan="5" class="text-muted text-center py-4">No audit logs recorded.</td></tr>';
    } else {
      tbody.innerHTML = logs.map(l => `
        <tr>
          <td class="font-mono text-muted">${l.timestamp ? l.timestamp.split('T')[1].split('.')[0] : 'N/A'}</td>
          <td><b>${l.actor}</b></td>
          <td class="font-mono">${l.action}</td>
          <td><span class="badge-risk-${(l.risk_level || 'info').toLowerCase()}">${l.risk_level}</span></td>
          <td style="font-size: 11px; color: #cbd5e1;">${JSON.stringify(l.details || {})}</td>
        </tr>
      `).join('');
    }
  } catch (err) {
    console.warn('Error fetching audit logs:', err);
  }

  document.getElementById('modal-audit-log').style.display = 'flex';
}

function closeAuditModal() {
  document.getElementById('modal-audit-log').style.display = 'none';
}

async function fetchInitialStatus() {
  try {
    const res = await fetch('/api/system/status');
    const data = await res.json();

    if (data.telemetry) updateTelemetryUI(data.telemetry);
    if (data.tokens) updateTokenUI(data.tokens.balance, data.tokens.total_used);

    if (data.active_incident) {
      onIncidentDetected(data.active_incident);
    }
  } catch (err) {
    console.warn('Error fetching initial status:', err);
  }
}
