
/*
  AGENTIC X — COMPLETE FRONTEND
  Real Python agents + Gemini + LangSmith

  Click 1: Short explanation inside bubble
  Click 2: Actual verdict and color
  Click 3: Close / prepare next round

  No fake evaluations.
  No additional Gemini calls when clicking agents.
*/

const $ = id => document.getElementById(id);

const AGENTS = [
  "Creative",
  "Finance",
  "Operations",
  "Safety"
];

const COLORS = {
  Creative: "#d4a2ff",
  Finance: "#ffd099",
  Operations: "#99d1ff",
  Safety: "#a2f2b0"
};

const STORAGE_KEY = "agenticx:latest-real-job:v3";

let scenarioGroups = [];
let baseCase = null;
let caseRequestSerial = 0;

let activeJob = null;
let polling = null;
let pollingBusy = false;

let latestResult = null;
let messages = [];
let currentRunInputs = null;

let replayReady = false;
let selectedAgent = null;

let agentStages = {};
let agentIndexes = {};

let currentStatus = {};


/* ---------- HELPERS ---------- */

function text(id, value) {
  const element = $(id);

  if (element) {
    element.textContent = String(value);
  }
}

function formatSar(value) {
  const n = Number(value);

  if (
    value === null ||
    value === undefined ||
    !Number.isFinite(n)
  ) {
    return "—";
  }

  return n.toLocaleString("en-US") + " SAR";
}

function bool(value) {
  return (
    value === true ||
    value === 1 ||
    String(value).trim().toLowerCase() === "true"
  );
}

function resetAgentInteraction() {
  selectedAgent = null;
  agentStages = {};
  agentIndexes = {};

  currentStatus = Object.fromEntries(
    AGENTS.map(name => [name, "Idle"])
  );

  // Remove explanation panels from older versions.
  $("agentExplanationPanel")?.remove();
}

function saveRun(record) {
  try {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify(record)
    );
  } catch (error) {
    console.warn("Result storage unavailable:", error);
  }
}

function readRun() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);

    if (!raw) return null;

    const record = JSON.parse(raw);

    if (!record?.inputs?.case_id) {
      return null;
    }

    if (
      record.status === "COMPLETED" &&
      Array.isArray(record.result?.evaluations)
    ) {
      return record;
    }

    if (
      record.status === "RUNNING" &&
      record.job_id
    ) {
      return record;
    }

  } catch (error) {
    console.warn("Stored result error:", error);
  }

  return null;
}

function forgetRun() {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch (_) {}
}


/* ---------- SHORT REAL EXPLANATIONS ---------- */

function financeSummary(evaluation) {
  const info =
    latestResult?.finance_breakdown?.[
      evaluation.option_id
    ];

  if (!info) {
    return String(evaluation.reason || "");
  }

  const remaining = Number(info.remaining_sar);

  return (
    `Budget ${formatSar(info.current_budget_sar)}. ` +
    `Cost ${formatSar(info.option_cost_sar)}. ` +
    (
      remaining >= 0
        ? `Remaining ${formatSar(remaining)}.`
        : `Over budget by ${formatSar(-remaining)}.`
    )
  );
}

function shortAgentSpeech(name, evaluation) {
  if (name === "Finance") {
    return financeSummary(evaluation);
  }

  const reason = String(
    evaluation.reason || ""
  ).replace(/\s+/g, " ").trim();

  // Keep the reasoning from the real recorded agent.
  const sentences = reason.split(
    /(?<=[.!?])\s+(?=[A-Z])/
  );

  let summary = sentences.slice(0, 2).join(" ");

  if (summary.length > 175) {
    summary =
      summary.slice(0, 172).trimEnd() + "…";
  }

  // Creative must display the verified quality comparison.
  if (name === "Creative") {
    const option = (baseCase?.options || []).find(
      o => String(o.option_id) ===
        String(evaluation.option_id)
    );

    const quality = option?.quality_score;

    const minimum =
      baseCase?.case?.required_quality_min;

    if (
      quality !== null &&
      quality !== undefined &&
      minimum !== null &&
      minimum !== undefined
    ) {
      summary =
        summary.slice(0, 125).trimEnd() +
        ` Quality: ${quality}/100 vs ${minimum}/100.`;
    }
  }

  return summary || "No explanation provided.";
}


/* ---------- AGENT EVALUATIONS ---------- */

function evaluationsFor(name) {
  return (
    latestResult?.evaluations || []
  ).filter(e => e.agent === name);
}

