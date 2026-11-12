
/* Agentic X — Interactive Multi-Agent Frontend */

const $ = id => document.getElementById(id);

const agentNames = [
  'Creative', 'Finance', 'Operations', 'Safety'
];

const agentColors = {
  Creative: '#d4a2ff',
  Finance: '#ffd099',
  Operations: '#99d1ff',
  Safety: '#a2f2b0'
};

const scenarioMeta = {
  'Screen Failure': {
    title: 'Screen Failure', impact: 'High'
  },
  'Budget Overrun': {
    title: 'Budget Overrun', impact: 'High'
  },
  'Safety Conflict': {
    title: 'Safety Conflict', impact: 'Critical'
  }
};

let scenarioGroups = [];
let baseCase = null;
let caseRequestSerial = 0;
let activeJob = null;
let polling = null;
let pollingBusy = false;
let messages = [];
let agentsState = {};
let latestResult = null;
let selectedAgent = null;
let agentSpeech = {};
let replayReady = false;
let agentRoundLabel = {};
let agentClickProgress = {};
let decisionRevealed = false;
let revealTimer = null;

function text(id, value) {
  const element = $(id);
  if (element) element.textContent = String(value);
}

function resetStatuses() {
  agentsState = Object.fromEntries(
    agentNames.map(name => [name, 'Idle'])
  );

  agentSpeech = {};
  agentRoundLabel = {};
  agentClickProgress = {};
}

function clearRevealTimer() {
  if (revealTimer !== null) {
    clearTimeout(revealTimer);
    revealTimer = null;
  }
}

function compactReason(value) {
  const clean = String(value || '')
    .replace(/\s+/g, ' ')
    .trim();

  return clean.length > 135
    ? clean.slice(0, 132).trimEnd() + '…'
    : clean;
}

function formatSar(value) {
  if (value === null || value === undefined) {
    return '—';
  }

  const number = Number(value);

  if (!Number.isFinite(number)) {
    return '—';
  }

  return number.toLocaleString('en-US') + ' SAR';
}

function clearExplanation() {
  const panel = $('agentExplanationPanel');
  if (panel) panel.remove();
}

function showFullExplanation(name, evaluation, round) {
  let panel = $('agentExplanationPanel');

  if (!panel) {
    panel = document.createElement('section');
    panel.id = 'agentExplanationPanel';

    panel.style.cssText = `
      max-width: 1100px;
      margin: 14px auto;
      padding: 16px 20px;
      background: #292044;
      border: 1px solid #bba0e5;
      border-radius: 16px;
      color: white;
      line-height: 1.7;
      font-size: 14px;
      overflow-wrap: anywhere;
    `;

    $('agents').after(panel);
  }

  panel.replaceChildren();

  const heading = document.createElement('strong');
  heading.textContent =
    `${name} Agent — Round ${round} — ${evaluation.option_id}`;

  heading.style.display = 'block';
  heading.style.marginBottom = '8px';

  const paragraph = document.createElement('p');
  paragraph.textContent =
    evaluation.reason || 'No explanation provided.';

  paragraph.style.margin = '0';

  const verdict = document.createElement('div');
  verdict.id = 'agentExplanationVerdict';
  verdict.style.cssText = `
    margin-top: 12px;
    font-weight: bold;
  `;

  verdict.textContent = 'Reviewing explanation...';

  panel.append(heading, paragraph, verdict);
}

function revealExplanationVerdict(evaluation) {
  const verdict = $('agentExplanationVerdict');

  if (!verdict) return;

  const accepted = Boolean(evaluation.approved);

  verdict.textContent = accepted
    ? '✓ Decision: Accepted'
    : '✕ Decision: Rejected';

  verdict.style.color = accepted
    ? '#82edaa'
    : '#ff9aaa';
}

function safeMessageElement(message, index) {
  const row = document.createElement('div');
  row.className = 'row';

  row.style.setProperty(
    '--c',
    agentColors[message.sender] || '#ded0ff'
  );

  const number = document.createElement('span');
  number.textContent =
    String(index + 1).padStart(2, '0');

  const sender = document.createElement('strong');
  sender.textContent = message.sender;

  const details = document.createElement('span');
  details.textContent =
    `${message.receiver} · ` +
    `${message.performative} · R${message.round}`;

  const content = document.createElement('span');
  content.className = 'msg';
  content.textContent = message.content;

  row.append(number, sender, details, content);

  return row;
}

