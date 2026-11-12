
/*
  AGENTIC X — SYNCHRONIZED ROUNDS
  Real Python Agents + Gemini + LangSmith

  Click 1: Agent explanation
  Click 2: Actual Accepted / Rejected verdict

  All four agents must finish the current round
  before Next Round becomes available.

  No mock decisions.
  No Gemini calls when clicking robots.
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
let pollTimer = null;
let pollingBusy = false;

let messages = [];
let latestResult = null;
let currentRunInputs = null;

let currentRound = 1;
let agentStages = {};
let activeAgent = null;
let resultsReady = false;


/* =========================================
   HELPERS
========================================= */

function text(id, value) {
  if ($(id)) {
    $(id).textContent = String(value);
  }
}

function bool(value) {
  return value === true ||
    value === 1 ||
    String(value).trim().toLowerCase() === "true";
}

function formatSar(value) {
  const number = Number(value);

  if (value == null || !Number.isFinite(number)) {
    return "—";
  }

  return number.toLocaleString("en-US") + " SAR";
}

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

function originalQuality(c) {
  return Number(c.required_quality_min ?? 0);
}

function originalEquipment(c) {
  return bool(c.backup_available);
}

function hasQualityControl() {
  return Boolean($("quality"));
}

function currentInputs() {
  return {
    case_id: $("scenario").value,
    budget_sar: Number($("budget").value),
    time_left_min: Number($("time").value),
    equipment_available:
      $("equipment").value === "available",

    ...(hasQualityControl()
      ? {
          minimum_quality:
            Number($("quality").value)
        }
      : {})
  };
}

function inputsMatch(a, b) {
  if (!a || !b) {
    return false;
  }

  return (
    String(a.case_id) === String(b.case_id) &&
    Number(a.budget_sar) === Number(b.budget_sar) &&
    Number(a.time_left_min) ===
      Number(b.time_left_min) &&
    bool(a.equipment_available) ===
      bool(b.equipment_available) &&
    (
      !hasQualityControl() ||
      Number(
        a.minimum_quality ??
        originalQuality(baseCase.case)
      ) === Number(b.minimum_quality)
    )
  );
}


/* =========================================
   LOCAL STORAGE
========================================= */

function readRun() {
  try {
    const stored = JSON.parse(
      localStorage.getItem(STORAGE_KEY) || "null"
    );

    if (!stored?.inputs?.case_id) {
      return null;
    }

    if (
      stored.status === "COMPLETED" &&
      Array.isArray(stored.result?.evaluations)
    ) {
      return stored;
    }

    if (
      stored.status === "RUNNING" &&
      typeof stored.job_id === "string"
    ) {
      return stored;
    }
  } catch (error) {
    console.warn("Could not read saved run", error);
  }

  return null;
}

function saveRun(value) {
  try {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify(value)
    );
  } catch (error) {
    console.warn("Could not save run", error);
  }
}

function forgetRun() {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch (_) {}
}


/* =========================================
   SYNCHRONIZED ROUND MANAGEMENT
========================================= */

function removeOldExplanation() {
  $("agentExplanationPanel")?.remove();
}

function resetReview() {
  currentRound = 1;
  activeAgent = null;

  agentStages = Object.fromEntries(
    AGENTS.map(agent => [agent, 0])
  );

  removeOldExplanation();
}

/*
  Agent stages:

  0 = Click me
  1 = Explanation visible
  2 = Verdict visible

  Every agent stays in the same currentRound.
*/

function recordedRounds() {
  if (!latestResult) {
    return [];
  }

  const fromMessages = (
    latestResult.messages || []
  )
    .filter(message =>
      message.sender === "Coordinator" &&
      message.performative === "PROPOSE"
    )
    .map(message => Number(message.round))
    .filter(Number.isInteger);

  const fromEvaluations = (
    latestResult.evaluations || []
  ).length
    ? Math.ceil(
        latestResult.evaluations.length / 4
      )
    : 0;

  const maxRound = Math.max(
    Number(latestResult.rounds) || 0,
    fromEvaluations,
    ...fromMessages,
    0
  );

  return Array.from(
    { length: maxRound },
    (_, index) => index + 1
  );
}