function selectedEvaluation(name) {
  const evaluations = evaluationsFor(name);

  if (!evaluations.length) {
    return null;
  }

  const index =
    (agentIndexes[name] || 0) % evaluations.length;

  return {
    evaluation: evaluations[index],
    round: index + 1
  };
}


/* ---------- AGENT DISPLAY ---------- */

function renderAgents() {
  const root = $("agents");

  if (!root) return;

  root.replaceChildren();

  AGENTS.forEach(name => {
    const stage = agentStages[name] || 0;

    const selected = selectedAgent === name;

    const current = selectedEvaluation(name);

    const evaluation = current?.evaluation;

    const explaining =
      replayReady &&
      selected &&
      stage === 1 &&
      evaluation;

    const revealing =
      replayReady &&
      selected &&
      stage === 2 &&
      evaluation;

    const holder = document.createElement("div");

    holder.className = "agent";

    if (selected) {
      holder.classList.add("selected");
    }

    // Neutral until the second click.
    if (revealing) {
      holder.classList.add(
        evaluation.approved ? "accepted" : "rejected"
      );
    } else {
      holder.classList.add("idle");
    }

    holder.style.setProperty(
      "--accent",
      COLORS[name]
    );

    const bubble = document.createElement("div");
    bubble.className = "bubble";

    bubble.style.setProperty(
      "font-size",
      "13px",
      "important"
    );

    bubble.style.setProperty(
      "line-height",
      "1.35",
      "important"
    );

    bubble.style.setProperty(
      "padding",
      "12px",
      "important"
    );

    if (!replayReady) {
      bubble.textContent = activeJob
        ? "Evaluating..."
        : "Run a scenario first";

    } else if (explaining) {
      bubble.textContent =
        shortAgentSpeech(name, evaluation);

    } else if (revealing) {
      bubble.textContent = evaluation.approved
        ? "✓ Accepted"
        : "✕ Rejected";

    } else {
      bubble.textContent = "Click me";
    }

    // Override old green styles from index.html.
    bubble.style.setProperty(
      "background",
      revealing
        ? (
            evaluation.approved
              ? "#176846"
              : "#862b50"
          )
        : "#292044",
      "important"
    );

    bubble.style.setProperty(
      "border-color",
      revealing
        ? (
            evaluation.approved
              ? "#70e6a5"
              : "#ff8eae"
          )
        : COLORS[name],
      "important"
    );

    bubble.style.setProperty(
      "box-shadow",
      revealing
        ? (
            evaluation.approved
              ? "0 0 18px #37e27744"
              : "0 0 18px #f2517a44"
          )
        : "0 0 12px #c995ff25",
      "important"
    );

    bubble.style.setProperty(
      "overflow",
      "hidden",
      "important"
    );

    bubble.style.setProperty(
      "overflow-wrap",
      "anywhere",
      "important"
    );

    const button = document.createElement("button");

    button.type = "button";

    button.setAttribute(
      "aria-label",
      `${name} Agent`
    );

    const robot = document.createElement("div");
    robot.className = "robot";

    const label = document.createElement("span");
    label.className = "name";
    label.textContent = `${name} Agent`;

    const state = document.createElement("div");
    state.className = "state";

    if (revealing) {
      state.textContent =
        `● ${
          evaluation.approved
            ? "Accepted"
            : "Rejected"
        } · R${current.round} · ` +
        evaluation.option_id;

    } else if (explaining) {
      state.textContent = "● Explaining";

    } else if (activeJob) {
      state.textContent = "● Processing";

    } else if (replayReady) {
      state.textContent = "● Click me";

    } else {
      state.textContent = "● Idle";
    }

    state.style.setProperty(
      "background",
      revealing
        ? (
            evaluation.approved
              ? "#176846"
              : "#862b50"
          )
        : "#493765",
      "important"
    );

    state.style.setProperty(
      "color",
      "#ffffff",
      "important"
    );

    button.append(robot, label, state);

    button.addEventListener(
      "click",
      () => handleAgentClick(name)
    );

    // Bubble is clickable too.
    bubble.style.cursor = "pointer";

    bubble.addEventListener(
      "click",
      () => handleAgentClick(name)
    );

    holder.append(bubble, button);

    root.append(holder);
  });
}


/* ---------- TWO-CLICK INTERACTION ---------- */