function renderLog() {
  const log = $('log');
  log.replaceChildren();

  if (!messages.length) {
    const empty = document.createElement('div');
    empty.className = 'empty';

    empty.textContent = activeJob
      ? 'Running real agents...'
      : 'Run a scenario to see the recorded ACL negotiation.';

    log.append(empty);
    return;
  }

  messages.forEach((message, index) => {
    log.append(safeMessageElement(message, index));
  });
}

/*
  Decision reveal:
  Before clicking: neutral appearance, no result.
  On clicking: explanation appears first.
  Shortly after: actual Accepted/Rejected and color appear.
*/
function renderAgents() {
  const root = $('agents');
  root.replaceChildren();

  agentNames.forEach(name => {
    const holder = document.createElement('div');
    holder.className = 'agent';

    const isSelected = selectedAgent === name;
    const showDecision =
      isSelected && decisionRevealed && replayReady;

    if (isSelected) {
      holder.classList.add('selected');
    }

    // Keep every agent neutral until its verdict is revealed.
    if (showDecision) {
      holder.classList.add(
        (agentsState[name] || 'Idle').toLowerCase()
      );
    } else {
      holder.classList.add('idle');
    }

    const bubble = document.createElement('div');
    bubble.className = 'bubble';

    if (isSelected && replayReady && agentSpeech[name]) {
      bubble.textContent = agentSpeech[name];
      bubble.title = agentSpeech[name];

    } else if (replayReady) {
      bubble.textContent = 'Click to view explanation';
      bubble.title = '';

    } else if (activeJob) {
      bubble.textContent = 'Evaluating...';
      bubble.title = '';

    } else {
      bubble.textContent = 'Ready to evaluate.';
      bubble.title = '';
    }

    const button = document.createElement('button');
    button.type = 'button';

    button.setAttribute(
      'aria-label',
      `Select ${name} Agent`
    );

    const robot = document.createElement('div');
    robot.className = 'robot';

    const label = document.createElement('span');
    label.className = 'name';
    label.textContent = `${name} Agent`;

    const state = document.createElement('div');
    state.className = 'state';

    if (showDecision) {
      const status = agentsState[name];

      state.textContent =
        `● ${status}` +
        (
          agentRoundLabel[name]
            ? ` · ${agentRoundLabel[name]}`
            : ''
        );

      state.style.color =
        status === 'Accepted'
          ? '#d8ffe8'
          : '#ffe1e6';

      state.style.background =
        status === 'Accepted'
          ? '#146845'
          : '#852b4b';

    } else if (isSelected && replayReady) {
      state.textContent = '● Explaining...';
      state.style.background = '#493765';
      state.style.color = '#ffffff';

    } else if (replayReady) {
      state.textContent = '● Decision hidden';
      state.style.background = '#493765';
      state.style.color = '#ffffff';

    } else if (activeJob) {
      state.textContent = '● Processing';
      state.style.background = '#493765';
      state.style.color = '#ffffff';

    } else {
      state.textContent = '● Idle';
      state.style.background = '#493765';
      state.style.color = '#ffffff';
    }

    button.append(robot, label, state);

    button.addEventListener('click', () => {
      handleAgentClick(name);
    });

    holder.append(bubble, button);
    root.append(holder);
  });
}

function controls() {
  updateChanged();

  text('budgetOut', formatSar($('budget').value));

  text(
    'timeOut',
    $('time').value + ' minutes'
  );

  text(
    'equipmentOut',
    $('equipment').value === 'available'
      ? 'Available'
      : 'Unavailable'
  );
}

function originalBudget(caseData) {
  return Number(
    caseData.initial_budget_sar ??
    caseData.budget_sar ??
    0
  );
}

function originalTime(caseData) {
  return Number(caseData.time_left_min ?? 0);
}

function originalEquipment(caseData) {
  const value = caseData.backup_available;

  return (
    value === true ||
    value === 1 ||
    String(value).toLowerCase() === 'true'
  );
}