function evaluationsForRound(round) {
  const evaluations =
    latestResult?.evaluations || [];

  /*
    Backend records four evaluations per
    successfully evaluated round.

    Never invent missing agent results.
  */

  return evaluations.slice(
    (round - 1) * 4,
    round * 4
  );
}

function evaluationFor(
  name,
  round = currentRound
) {
  return evaluationsForRound(round)
    .find(evaluation =>
      evaluation.agent === name
    ) || null;
}

function allAgentsFinishedRound() {
  return AGENTS.every(name =>
    agentStages[name] === 2 &&
    Boolean(evaluationFor(name))
  );
}


/* =========================================
   AGENT EXPLANATIONS
========================================= */

function shortSpeech(name, evaluation) {
  let reason = String(
    evaluation.reason || ""
  )
    .replace(/\s+/g, " ")
    .trim();

  if (name === "Finance") {
    const info =
      latestResult?.finance_breakdown?.[
        evaluation.option_id
      ];

    if (info) {
      const remaining = Number(
        info.remaining_sar
      );

      return (
        `Budget ${formatSar(info.current_budget_sar)}; ` +
        `option ${formatSar(info.option_cost_sar)}. ` +
        (
          remaining >= 0
            ? `${formatSar(remaining)} remaining.`
            : `${formatSar(-remaining)} over budget.`
        )
      );
    }
  }

  if (name === "Operations") {
    const times = reason.match(
      /requires\s+([\d.]+)\s+minutes,\s+but only\s+([\d.]+)\s+minutes/i
    );

    if (times) {
      const required = Number(times[1])
        .toFixed(1)
        .replace(/\.0$/, "");

      const available = Number(times[2])
        .toFixed(1)
        .replace(/\.0$/, "");

      return (
        `Needs ${required} min; ` +
        `only ${available} min available.`
      );
    }
  }

  let first = reason.split(
    /(?<=[.!?])\s+(?=[A-Z])/
  )[0] || reason;

  const limit =
    name === "Creative" ? 102 : 145;

  if (first.length > limit) {
    first =
      first.slice(0, limit - 1).trimEnd() +
      "…";
  }

  if (name === "Creative") {
    const option = (
      baseCase?.options || []
    ).find(
      item =>
        String(item.option_id) ===
        String(evaluation.option_id)
    );

    const required =
      currentRunInputs?.minimum_quality ??
      baseCase?.case?.required_quality_min;

    if (
      option?.quality_score != null &&
      required != null
    ) {
      first +=
        ` Quality: ${Number(option.quality_score)}/100` +
        ` vs ${Number(required)}/100.`;
    }
  }

  return first || "No explanation provided.";
}


/* =========================================
   NEXT ROUND BUTTON
========================================= */

function showNextRoundControl() {
  let strip = $("roundNavigation");

  if (!strip) {
    strip = document.createElement("div");
    strip.id = "roundNavigation";

    strip.style.cssText = `
      max-width: 1100px;
      margin: 10px auto 4px;
      display: flex;
      gap: 12px;
      justify-content: center;
      align-items: center;
      flex-wrap: wrap;
      color: white;
      font-size: 13px;
    `;

    $("agents")?.after(strip);
  }

  strip.replaceChildren();

  if (!resultsReady || !latestResult) {
    return;
  }

  const rounds = recordedRounds();

  const label = document.createElement("strong");

  label.textContent =
    `Round ${currentRound} of ${rounds.length || 1}`;

  strip.append(label);

  const done = allAgentsFinishedRound();

  const hasNext =
    rounds.includes(currentRound + 1) &&
    evaluationsForRound(
      currentRound + 1
    ).length > 0;

  if (hasNext) {
    const button = document.createElement("button");

    button.type = "button";
    button.textContent = "Next Round →";

    /*
      Button stays disabled until ALL FOUR
      agents reveal their decisions.
    */

    button.disabled = !done;

    button.style.cssText = `
      border: 1px solid #c8a7ff;
      border-radius: 10px;
      color: white;
      background: #6b4c99;
      padding: 8px 16px;
      font-weight: 700;
      cursor: pointer;
    `;

    if (!done) {
      button.style.opacity = ".45";
    }

    button.title = done
      ? "Show the next recorded negotiation round"
      : "Reveal all four agent decisions first";

    button.onclick = () => {
      if (!allAgentsFinishedRound()) {
        return;
      }

      if (
        !evaluationsForRound(
          currentRound + 1
        ).length
      ) {
        return;
      }

      /*
        All agents move together.
      */

      currentRound++;

      activeAgent = null;

      agentStages = Object.fromEntries(
        AGENTS.map(name => [name, 0])
      );

      renderAgents();
    };

    strip.append(button);
  } else if (done) {
    const doneLabel =
      document.createElement("span");

    doneLabel.textContent =
      "All recorded rounds reviewed";

    doneLabel.style.color = "#d0bfea";

    strip.append(doneLabel);
  }
}