function handleAgentClick(name) {
  if (
    activeJob ||
    !replayReady ||
    !latestResult
  ) {
    return;
  }

  const evaluations = evaluationsFor(name);

  if (!evaluations.length) {
    return;
  }

  // Switching agent starts its explanation.
  if (selectedAgent !== name) {
    selectedAgent = name;

    agentStages = {
      [name]: 1
    };

  } else if (agentStages[name] === 1) {
    // Second click reveals the actual decision.
    agentStages[name] = 2;

  } else {
    // Third click closes this agent.
    selectedAgent = null;
    agentStages = {};

    // Next time, show next recorded round if present.
    agentIndexes[name] =
      (
        (agentIndexes[name] || 0) + 1
      ) % evaluations.length;
  }

  renderAgents();
}


/* ---------- ACL NEGOTIATION LOG ---------- */

function renderLog() {
  const root = $("log");

  if (!root) return;

  root.replaceChildren();

  if (!messages.length) {
    const empty = document.createElement("div");
    empty.className = "empty";

    empty.textContent = activeJob
      ? "Running real agents..."
      : "Run a scenario to see the negotiation log.";

    root.append(empty);
    return;
  }

  messages.forEach((message, index) => {
    const row = document.createElement("div");
    row.className = "row";

    row.style.setProperty(
      "--c",
      COLORS[message.sender] || "#ded0ff"
    );

    const number = document.createElement("span");

    number.textContent =
      String(index + 1).padStart(2, "0");

    const sender = document.createElement("strong");
    sender.textContent = message.sender;

    const details = document.createElement("span");

    details.textContent =
      `${message.receiver} · ` +
      `${message.performative} · R${message.round}`;

    const content = document.createElement("span");
    content.className = "msg";
    content.textContent = message.content;

    row.append(number, sender, details, content);

    root.append(row);
  });
}


/* ---------- ORIGINAL DATASET VALUES ---------- */

function originalBudget(c) {
  return Number(
    c.initial_budget_sar ??
    c.budget_sar ??
    0
  );
}

function originalTime(c) {
  return Number(c.time_left_min ?? 0);
}

function originalEquipment(c) {
  return bool(c.backup_available);
}

function updateChanged() {
  if (!baseCase) return;

  const c = baseCase.case;

  const changed =
    Number($("budget").value) !== originalBudget(c) ||
    Number($("time").value) !== originalTime(c) ||
    ($("equipment").value === "available") !==
      originalEquipment(c);

  text(
    "changeIndicator",
    changed
      ? "Modified test conditions"
      : "Original dataset values"
  );
}

function controls() {
  updateChanged();

  text(
    "budgetOut",
    formatSar($("budget").value)
  );

  text(
    "timeOut",
    $("time").value + " minutes"
  );

  text(
    "equipmentOut",
    $("equipment").value === "available"
      ? "Available"
      : "Unavailable"
  );
}

function resetOriginal() {
  if (!baseCase || activeJob) return;

  const c = baseCase.case;

  $("budget").value = originalBudget(c);

  $("time").value = originalTime(c);

  $("equipment").value =
    originalEquipment(c)
      ? "available"
      : "unavailable";

  controls();
}


/* ---------- OPTIONS DISPLAY ---------- */

function renderCaseOptions(options) {
  const root = $("scenarioOptions");

  root.replaceChildren();

  (options || []).forEach(option => {
    const card = document.createElement("div");

    card.className = "scenario-option";

    const heading = document.createElement("strong");

    heading.textContent =
      `${option.option_id} · ${option.option_name}`;

    const facts = document.createElement("span");

    facts.className = "option-facts";

    facts.textContent =
      `Cost: ${formatSar(option.cost_sar)} · ` +
      `Duration: ${option.duration_min} min · ` +
      `Quality: ${option.quality_score}`;

    const backup = document.createElement("span");

    backup.className = "option-backup";

    backup.textContent =
      "Backup Equipment: " +
      (
        bool(option.needs_backup)
          ? "Required"
          : "Not required"
      );

    card.append(heading, facts, backup);

    root.append(card);
  });
}

function showScenario() {
  const type = $("scenarioType").value;

  text("scenarioTitle", type);

  text(
    "scenarioDescription",
    baseCase?.case?.incident ||
    "Loading scenario data..."
  );
}


/* ---------- FINAL DECISION ---------- */