function renderCaseOptions(options) {
  const container = $('scenarioOptions');
  container.replaceChildren();

  (options || []).forEach(option => {
    const card = document.createElement('div');
    card.className = 'scenario-option';

    const heading = document.createElement('strong');
    heading.textContent =
      `${option.option_id || ''} · ` +
      `${option.option_name || ''}`;

    const facts = document.createElement('span');
    facts.className = 'option-facts';

    facts.textContent =
      `Cost: ${formatSar(option.cost_sar)} · ` +
      `Duration: ${option.duration_min ?? '—'} min · ` +
      `Quality: ${option.quality_score ?? '—'}`;

    const backup = document.createElement('span');
    backup.className = 'option-backup';

    const needsBackup =
      option.needs_backup === true ||
      option.needs_backup === 1 ||
      String(option.needs_backup).toLowerCase() === 'true';

    backup.textContent =
      'Backup Equipment: ' +
      (needsBackup ? 'Required' : 'Not required');

    card.append(heading, facts, backup);
    container.append(card);
  });
}

function showScenario() {
  const caseData = baseCase?.case;
  const type = $('scenarioType').value;

  text(
    'scenarioTitle',
    scenarioMeta[type]?.title || type
  );

  text(
    'scenarioDescription',
    caseData?.incident || 'Loading scenario data…'
  );
}

function updateChanged() {
  if (!baseCase) return;

  const caseData = baseCase.case;

  const altered =
    Number($('budget').value) !== originalBudget(caseData) ||
    Number($('time').value) !== originalTime(caseData) ||
    ($('equipment').value === 'available') !==
      originalEquipment(caseData);

  text(
    'changeIndicator',
    altered
      ? 'Modified test conditions'
      : 'Original dataset values'
  );
}

function resetOriginal() {
  if (!baseCase || activeJob) return;

  const caseData = baseCase.case;

  $('budget').value = originalBudget(caseData);
  $('time').value = originalTime(caseData);

  $('equipment').value =
    originalEquipment(caseData)
      ? 'available'
      : 'unavailable';

  controls();
  updateChanged();
}

async function selectCase() {
  if (activeJob) return;

  const serial = ++caseRequestSerial;
  const id = $('scenario').value;

  baseCase = null;

  text('scenarioOriginal', 'Loading case details…');
  text('scenarioDescription', 'Loading case data…');

  $('run').disabled = true;

  try {
    const response = await fetch(
      '/api/case/' + encodeURIComponent(id),
      { cache: 'no-store' }
    );

    if (!response.ok) {
      throw Error('Could not load case data');
    }

    const data = await response.json();

    if (serial !== caseRequestSerial) return;

    baseCase = data;
    const caseData = data.case;

    text(
      'scenarioOriginal',
      `Case ${caseData.case_id} · ` +
      `Budget: ${formatSar(originalBudget(caseData))} · ` +
      `Time: ${originalTime(caseData)} min · ` +
      `Equipment: ${
        originalEquipment(caseData)
          ? 'Available'
          : 'Unavailable'
      } · ` +
      `Minimum quality: ${
        caseData.required_quality_min ?? '—'
      }/100`
    );

    renderCaseOptions(data.options);
    resetOriginal();
    reset();
    showScenario();

  } catch (error) {
    if (serial !== caseRequestSerial) return;

    text(
      'scenarioOriginal',
      'Could not load case data: ' + error.message
    );

    text('status', 'DATA ERROR');
    text('explanation', error.message);

    $('run').disabled = true;
  }
}

async function selectType() {
  const type = $('scenarioType').value;

  const records =
    scenarioGroups.find(group => group.type === type)
      ?.cases || [];

  const select = $('scenario');
  select.replaceChildren();

  records.forEach(record => {
    const option = document.createElement('option');

    option.value = record.case_id;
    option.textContent = record.case_id;

    select.append(option);
  });

  if (records.length) {
    $('catalogNotice').style.display = 'none';
    await selectCase();

  } else {
    $('catalogNotice').textContent =
      'No cases found for this scenario.';

    $('catalogNotice').style.display = 'block';
    $('run').disabled = true;
  }
}