/* =========================================
   RENDER AGENTS
========================================= */

function renderAgents() {
  const root = $("agents");

  if (!root) {
    return;
  }

  removeOldExplanation();
  root.replaceChildren();

  AGENTS.forEach(name => {
    const stage = agentStages[name] || 0;

    const evaluation = resultsReady
      ? evaluationFor(name)
      : null;

    const showDecision =
      resultsReady &&
      stage === 2 &&
      Boolean(evaluation);

    const showExplanation =
      resultsReady &&
      stage === 1 &&
      Boolean(evaluation);

    const holder = document.createElement("div");

    holder.className =
      "agent " +
      (
        showDecision
          ? (
              evaluation.approved
                ? "accepted"
                : "rejected"
            )
          : "idle"
      );

    holder.style.setProperty(
      "--accent",
      COLORS[name]
    );

    if (activeAgent === name) {
      holder.classList.add("selected");
    }

    const bubble = document.createElement("div");
    bubble.className = "bubble";

    const bubbleBackground = showDecision
      ? (
          evaluation.approved
            ? "#176846"
            : "#862b50"
        )
      : "#292044";

    const bubbleBorder = showDecision
      ? (
          evaluation.approved
            ? "#70e6a5"
            : "#ff8eae"
        )
      : COLORS[name];

    bubble.style.cssText = `
      font-size: 11px !important;
      line-height: 1.2 !important;
      padding: 7px !important;
      overflow: hidden !important;
      overflow-wrap: anywhere;
      background: ${bubbleBackground} !important;
      border-color: ${bubbleBorder} !important;
      cursor: pointer;
    `;

    if (activeJob) {
      bubble.textContent = "Evaluating...";
    } else if (!resultsReady) {
      bubble.textContent = "Run a scenario first";
    } else if (!evaluation) {
      bubble.textContent = "No recorded evaluation";
    } else if (showExplanation) {
      bubble.textContent =
        shortSpeech(name, evaluation);
    } else if (showDecision) {
      bubble.textContent = evaluation.approved
        ? "✓ Accepted"
        : "✕ Rejected";
    } else {
      bubble.textContent = "Click me";
    }

    const button = document.createElement("button");

    button.type = "button";

    button.setAttribute(
      "aria-label",
      `Review ${name} Agent round ${currentRound}`
    );

    const robot = document.createElement("div");
    robot.className = "robot";

    const label = document.createElement("span");
    label.className = "name";
    label.textContent = name + " Agent";

    const state = document.createElement("div");
    state.className = "state";

    if (activeJob) {
      state.textContent = "● Processing";
    } else if (!resultsReady) {
      state.textContent = "● Idle";
    } else if (showDecision) {
      state.textContent =
        `● ${evaluation.approved ? "Accepted" : "Rejected"}` +
        ` · R${currentRound}`;
    } else if (showExplanation) {
      state.textContent =
        `● Explaining · R${currentRound}`;
    } else if (evaluation) {
      state.textContent =
        `● Click me · R${currentRound}`;
    } else {
      state.textContent = "● Unavailable";
    }

    state.style.setProperty(
      "background",
      showDecision
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

    const click = () => handleAgentClick(name);

    button.addEventListener("click", click);
    bubble.addEventListener("click", click);

    button.append(
      robot,
      label,
      state
    );

    holder.append(
      bubble,
      button
    );

    root.append(holder);
  });

  showNextRoundControl();
}


/* =========================================
   AGENT CLICK LOGIC
========================================= */

function handleAgentClick(name) {
  if (
    activeJob ||
    !resultsReady ||
    !latestResult
  ) {
    return;
  }

  const evaluation = evaluationFor(name);

  if (!evaluation) {
    return;
  }

  activeAgent = name;

  if (agentStages[name] === 0) {
    // First click: explanation
    agentStages[name] = 1;
  } else if (agentStages[name] === 1) {
    // Second click: actual verdict
    agentStages[name] = 2;
  }

  /*
    Additional clicks do nothing.

    An individual agent cannot advance
    to Round 2 alone.
  */

  renderAgents();
}


/* =========================================
   NEGOTIATION LOG
========================================= */

function renderLog() {
  const root = $("log");

  if (!root) {
    return;
  }

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
    sender.textContent = message.sender || "";

    const info = document.createElement("span");

    info.textContent =
      `${message.receiver} · ` +
      `${message.performative} · ` +
      `R${message.round}`;

    const content = document.createElement("span");
    content.className = "msg";

    content.textContent = message.content || "";

    row.append(
      number,
      sender,
      info,
      content
    );

    root.append(row);
  });
}


