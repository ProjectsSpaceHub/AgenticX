
/* Agentic X — Persistent Real Evaluations */

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
  'Screen Failure': 'Screen Failure',
  'Budget Overrun': 'Budget Overrun',
  'Safety Conflict': 'Safety Conflict'
};

const STORAGE_KEY = 'agenticx:latest-real-job:v2';

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
let currentRunInputs = null;

function text(id, value) {
  const element = $(id);
  if (element) element.textContent = String(value);
}

function formatSar(value) {
  if (value == null || !Number.isFinite(Number(value))) {
    return '—';
  }

  return Number(value).toLocaleString('en-US') + ' SAR';
}

function compactReason(value) {
  const clean = String(value || '')
    .replace(/\s+/g, ' ')
    .trim();

  return clean.length > 132
    ? clean.slice(0, 129).trimEnd() + '…'
    : clean;
}

function actualBoolean(value) {
  return value === true ||
    value === 1 ||
    String(value).trim().toLowerCase() === 'true';
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
  }

  revealTimer = null;
}

function clearExplanation() {
  $('agentExplanationPanel')?.remove();
}

function clearInteraction() {
  clearRevealTimer();
  selectedAgent = null;
  decisionRevealed = false;
  clearExplanation();
}

// Save the real evaluation locally in this browser.
function saveRun(record) {
  try {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify(record)
    );
  } catch (error) {
    console.warn('Could not save last run:', error);
  }
}

function readRun() {
  try {
    const record = JSON.parse(
      localStorage.getItem(STORAGE_KEY) || 'null'
    );

    if (!record?.inputs?.case_id) {
      return null;
    }

    if (
      record.status === 'COMPLETED' &&
      Array.isArray(record.result?.evaluations)
    ) {
      return record;
    }

    if (
      record.status === 'RUNNING' &&
      typeof record.job_id === 'string'
    ) {
      return record;
    }

  } catch (error) {
    console.warn('Could not read last run:', error);
  }

  return null;
}

function forgetRun() {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch (_) {}
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

  heading.style.cssText =
    'display:block;margin-bottom:8px';

  const reason = document.createElement('p');

  reason.textContent =
    evaluation.reason || 'No explanation provided.';

  reason.style.margin = '0';

  const verdict = document.createElement('div');
  verdict.id = 'agentExplanationVerdict';

  verdict.style.cssText =
    'margin-top:12px;font-weight:bold';

  verdict.textContent = 'Reviewing explanation...';

  panel.append(heading, reason, verdict);
}

function revealExplanationVerdict(evaluation) {
  const verdict = $('agentExplanationVerdict');

  if (!verdict) return;

  verdict.textContent = evaluation.approved
    ? '✓ Decision: Accepted'
    : '✕ Decision: Rejected';

  verdict.style.color = evaluation.approved
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
      : 'Run a scenario to see recorded ACL negotiation.';

    log.append(empty);
    return;
  }

  messages.forEach((message, index) => {
    log.append(safeMessageElement(message, index));
  });
}