async function initCatalog() {
  try {
    const response = await fetch(
      '/api/scenarios',
      { cache: 'no-store' }
    );

    if (!response.ok) {
      throw Error('Catalog unavailable');
    }

    scenarioGroups = await response.json();
    await selectType();

  } catch (error) {
    text(
      'scenarioOriginal',
      'Case catalog error: ' + error.message
    );

    $('catalogNotice').textContent =
      'Cannot load cases from Python API.';

    $('catalogNotice').style.display = 'block';
    $('run').disabled = true;
  }
}

function evaluationsFor(name) {
  return (latestResult?.evaluations || [])
    .filter(evaluation => evaluation.agent === name);
}

function financeSummary(evaluation) {
  const info =
    latestResult?.finance_breakdown?.[evaluation.option_id];

  if (!info) {
    return compactReason(evaluation.reason);
  }

  const remaining = Number(info.remaining_sar);

  const balance = remaining >= 0
    ? `Remaining: ${formatSar(remaining)}`
    : `Over budget: ${formatSar(-remaining)}`;

  return (
    `Budget: ${formatSar(info.current_budget_sar)} · ` +
    `Cost: ${formatSar(info.option_cost_sar)} · ` +
    balance
  );
}

function showDecision(result) {
  latestResult = result;

  const agreed = result.status === 'AGREED';

  text(
    'status',
    agreed ? 'AGREED' : result.status
  );

  $('status').className =
    agreed ? 'decision' : '';

  text(
    'explanation',
    `${result.reason} · ` +
    `${result.rounds} round(s) · ` +
    `${result.evaluations.length} evaluations`
  );

  text(
    'solution',
    result.selected_option_name ||
    result.selected_option_id ||
    'No approved solution — human escalation'
  );

  text(
    'cost',
    result.selected_option?.cost_sar != null
      ? formatSar(result.selected_option.cost_sar)
      : '—'
  );

  text(
    'duration',
    result.selected_option?.duration_min != null
      ? result.selected_option.duration_min + ' minutes'
      : '—'
  );

  text(
    'safety',
    agreed
      ? 'Approved by Safety Agent'
      : 'No approved final solution'
  );

  showScenario();
}

function stopPolling() {
  if (polling) {
    clearInterval(polling);
    polling = null;
  }
}

async function pollJob(jobId) {
  if (pollingBusy) return;
  pollingBusy = true;

  try {
    const response = await fetch(
      '/api/job/' + encodeURIComponent(jobId),
      { cache: 'no-store' }
    );

    const job = await response.json();

    if (!response.ok) {
      throw Error(job.detail || 'Polling failed');
    }

    if (activeJob !== jobId) return;

    if (job.status === 'COMPLETED') {
      stopPolling();
      activeJob = null;

      messages = job.result.messages || [];
      latestResult = job.result;
      replayReady = true;

      resetStatuses();
      selectedAgent = null;
      decisionRevealed = false;
      clearRevealTimer();
      clearExplanation();

      agentNames.forEach(name => {
        const evaluations = evaluationsFor(name);

        if (!evaluations.length) {
          agentsState[name] = 'Idle';
          agentSpeech[name] = 'No evaluation recorded.';
          return;
        }

        const last =
          evaluations[evaluations.length - 1];

        // Save actual verdict internally.
        // Do not show it before a robot is clicked.
        agentsState[name] =
          last.approved ? 'Accepted' : 'Rejected';

        agentRoundLabel[name] =
          `R${evaluations.length} · ${last.option_id}`;

        agentSpeech[name] =
          name === 'Finance'
            ? financeSummary(last)
            : compactReason(last.reason);
      });

      showDecision(job.result);

      $('run').disabled = false;

      renderAgents();
      renderLog();
      return;
    }

    if (job.status === 'ERROR') {
      stopPolling();
      activeJob = null;

      text('status', 'EXECUTION ERROR');

      text(
        'explanation',
        job.error || 'See Python backend logs.'
      );

      $('run').disabled = false;
      renderAgents();
      renderLog();
      return;
    }

    agentNames.forEach(name => {
      const status = job.agent_status?.[name];

      if (status) {
        agentsState[name] = status;
      }
    });

    const current = job.current_option;

    text('status', 'Running real agents');

    text(
      'explanation',
      current
        ? `Evaluating ${current}. Gemini responses may take time.`
        : 'Starting agent evaluations...'
    );

    renderAgents();

  } catch (error) {
    stopPolling();
    activeJob = null;

    text('status', 'CONNECTION ERROR');
    text('explanation', error.message);

    $('run').disabled = false;
    renderAgents();

  } finally {
    pollingBusy = false;
  }
}