function showDecision(result) {
  latestResult = result;

  const agreed = result.status === "AGREED";

  text("status", result.status);

  $("status").className =
    agreed ? "decision" : "";

  text(
    "explanation",
    `${result.reason} · ` +
    `${result.rounds} round(s) · ` +
    `${result.evaluations.length} evaluations`
  );

  text(
    "solution",
    result.selected_option_name ||
    result.selected_option_id ||
    "No approved solution — human escalation"
  );

  text(
    "cost",
    result.selected_option?.cost_sar != null
      ? formatSar(result.selected_option.cost_sar)
      : "—"
  );

  text(
    "duration",
    result.selected_option?.duration_min != null
      ? result.selected_option.duration_min + " minutes"
      : "—"
  );

  text(
    "safety",
    agreed
      ? "Approved by Safety Agent"
      : "No approved final solution"
  );

  showScenario();
}


/* ---------- STORE COMPLETED RESULTS ---------- */

function displayCompletedRun(result, save = true) {
  if (!Array.isArray(result?.evaluations)) {
    throw Error("Invalid agent evaluation data");
  }

  latestResult = result;
  messages = result.messages || [];

  replayReady = true;
  activeJob = null;

  resetAgentInteraction();

  AGENTS.forEach(name => {
    const evaluations = evaluationsFor(name);

    if (!evaluations.length) return;

    const last = evaluations[evaluations.length - 1];

    currentStatus[name] =
      last.approved ? "Accepted" : "Rejected";
  });

  showDecision(result);

  $("run").disabled = false;

  renderAgents();
  renderLog();

  if (save && currentRunInputs) {
    saveRun({
      status: "COMPLETED",
      inputs: currentRunInputs,
      result
    });
  }
}


/* ---------- RESTORE SAVED RESULTS ---------- */

function restoreSavedRunForCase() {
  const saved = readRun();

  if (
    !saved ||
    !baseCase ||
    saved.inputs.case_id !==
      baseCase.case.case_id
  ) {
    return;
  }

  currentRunInputs = saved.inputs;

  $("budget").value =
    saved.inputs.budget_sar;

  $("time").value =
    saved.inputs.time_left_min;

  $("equipment").value =
    saved.inputs.equipment_available
      ? "available"
      : "unavailable";

  controls();

  if (saved.status === "COMPLETED") {
    displayCompletedRun(saved.result, false);

  } else if (saved.status === "RUNNING") {
    activeJob = saved.job_id;

    $("run").disabled = true;

    text("status", "Resuming previous run");

    text(
      "explanation",
      "Retrieving recorded evaluation without starting Gemini again."
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


/* ---------- LOAD CASES ---------- */

async function selectCase() {
  if (activeJob) return;

  const serial = ++caseRequestSerial;

  const id = $("scenario").value;

  baseCase = null;

  $("run").disabled = true;

  text("scenarioOriginal", "Loading case details...");

  try {
    const response = await fetch(
      "/api/case/" + encodeURIComponent(id),
      { cache: "no-store" }
    );

    if (!response.ok) {
      throw Error("Could not load case data");
    }

    const data = await response.json();

    if (serial !== caseRequestSerial) return;

    baseCase = data;

    const c = data.case;

    text(
      "scenarioOriginal",
      `Case ${c.case_id} · ` +
      `Budget: ${formatSar(originalBudget(c))} · ` +
      `Time: ${originalTime(c)} min · ` +
      `Equipment: ${
        originalEquipment(c)
          ? "Available"
          : "Unavailable"
      } · Minimum quality: ` +
      `${c.required_quality_min ?? "—"}/100`
    );

    renderCaseOptions(data.options);

    reset();

    resetOriginal();

    showScenario();

    restoreSavedRunForCase();

  } catch (error) {
    if (serial !== caseRequestSerial) return;

    text("status", "DATA ERROR");

    text("explanation", error.message);

    $("run").disabled = true;
  }
}

async function selectType() {
  const type = $("scenarioType").value;

  const records =
    scenarioGroups.find(g => g.type === type)
      ?.cases || [];

  const select = $("scenario");

  select.replaceChildren();

  records.forEach(record => {
    const option = document.createElement("option");

    option.value = record.case_id;

    option.textContent = record.case_id;

    select.append(option);
  });

  if (records.length) {
    $("catalogNotice").style.display = "none";

    await selectCase();

  } else {
    $("catalogNotice").textContent =
      "No cases available.";

    $("catalogNotice").style.display = "block";

    $("run").disabled = true;
  }
}

async function initCatalog() {
  try {
    const response = await fetch(
      "/api/scenarios",
      { cache: "no-store" }
    );

    if (!response.ok) {
      throw Error("Catalog unavailable");
    }

    scenarioGroups = await response.json();

    const saved = readRun();

    if (saved) {
      const matching = scenarioGroups.find(group =>
        (group.cases || []).some(
          c => c.case_id === saved.inputs.case_id
        )
      );

      if (matching) {
        $("scenarioType").value = matching.type;
      }
    }

    await selectType();

    if (saved) {
      const exists = [
        ...$("scenario").options
      ].some(
        o => o.value === saved.inputs.case_id
      );

      if (
        exists &&
        $("scenario").value !== saved.inputs.case_id
      ) {
        $("scenario").value =
          saved.inputs.case_id;

        await selectCase();
      }
    }

  } catch (error) {
    text("status", "CATALOG ERROR");

    text("explanation", error.message);

    $("run").disabled = true;
  }
}


/* ---------- POLL PYTHON BACKEND ---------- */

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
      "/api/job/" + encodeURIComponent(jobId),
      { cache: "no-store" }
    );

    const job = await response.json();

    if (!response.ok) {
      throw Error(job.detail || "Polling failed");
    }

    if (activeJob !== jobId) return;

    if (job.status === "COMPLETED") {
      stopPolling();

      displayCompletedRun(job.result);
      return;
    }

    if (job.status === "ERROR") {
      stopPolling();

      activeJob = null;

      forgetRun();

      text("status", "EXECUTION ERROR");

      text(
        "explanation",
        job.error || "Check Python backend logs"
      );

      $("run").disabled = false;

      renderAgents();
      return;
    }

    if (job.status !== "RUNNING") {
      throw Error("Unexpected job status");
    }

    AGENTS.forEach(name => {
      if (job.agent_status?.[name]) {
        currentStatus[name] =
          job.agent_status[name];
      }
    });

    text("status", "Running real agents");

    text(
      "explanation",
      job.current_option
        ? `Evaluating ${job.current_option}...`
        : "Starting agent evaluations..."
    );

    renderAgents();

  } catch (error) {
    stopPolling();

    activeJob = null;

    text("status", "CONNECTION ERROR");

    text("explanation", error.message);

    $("run").disabled = false;

  } finally {
    pollingBusy = false;
  }
}