// Agents stay neutral until clicked.
function renderAgents() {
  const root = $('agents');
  root.replaceChildren();

  agentNames.forEach(name => {
    const holder = document.createElement('div');
    holder.className = 'agent';

    const isSelected = selectedAgent === name;

    const reveal =
      isSelected &&
      decisionRevealed &&
      replayReady &&
      (
        agentsState[name] === 'Accepted' ||
        agentsState[name] === 'Rejected'
      );

    if (isSelected) {
      holder.classList.add('selected');
    }

    holder.classList.add(
      reveal
        ? agentsState[name].toLowerCase()
        : 'idle'
    );

    const bubble = document.createElement('div');
    bubble.className = 'bubble';

    if (
      isSelected &&
      replayReady &&
      agentSpeech[name]
    ) {
      bubble.textContent = agentSpeech[name];
      bubble.title = agentSpeech[name];

    } else if (replayReady) {
      bubble.textContent =
        'Click to view explanation';

    } else if (activeJob) {
      bubble.textContent = 'Evaluating...';

    } else {
      bubble.textContent = 'Run a scenario first';
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

    if (reveal) {
      state.textContent =
        `● ${agentsState[name]} · ` +
        (agentRoundLabel[name] || '');

      state.style.background =
        agentsState[name] === 'Accepted'
          ? '#146845'
          : '#852b4b';

      state.style.color = '#fff';

    } else if (isSelected && replayReady) {
      state.textContent = '● Explaining...';

    } else if (replayReady) {
      state.textContent = '● Decision hidden';

    } else if (activeJob) {
      state.textContent = '● Processing';

    } else {
      state.textContent = '● Idle';
    }

    if (!reveal) {
      state.style.background = '#493765';
      state.style.color = '#fff';
    }

    button.append(robot, label, state);

    button.addEventListener('click', () => {
      handleAgentClick(name);
    });

    holder.append(bubble, button);
    root.append(holder);
  });
}

function originalBudget(c) {
  return Number(
    c.initial_budget_sar ?? c.budget_sar ?? 0
  );
}

function originalTime(c) {
  return Number(c.time_left_min ?? 0);
}

function originalEquipment(c) {
  return actualBoolean(c.backup_available);
}

function updateChanged() {
  if (!baseCase) return;

  const c = baseCase.case;

  const altered =
    Number($('budget').value) !== originalBudget(c) ||
    Number($('time').value) !== originalTime(c) ||
    ($('equipment').value === 'available') !==
      originalEquipment(c);

  text(
    'changeIndicator',
    altered
      ? 'Modified test conditions'
      : 'Original dataset values'
  );
}

function controls() {
  updateChanged();

  text(
    'budgetOut',
    formatSar($('budget').value)
  );

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

function resetOriginal() {
  if (!baseCase || activeJob) return;

  const c = baseCase.case;

  $('budget').value = originalBudget(c);
  $('time').value = originalTime(c);

  $('equipment').value =
    originalEquipment(c)
      ? 'available'
      : 'unavailable';

  controls();
}

function renderCaseOptions(options) {
  const root = $('scenarioOptions');
  root.replaceChildren();

  (options || []).forEach(o => {
    const card = document.createElement('div');
    card.className = 'scenario-option';

    const heading = document.createElement('strong');

    heading.textContent =
      `${o.option_id || ''} · ${o.option_name || ''}`;

    const facts = document.createElement('span');
    facts.className = 'option-facts';

    facts.textContent =
      `Cost: ${formatSar(o.cost_sar)} · ` +
      `Duration: ${o.duration_min ?? '—'} min · ` +
      `Quality: ${o.quality_score ?? '—'}`;

    const backup = document.createElement('span');
    backup.className = 'option-backup';

    backup.textContent =
      'Backup Equipment: ' +
      (
        actualBoolean(o.needs_backup)
          ? 'Required'
          : 'Not required'
      );

    card.append(heading, facts, backup);
    root.append(card);
  });
}

function showScenario() {
  const type = $('scenarioType').value;

  text(
    'scenarioTitle',
    scenarioMeta[type] || type
  );

  text(
    'scenarioDescription',
    baseCase?.case?.incident ||
    'Loading scenario data…'
  );
}

function evaluationsFor(name) {
  return (latestResult?.evaluations || [])
    .filter(e => e.agent === name);
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

  text('status', result.status);

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

// Display a real completed evaluation.
function displayCompletedRun(result, shouldSave = true) {
  if (!Array.isArray(result?.evaluations)) {
    throw Error('Invalid recorded evaluation result');
  }

  messages = result.messages || [];
  latestResult = result;
  replayReady = true;

  resetStatuses();
  clearInteraction();

  agentNames.forEach(name => {
    const evaluations = evaluationsFor(name);

    if (!evaluations.length) return;

    const last = evaluations[evaluations.length - 1];

    agentsState[name] =
      last.approved ? 'Accepted' : 'Rejected';

    agentRoundLabel[name] =
      `R${evaluations.length} · ${last.option_id}`;

    agentSpeech[name] =
      name === 'Finance'
        ? financeSummary(last)
        : compactReason(last.reason);
  });

  showDecision(result);

  $('run').disabled = false;
  renderAgents();
  renderLog();

  if (shouldSave && currentRunInputs) {
    saveRun({
      status: 'COMPLETED',
      inputs: currentRunInputs,
      result
    });
  }
}

// Restore results after refreshing the page.
function restoreSavedRunForCase() {
  const saved = readRun();

  if (
    !saved ||
    !baseCase ||
    saved.inputs.case_id !== baseCase.case.case_id
  ) {
    return;
  }

  currentRunInputs = saved.inputs;

  $('budget').value = saved.inputs.budget_sar;
  $('time').value = saved.inputs.time_left_min;

  $('equipment').value =
    saved.inputs.equipment_available
      ? 'available'
      : 'unavailable';

  controls();

  if (saved.status === 'COMPLETED') {
    displayCompletedRun(saved.result, false);

  } else if (saved.status === 'RUNNING') {
    activeJob = saved.job_id;
    $('run').disabled = true;

    text('status', 'Resuming previous run');

    text(
      'explanation',
      'Checking previous real evaluation without calling Gemini again.'
    );

    renderAgents();

    pollJob(saved.job_id).then(() => {
      if (
        activeJob === saved.job_id &&
        !polling
      ) {
        polling = setInterval(
          () => pollJob(saved.job_id),
          1500
        );
      }
    });
  }
}

function reset(clearSaved = false) {
  if (clearSaved) {
    forgetRun();
    currentRunInputs = null;
  }

  stopPolling();
  clearInteraction();

  activeJob = null;
  messages = [];
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

async function selectCase() {
  if (activeJob) return;

  const serial = ++caseRequestSerial;
  const id = $('scenario').value;

  baseCase = null;

  text(
    'scenarioOriginal',
    'Loading case details…'
  );

  text(
    'scenarioDescription',
    'Loading case data…'
  );

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

    const c = data.case;

    text(
      'scenarioOriginal',
      `Case ${c.case_id} · ` +
      `Budget: ${formatSar(originalBudget(c))} · ` +
      `Time: ${originalTime(c)} min · ` +
      `Equipment: ${
        originalEquipment(c)
          ? 'Available'
          : 'Unavailable'
      } · ` +
      `Minimum quality: ${
        c.required_quality_min ?? '—'
      }/100`
    );

    renderCaseOptions(data.options);

    reset();
    resetOriginal();
    showScenario();

    restoreSavedRunForCase();

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
    scenarioGroups.find(g => g.type === type)?.cases || [];

  const select = $('scenario');
  select.replaceChildren();

  records.forEach(c => {
    const option = document.createElement('option');

    option.value = c.case_id;
    option.textContent = c.case_id;

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

    const saved = readRun();

    if (saved) {
      const match = scenarioGroups.find(g =>
        (g.cases || []).some(
          c => c.case_id === saved.inputs.case_id
        )
      );

      if (match) {
        $('scenarioType').value = match.type;
      }
    }

    await selectType();

    if (
      saved &&
      [...$('scenario').options].some(
        o => o.value === saved.inputs.case_id
      ) &&
      $('scenario').value !== saved.inputs.case_id
    ) {
      $('scenario').value = saved.inputs.case_id;
      await selectCase();
    }

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

function stopPolling() {
  if (polling !== null) {
    clearInterval(polling);
  }

  polling = null;
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

      displayCompletedRun(job.result);
      return;
    }

    if (job.status === 'ERROR') {
      stopPolling();
      activeJob = null;
      forgetRun();

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

    if (job.status !== 'RUNNING') {
      throw Error('Unexpected job status');
    }

    agentNames.forEach(name => {
      if (job.agent_status?.[name]) {
        agentsState[name] =
          job.agent_status[name];
      }
    });

    text('status', 'Running real agents');

    text(
      'explanation',
      job.current_option
        ? `Evaluating ${job.current_option}. Gemini responses may take time.`
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
  clearInteraction();
  resetStatuses();

  messages = [];
  latestResult = null;
  replayReady = false;

  $('run').disabled = true;

  text('status', 'Starting run');

  text(
    'explanation',
    'Sending scenario to the real Python multi-agent system...'
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

    currentRunInputs = body;
    activeJob = job.job_id;

    saveRun({
      status: 'RUNNING',
      job_id: activeJob,
      inputs: body
    });

    await pollJob(activeJob);

    if (activeJob && !polling) {
      polling = setInterval(
        () => pollJob(activeJob),
        1500
      );
    }

  } catch (error) {
    activeJob = null;

    text('status', 'RUN FAILED');
    text('explanation', error.message);

    $('run').disabled = false;
  }
}

// Show explanation first, then the real decision and color.
function handleAgentClick(name) {
  if (
    activeJob ||
    !replayReady ||
    !latestResult
  ) {
    return;
  }

  clearRevealTimer();

  if (selectedAgent === name) {
    clearInteraction();
    renderAgents();
    return;
  }

  const evaluations = evaluationsFor(name);

  if (!evaluations.length) {
    clearInteraction();

    text(
      'explanation',
      `No recorded evaluation for ${name} in this run.`
    );

    renderAgents();
    return;
  }

  selectedAgent = name;
  decisionRevealed = false;
  clearExplanation();

  const index = agentClickProgress[name] || 0;
  const safeIndex = index % evaluations.length;

  const evaluation = evaluations[safeIndex];

  agentSpeech[name] =
    name === 'Finance'
      ? financeSummary(evaluation)
      : compactReason(evaluation.reason);

  agentRoundLabel[name] =
    `R${safeIndex + 1} · ${evaluation.option_id}`;

  agentClickProgress[name] = index + 1;

  showFullExplanation(
    name,
    evaluation,
    safeIndex + 1
  );

  renderAgents();

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

$('run').addEventListener('click', run);

$('reset').addEventListener(
  'click',
  () => reset(true)
);

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