async function run() {
  if (activeJob || !baseCase) return;

  stopPolling();
  clearRevealTimer();
  clearExplanation();
  resetStatuses();

  decisionRevealed = false;
  selectedAgent = null;
  messages = [];
  latestResult = null;
  replayReady = false;

  $('run').disabled = true;

  text('status', 'Starting run');

  text(
    'explanation',
    'Sending the scenario to the real Python agents...'
  );

  renderAgents();
  renderLog();

  const body = {
    case_id: $('scenario').value,
    budget_sar: Number($('budget').value),
    time_left_min: Number($('time').value),
    equipment_available:
      $('equipment').value === 'available'
  };

  try {
    const response = await fetch('/api/start', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(body)
    });

    const job = await response.json();

    if (!response.ok) {
      throw Error(job.detail || 'Run rejected');
    }

    activeJob = job.job_id;

    await pollJob(activeJob);

    if (activeJob) {
      polling = setInterval(() => {
        if (activeJob) pollJob(activeJob);
      }, 1500);
    }

  } catch (error) {
    activeJob = null;

    text('status', 'RUN FAILED');
    text('explanation', error.message);

    $('run').disabled = false;
  }
}

/*
  Click behavior:
  1. Show actual reasoning first.
  2. Wait briefly.
  3. Reveal actual Accepted/Rejected and color.
  4. Opening another agent hides the previous verdict.
*/
function handleAgentClick(name) {
  if (activeJob || !replayReady || !latestResult) {
    return;
  }

  clearRevealTimer();

  if (selectedAgent === name) {
    selectedAgent = null;
    decisionRevealed = false;
    clearExplanation();
    renderAgents();
    return;
  }

  selectedAgent = name;
  decisionRevealed = false;
  clearExplanation();

  const evaluations = evaluationsFor(name);

  if (!evaluations.length) {
    agentSpeech[name] = 'No evaluation recorded.';
    renderAgents();
    return;
  }

  const index =
    (agentClickProgress[name] || 0) %
    evaluations.length;

  const evaluation = evaluations[index];

  // Store the real verdict but keep it visually hidden.
  agentsState[name] =
    evaluation.approved ? 'Accepted' : 'Rejected';

  agentRoundLabel[name] =
    `R${index + 1} · ${evaluation.option_id}`;

  agentSpeech[name] =
    name === 'Finance'
      ? financeSummary(evaluation)
      : compactReason(evaluation.reason);

  // Show the full explanation first.
  showFullExplanation(name, evaluation, index + 1);

  agentClickProgress[name] = index + 1;

  renderAgents();

  // Reveal verdict and color after the explanation.
  revealTimer = setTimeout(() => {
    if (
      selectedAgent !== name ||
      activeJob ||
      !replayReady
    ) {
      return;
    }

    decisionRevealed = true;

    revealExplanationVerdict(evaluation);
    renderAgents();

    revealTimer = null;
  }, 1200);
}

function reset() {
  clearRevealTimer();
  stopPolling();
  clearExplanation();

  decisionRevealed = false;
  activeJob = null;
  messages = [];
  selectedAgent = null;
  latestResult = null;
  replayReady = false;

  resetStatuses();

  $('run').disabled = !baseCase;

  text('status', 'Awaiting Simulation');

  text(
    'explanation',
    'Run a real scenario using the Python backend.'
  );

  [
    'solution', 'cost', 'duration', 'safety'
  ].forEach(id => text(id, '—'));

  renderAgents();
  renderLog();
  showScenario();
}

$('run').addEventListener('click', run);
$('reset').addEventListener('click', reset);

['budget', 'time', 'equipment'].forEach(id => {
  $(id).addEventListener('input', controls);
});

$('scenario').addEventListener(
  'change',
  selectCase
);

$('scenarioType').addEventListener(
  'change',
  selectType
);

$('resetOriginal').addEventListener(
  'click',
  resetOriginal
);

resetStatuses();
reset();
controls();
initCatalog();