/* ---------- START REAL SIMULATION ---------- */

async function run() {
  if (activeJob || !baseCase) return;

  stopPolling();

  resetAgentInteraction();

  messages = [];

  latestResult = null;

  replayReady = false;

  $("run").disabled = true;

  text("status", "Starting run");

  text(
    "explanation",
    "Sending scenario to the real Python agents..."
  );

  renderAgents();
  renderLog();

  const body = {
    case_id: $("scenario").value,

    budget_sar:
      Number($("budget").value),

    time_left_min:
      Number($("time").value),

    equipment_available:
      $("equipment").value === "available"
  };

  try {
    const response = await fetch("/api/start", {
      method: "POST",

      headers: {
        "Content-Type": "application/json"
      },

      body: JSON.stringify(body)
    });

    const job = await response.json();

    if (!response.ok) {
      throw Error(job.detail || "Run failed");
    }

    currentRunInputs = body;

    activeJob = job.job_id;

    saveRun({
      status: "RUNNING",
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

    text("status", "RUN FAILED");

    text("explanation", error.message);

    $("run").disabled = false;
  }
}


/* ---------- RESET ---------- */

function reset(clearSaved = false) {
  if (clearSaved) {
    forgetRun();
    currentRunInputs = null;
  }

  stopPolling();

  activeJob = null;

  messages = [];

  latestResult = null;

  replayReady = false;

  resetAgentInteraction();

  $("run").disabled = !baseCase;

  text("status", "Awaiting Simulation");

  text(
    "explanation",
    "Run a scenario using the real Python backend."
  );

  [
    "solution",
    "cost",
    "duration",
    "safety"
  ].forEach(id => text(id, "—"));

  renderAgents();
  renderLog();
  showScenario();
}


/* ---------- EVENTS ---------- */

$("run").addEventListener("click", run);

$("reset").addEventListener(
  "click",
  () => reset(true)
);

["budget", "time", "equipment"].forEach(id => {
  $(id).addEventListener("input", controls);
});

$("scenario").addEventListener(
  "change",
  selectCase
);

$("scenarioType").addEventListener(
  "change",
  selectType
);

$("resetOriginal").addEventListener(
  "click",
  resetOriginal
);


/* ---------- INITIALIZATION ---------- */

resetAgentInteraction();
reset();
controls();
initCatalog();