/* =========================================
   INPUT CONTROLS
========================================= */

function updateChanged() {
  if (!baseCase) {
    return;
  }

  const original = {
    case_id: baseCase.case.case_id,
    budget_sar: originalBudget(baseCase.case),
    time_left_min: originalTime(baseCase.case),
    equipment_available:
      originalEquipment(baseCase.case),
    minimum_quality:
      originalQuality(baseCase.case)
  };

  text(
    "changeIndicator",
    inputsMatch(original, currentInputs())
      ? "Original dataset values"
      : "Modified test conditions"
  );
}

function controls() {
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

  updateChanged();

  /*
    Old results must not be presented as
    results for changed test conditions.
  */

  if (
    resultsReady &&
    currentRunInputs &&
    !inputsMatch(
      currentRunInputs,
      currentInputs()
    )
  ) {
    resultsReady = false;
    latestResult = null;
    messages = [];

    resetReview();

    text(
      "status",
      "Inputs changed — run again"
    );

    text(
      "explanation",
      "Run to evaluate the new inputs."
    );

    [
      "solution",
      "cost",
      "duration",
      "safety"
    ].forEach(id => text(id, "—"));

    renderAgents();
    renderLog();
  }
}

function resetOriginal() {
  if (!baseCase || activeJob) {
    return;
  }

  $("budget").value =
    originalBudget(baseCase.case);

  $("time").value =
    originalTime(baseCase.case);

  $("equipment").value =
    originalEquipment(baseCase.case)
      ? "available"
      : "unavailable";

  if (hasQualityControl()) {
    $("quality").value =
      originalQuality(baseCase.case);
  }

  controls();
}


/* =========================================
   SCENARIO OPTIONS
========================================= */

function renderCaseOptions(options) {
  const root = $("scenarioOptions");

  root.replaceChildren();

  (options || []).forEach(option => {
    const card = document.createElement("div");
    card.className = "scenario-option";

    const title = document.createElement("strong");

    title.textContent =
      `${option.option_id || ""} · ` +
      `${option.option_name || ""}`;

    const facts = document.createElement("span");
    facts.className = "option-facts";

    facts.textContent =
      `Cost: ${formatSar(option.cost_sar)} · ` +
      `Duration: ${option.duration_min ?? "—"} min · ` +
      `Quality: ${option.quality_score ?? "—"}`;

    const backup = document.createElement("span");
    backup.className = "option-backup";

    backup.textContent =
      `Backup Equipment: ` +
      (
        bool(option.needs_backup)
          ? "Required"
          : "Not required"
      );

    card.append(
      title,
      facts,
      backup
    );

    root.append(card);
  });
}

function showScenario() {
  text(
    "scenarioTitle",
    $("scenarioType").value
  );

  text(
    "scenarioDescription",
    baseCase?.case?.incident ||
      "Loading scenario data..."
  );
}


/* =========================================
   FINAL DECISION
========================================= */

function showDecision(result) {
  const agreed = result.status === "AGREED";

  text("status", result.status);

  $("status").className =
    agreed ? "decision" : "";

  text(
    "explanation",
    `${result.reason} · ` +
    `${result.rounds} round(s) · ` +
    `${(result.evaluations || []).length} evaluations`
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
      ? formatSar(
          result.selected_option.cost_sar
        )
      : "—"
  );

  text(
    "duration",
    result.selected_option?.duration_min != null
      ? result.selected_option.duration_min +
        " minutes"
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


/* =========================================
   DISPLAY COMPLETED RUN
========================================= */

function displayCompletedRun(
  result,
  save = true
) {
  if (!Array.isArray(result?.evaluations)) {
    throw Error(
      "Invalid server evaluation result"
    );
  }

  latestResult = result;
  messages = result.messages || [];

  activeJob = null;
  resultsReady = true;

  resetReview();
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


/* =========================================
   JOB POLLING
========================================= */

function stopPolling() {
  if (pollTimer !== null) {
    clearInterval(pollTimer);
  }

  pollTimer = null;
}

async function pollJob(jobId) {
  if (pollingBusy) {
    return;
  }

  pollingBusy = true;

  try {
    const response = await fetch(
      "/api/job/" + encodeURIComponent(jobId),
      { cache: "no-store" }
    );

    const job = await response.json();

    if (!response.ok) {
      throw Error(
        job.detail || `HTTP ${response.status}`
      );
    }

    if (activeJob !== jobId) {
      return;
    }

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
        job.error || "See Python backend logs."
      );

      $("run").disabled = false;

      renderAgents();
      renderLog();
      return;
    }

    text(
      "status",
      "Running real agents"
    );

    text(
      "explanation",
      job.current_option
        ? `Evaluating ${job.current_option}...`
        : "Starting real evaluations..."
    );

    renderAgents();
  } catch (error) {
    stopPolling();

    activeJob = null;
    $("run").disabled = false;

    text("status", "CONNECTION ERROR");
    text("explanation", error.message);

    renderAgents();
  } finally {
    pollingBusy = false;
  }
}

async function startPolling(jobId) {
  await pollJob(jobId);

  if (
    activeJob === jobId &&
    pollTimer === null
  ) {
    pollTimer = setInterval(
      () => pollJob(jobId),
      1500
    );
  }
}


/* =========================================
   RUN REAL AGENTS
========================================= */

async function run() {
  if (activeJob || !baseCase) {
    return;
  }

  const inputs = currentInputs();

  const invalid =
    !Number.isFinite(inputs.budget_sar) ||
    !Number.isFinite(inputs.time_left_min) ||
    (
      hasQualityControl() &&
      (
        !Number.isFinite(
          inputs.minimum_quality
        ) ||
        inputs.minimum_quality < 0 ||
        inputs.minimum_quality > 100
      )
    );

  if (invalid) {
    text(
      "explanation",
      "Enter valid Budget, Time and Minimum Quality values."
    );

    return;
  }

  stopPolling();
  resetReview();

  resultsReady = false;
  latestResult = null;
  messages = [];

  $("run").disabled = true;

  text("status", "Starting run");

  text(
    "explanation",
    "Sending the scenario to real Python agents..."
  );

  renderAgents();
  renderLog();

  try {
    const response = await fetch(
      "/api/start",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify(inputs)
      }
    );

    const job = await response.json();

    if (!response.ok) {
      throw Error(
        typeof job.detail === "string"
          ? job.detail
          : JSON.stringify(job.detail || job)
      );
    }

    currentRunInputs = inputs;
    activeJob = job.job_id;

    saveRun({
      status: "RUNNING",
      job_id: activeJob,
      inputs
    });

    await startPolling(activeJob);
  } catch (error) {
    activeJob = null;

    $("run").disabled = false;

    text("status", "RUN FAILED");
    text("explanation", error.message);

    renderAgents();
  }
}


/* =========================================
   RESET
========================================= */

function reset(clearSaved = false) {
  if (clearSaved) {
    forgetRun();
    currentRunInputs = null;
  }

  stopPolling();

  activeJob = null;
  resultsReady = false;
  latestResult = null;
  messages = [];

  resetReview();

  $("run").disabled = !baseCase;

  text(
    "status",
    "Awaiting Simulation"
  );

  text(
    "explanation",
    "Run the selected case using the real Python agents."
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


/* =========================================
   LOAD SCENARIOS
========================================= */

async function selectCase() {
  if (activeJob) {
    return;
  }

  const request = ++caseRequestSerial;
  const id = $("scenario").value;

  baseCase = null;
  $("run").disabled = true;

  text(
    "scenarioOriginal",
    "Loading case details..."
  );

  try {
    const response = await fetch(
      "/api/case/" + encodeURIComponent(id),
      { cache: "no-store" }
    );

    if (!response.ok) {
      throw Error(`Cannot load ${id}`);
    }

    const data = await response.json();

    if (request !== caseRequestSerial) {
      return;
    }

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
      } · ` +
      `Minimum quality: ${originalQuality(c)}/100`
    );

    renderCaseOptions(data.options);

    reset(false);
    resetOriginal();
    showScenario();

    restoreSavedRunForCase();
  } catch (error) {
    if (request !== caseRequestSerial) {
      return;
    }

    text("status", "DATA ERROR");
    text("explanation", error.message);

    $("run").disabled = true;
  }
}

async function selectType() {
  if (activeJob) {
    return;
  }

  const type = $("scenarioType").value;

  const records = (
    scenarioGroups.find(
      group => group.type === type
    )?.cases || []
  );

  const select = $("scenario");
  select.replaceChildren();

  for (const c of records) {
    const option = document.createElement("option");

    option.value = c.case_id;
    option.textContent = c.case_id;

    select.append(option);
  }

  if (!records.length) {
    text(
      "catalogNotice",
      "No cases found."
    );

    $("catalogNotice").style.display = "block";
    $("run").disabled = true;

    return;
  }

  $("catalogNotice").style.display = "none";

  await selectCase();
}


/* =========================================
   INITIAL CATALOG
========================================= */

async function initCatalog() {
  try {
    const response = await fetch(
      "/api/scenarios",
      { cache: "no-store" }
    );

    if (!response.ok) {
      throw Error(
        "Scenario catalog unavailable"
      );
    }

    scenarioGroups = await response.json();

    const saved = readRun();

    const group = saved &&
      scenarioGroups.find(group =>
        (group.cases || []).some(
          c =>
            c.case_id ===
            saved.inputs.case_id
        )
      );

    if (group) {
      $("scenarioType").value = group.type;
    }

    await selectType();

    if (
      saved &&
      [...$("scenario").options].some(
        option =>
          option.value === saved.inputs.case_id
      ) &&
      $("scenario").value !== saved.inputs.case_id
    ) {
      $("scenario").value =
        saved.inputs.case_id;

      await selectCase();
    }
  } catch (error) {
    text("status", "CATALOG ERROR");
    text("explanation", error.message);

    $("run").disabled = true;
  }
}


/* =========================================
   RESTORE SAVED RESULT
========================================= */

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

  $("budget").value =
    saved.inputs.budget_sar;

  $("time").value =
    saved.inputs.time_left_min;

  $("equipment").value =
    bool(saved.inputs.equipment_available)
      ? "available"
      : "unavailable";

  if (hasQualityControl()) {
    $("quality").value =
      saved.inputs.minimum_quality ??
      originalQuality(baseCase.case);
  }

  currentRunInputs = {
    ...saved.inputs,

    ...(hasQualityControl()
      ? {
          minimum_quality:
            Number($("quality").value)
        }
      : {})
  };

  controls();

  if (saved.status === "COMPLETED") {
    displayCompletedRun(
      saved.result,
      false
    );
  } else if (saved.status === "RUNNING") {
    activeJob = saved.job_id;

    $("run").disabled = true;

    text(
      "status",
      "Resuming previous run"
    );

    text(
      "explanation",
      "Checking previous job without starting Gemini again."
    );

    renderAgents();
    startPolling(saved.job_id);
  }
}


/* =========================================
   EVENTS
========================================= */

$("run").addEventListener(
  "click",
  run
);

$("reset").addEventListener(
  "click",
  () => reset(true)
);

[
  "budget",
  "time",
  "equipment",
  "quality"
].forEach(id => {
  if ($(id)) {
    $(id).addEventListener(
      "input",
      controls
    );
  }
});

$("resetOriginal").addEventListener(
  "click",
  resetOriginal
);

$("scenario").addEventListener(
  "change",
  selectCase
);

$("scenarioType").addEventListener(
  "change",
  selectType
);


/* =========================================
   INITIALIZATION
========================================= */

reset(false);
controls();
initCatalog();

