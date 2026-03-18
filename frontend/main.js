import { fetchRun, startRun } from "./api.js";
import { STEP_SEQUENCE, createGraphController } from "./graph.js";

const MAX_FILE_SIZE = 2 * 1024 * 1024;
const ACCEPTED_EXTENSIONS = [".txt", ".md"];
const ACCEPTED_TYPES = ["text/plain", "text/markdown", "text/x-markdown"];

const STEP_COPY = {
  extract: {
    kicker: "Graph in motion",
    title: "Extracting action items",
    body: "Pulling clear tasks, owners, and signals out of the transcript.",
    pill: "Processing",
  },
  resolve: {
    kicker: "Matching context",
    title: "Resolving owners",
    body: "Aligning names with the team roster and tightening the handoff.",
    pill: "Processing",
  },
  review: {
    kicker: "Human checkpoint",
    title: "Holding at review",
    body: "Representing the approval step as a clean pause in the graph.",
    pill: "Review",
  },
  route: {
    kicker: "Routing work",
    title: "Routing downstream tools",
    body: "Deciding which parts of the run should touch Jira, GitHub, and Slack.",
    pill: "Processing",
  },
  jira: {
    kicker: "Writing system of record",
    title: "Creating Jira tickets",
    body: "Stamping each approved item into the durable work stream.",
    pill: "Processing",
  },
  github: {
    kicker: "Engineering path",
    title: "Creating GitHub branches",
    body: "Spinning out the engineering lane so code work can move immediately.",
    pill: "Processing",
  },
  slack: {
    kicker: "Delivery loop",
    title: "Sending Slack updates",
    body: "Packaging the outcome for the channel that closes the loop.",
    pill: "Processing",
  },
};

const state = {
  status: "idle",
  dragActive: false,
  file: null,
  runId: null,
  error: null,
  retryable: false,
  currentStepId: null,
  failureStepId: null,
  stepStates: createEmptyStepStates(),
  loopClosed: false,
  summary: null,
};

const timers = [];
const stage = document.querySelector("#stage");

let currentView = null;
let graphController = null;

render();

function createEmptyStepStates() {
  return Object.fromEntries(STEP_SEQUENCE.map((step) => [step.id, "pending"]));
}

function clearTimers() {
  while (timers.length) {
    window.clearTimeout(timers.pop());
  }
}

function wait(delay, callback) {
  const timer = window.setTimeout(callback, delay);
  timers.push(timer);
}

function resetState() {
  clearTimers();
  state.status = "idle";
  state.dragActive = false;
  state.file = null;
  state.runId = null;
  state.error = null;
  state.retryable = false;
  state.currentStepId = null;
  state.failureStepId = null;
  state.stepStates = createEmptyStepStates();
  state.loopClosed = false;
  state.summary = null;
  currentView = null;
  graphController = null;
  render();
}

function setStatus(nextStatus, patch = {}) {
  Object.assign(state, patch);
  state.status = nextStatus;
  render();
}

function render() {
  const nextView = getView(state.status);
  if (nextView !== currentView) {
    currentView = nextView;
    stage.innerHTML = viewMarkup(nextView);
    bindView(nextView);
  }

  updateView(nextView);
}

function getView(status) {
  if (status === "idle") {
    return "idle";
  }
  if (status === "validating" || status === "spinning") {
    return "loading";
  }
  return "run";
}

function viewMarkup(view) {
  if (view === "idle") {
    return `
      <div class="drop-surface">
        <label class="dropzone ${state.dragActive ? "is-active" : ""}" id="dropzone">
          <input id="file-input" class="sr-only" type="file" accept=".txt,.md,text/plain,text/markdown" />
          <div class="dropzone__glass">
            <span class="dropzone__eyebrow">Transcript intake</span>
            <strong class="dropzone__title">Drop transcript file</strong>
            <span class="dropzone__hint">TXT or Markdown is enough for the demo.</span>
          </div>
        </label>
      </div>
    `;
  }

  if (view === "loading") {
    return `
      <div class="run-shell">
        <div class="topline">
          <span class="file-chip" id="file-chip"></span>
          <span class="state-pill" id="state-pill"></span>
        </div>

        <section class="spin-stage">
          <div class="spin-orbit" aria-hidden="true">
            <span class="spin-orbit__core"></span>
            <span class="spin-orbit__sat spin-orbit__sat--one"></span>
            <span class="spin-orbit__sat spin-orbit__sat--two"></span>
            <span class="spin-orbit__sat spin-orbit__sat--three"></span>
          </div>
          <div class="spin-stage__labels">
            <span>Extract</span>
            <span>Resolve</span>
            <span>Deliver</span>
          </div>
          <p class="status-kicker" id="status-kicker"></p>
          <h2 class="status-title" id="status-title"></h2>
          <p class="status-body" id="status-body"></p>
        </section>
      </div>
    `;
  }

  return `
    <div class="run-shell">
      <div class="topline">
        <span class="file-chip" id="file-chip"></span>
        <span class="state-pill" id="state-pill"></span>
      </div>

      <section class="graph-stage">
        <div id="graph-mount"></div>
      </section>

      <section class="status-stack">
        <p class="status-kicker" id="status-kicker"></p>
        <h2 class="status-title" id="status-title"></h2>
        <p class="status-body" id="status-body"></p>
      </section>

      <section class="result-strip" id="result-strip"></section>

      <section class="details-panel" id="details-panel"></section>

      <div class="action-row" id="action-row"></div>
    </div>
  `;
}

function bindView(view) {
  if (view === "idle") {
    const dropzone = document.querySelector("#dropzone");
    const fileInput = document.querySelector("#file-input");

    dropzone.addEventListener("dragenter", handleDragEnter);
    dropzone.addEventListener("dragover", handleDragOver);
    dropzone.addEventListener("dragleave", handleDragLeave);
    dropzone.addEventListener("drop", handleDrop);
    fileInput.addEventListener("change", handleFileSelection);
    return;
  }

  if (view === "run") {
    const mount = document.querySelector("#graph-mount");
    graphController = createGraphController(mount);
  }
}

function updateView(view) {
  if (view === "idle") {
    const dropzone = document.querySelector("#dropzone");
    if (dropzone) {
      dropzone.classList.toggle("is-active", state.dragActive);
    }
    return;
  }

  document.querySelector("#file-chip").textContent = state.file?.name ?? "transcript.txt";
  document.querySelector("#state-pill").textContent = pillText();
  document.querySelector("#status-kicker").textContent = kickerText();
  document.querySelector("#status-title").textContent = titleText();
  document.querySelector("#status-body").textContent = bodyText();

  if (view === "run" && graphController) {
    graphController.update({
      stepStates: state.stepStates,
      loopClosed: state.loopClosed,
    });

    const resultStrip = document.querySelector("#result-strip");
    resultStrip.innerHTML = stripMarkup();

    const detailsPanel = document.querySelector("#details-panel");
    detailsPanel.innerHTML = detailsMarkup();

    const actionRow = document.querySelector("#action-row");
    actionRow.innerHTML = actionMarkup();

    actionRow.querySelectorAll("[data-action]").forEach((button) => {
      button.addEventListener("click", handleActionClick);
    });
  }
}

function handleDragEnter(event) {
  event.preventDefault();
  state.dragActive = true;
  render();
}

function handleDragOver(event) {
  event.preventDefault();
  if (!state.dragActive) {
    state.dragActive = true;
    render();
  }
}

function handleDragLeave(event) {
  if (!event.currentTarget.contains(event.relatedTarget)) {
    state.dragActive = false;
    render();
  }
}

function handleDrop(event) {
  event.preventDefault();
  state.dragActive = false;
  const file = event.dataTransfer?.files?.[0];
  if (file) {
    void startFileFlow(file);
  } else {
    render();
  }
}

function handleFileSelection(event) {
  const file = event.target.files?.[0];
  event.target.value = "";
  if (file) {
    void startFileFlow(file);
  }
}

async function startFileFlow(file) {
  clearTimers();
  graphController = null;

  const startedAt = performance.now();
  setStatus("validating", {
    file,
    runId: null,
    error: null,
    retryable: false,
    stepStates: createEmptyStepStates(),
    currentStepId: null,
    failureStepId: null,
    loopClosed: false,
    summary: null,
  });

  try {
    await readAndValidateFile(file);
    const elapsed = performance.now() - startedAt;
    const remaining = Math.max(320 - elapsed, 0);

    wait(remaining, () => {
      void beginBackendRun(file);
    });
  } catch (error) {
    showError(error.message, false);
  }
}

async function readAndValidateFile(file) {
  const lowerName = file.name.toLowerCase();
  const matchesExtension = ACCEPTED_EXTENSIONS.some((extension) => lowerName.endsWith(extension));
  const matchesType = !file.type || ACCEPTED_TYPES.includes(file.type);

  if (!(matchesExtension && matchesType)) {
    throw new Error("Use a .txt or .md transcript file.");
  }

  if (file.size > MAX_FILE_SIZE) {
    throw new Error("Keep the transcript under 2 MB for this demo.");
  }

  const text = await file.text();
  const trimmed = text.trim();

  if (!trimmed) {
    throw new Error("The file is empty.");
  }

  if (trimmed.length < 100) {
    throw new Error("The transcript is too short to animate a full run.");
  }

  if (/\u0000/.test(text)) {
    throw new Error("The file looks binary instead of plain text.");
  }

  return text;
}

async function beginBackendRun(file) {
  setStatus("spinning", {
    error: null,
    retryable: false,
    currentStepId: null,
    failureStepId: null,
    stepStates: createEmptyStepStates(),
    loopClosed: false,
  });
  try {
    const { run_id: runId } = await startRun(file);
    state.runId = runId;
    pollRun(runId);
  } catch (error) {
    showError(
      `${error.message} Start the bridge with "python3 frontend/app.py" if it is not running.`,
      false
    );
  }
}

function showError(message, retryable) {
  clearTimers();
  state.error = message;
  state.retryable = retryable;
  state.currentStepId = state.failureStepId;
  setStatus("error", {});
}

function handleActionClick(event) {
  const action = event.currentTarget.dataset.action;

  if (action === "retry") {
    if (state.file) {
      void startFileFlow(state.file);
    }
    return;
  }

  if (action === "reset") {
    resetState();
  }
}

async function pollRun(runId) {
  try {
    const run = await fetchRun(runId);
    if (state.runId !== runId) {
      return;
    }
    applyRun(run);

    if (run.status !== "completed" && run.status !== "error") {
      wait(700, () => {
        if (state.runId === runId) {
          void pollRun(runId);
        }
      });
    }
  } catch (error) {
    showError(error.message, true);
  }
}

function applyRun(run) {
  state.runId = run.run_id;
  state.currentStepId = run.current_step_id;
  state.failureStepId = run.failure_step_id;
  state.stepStates = run.step_states || createEmptyStepStates();
  state.loopClosed = Boolean(run.loop_closed);
  state.summary = run.summary || null;
  state.retryable = Boolean(run.retryable);
  state.error = run.error;

  if (run.status === "spinning") {
    setStatus("spinning", {});
    return;
  }

  if (run.status === "processing") {
    setStatus("processing", {});
    return;
  }

  if (run.status === "completed") {
    setStatus("completed", {});
    return;
  }

  if (run.status === "error") {
    setStatus("error", {});
  }
}

function stripMarkup() {
  if (!state.summary) {
    return "";
  }

  const items = [];

  if (state.summary.item_count !== undefined) {
    items.push(`${state.summary.item_count} action${state.summary.item_count === 1 ? "" : "s"}`);
  }

  if (state.summary.ticket_count) {
    items.push(`${state.summary.ticket_count} Jira`);
  }

  if (state.summary.branch_count) {
    items.push(`${state.summary.branch_count} branch${state.summary.branch_count === 1 ? "" : "es"}`);
  }

  if (state.summary.dry_run === true) {
    items.push("DRY_RUN");
  } else if (state.summary.dry_run === false) {
    items.push("live mode");
  }

  if (state.status === "completed") {
    items.push("Loop closed");
  }

  if (state.status === "error" && state.failureStepId && STEP_COPY[state.failureStepId]) {
    items.push(`Stopped at ${STEP_COPY[state.failureStepId].title.replace("Creating ", "")}`);
  }

  return items.map((item) => `<span class="metric-chip">${item}</span>`).join("");
}

function actionMarkup() {
  if (state.status === "completed") {
    return `
      <button class="action-button action-button--primary" data-action="reset">
        Upload another transcript
      </button>
    `;
  }

  if (state.status === "error") {
    return `
      ${state.retryable ? '<button class="action-button action-button--primary" data-action="retry">Retry run</button>' : ""}
      <button class="action-button action-button--secondary" data-action="reset">
        Start over
      </button>
    `;
  }

  return "";
}

function detailsMarkup() {
  if (!state.summary) {
    return "";
  }

  const hasItems = Array.isArray(state.summary.items) && state.summary.items.length > 0;
  const hasErrors =
    Array.isArray(state.summary.processing_errors) && state.summary.processing_errors.length > 0;
  const outputTail = Array.isArray(state.summary.stdout_tail)
    ? state.summary.stdout_tail.slice(-8)
    : [];

  if (state.status === "processing") {
    return `
      <div class="details-card details-card--soft">
        <p class="details-card__eyebrow">Process</p>
        <p class="details-card__text">Running the real <code>main.py</code> pipeline in the background.</p>
      </div>
    `;
  }

  if (state.status === "completed" || state.status === "error") {
    return `
      ${hasItems ? itemListMarkup(state.summary.items) : ""}
      ${hasErrors ? errorListMarkup(state.summary.processing_errors) : ""}
      ${outputTail.length ? outputMarkup(outputTail) : ""}
    `;
  }

  return "";
}

function itemListMarkup(items) {
  return `
    <div class="details-card">
      <p class="details-card__eyebrow">Run output</p>
      <div class="item-list">
        ${items
          .map(
            (item) => `
              <article class="item-card">
                <strong>${escapeHtml(item.title || "Untitled")}</strong>
                ${item.assignee ? `<span>${escapeHtml(item.assignee)}</span>` : ""}
                ${item.jira ? `<span>${escapeHtml(item.jira)}</span>` : ""}
                ${item.github_branch ? `<span>${escapeHtml(item.github_branch)}</span>` : ""}
              </article>
            `
          )
          .join("")}
      </div>
    </div>
  `;
}

function errorListMarkup(errors) {
  return `
    <div class="details-card details-card--soft">
      <p class="details-card__eyebrow">Processing errors</p>
      <ul class="error-list">
        ${errors.map((error) => `<li>${escapeHtml(error)}</li>`).join("")}
      </ul>
    </div>
  `;
}

function outputMarkup(lines) {
  return `
    <details class="details-card details-card--soft log-card">
      <summary>Process output</summary>
      <pre>${escapeHtml(lines.join("\n"))}</pre>
    </details>
  `;
}

function kickerText() {
  if (state.status === "validating") {
    return "File accepted";
  }

  if (state.status === "spinning") {
    return "Agents spinning up";
  }

  if (state.status === "completed") {
    return "Run complete";
  }

  if (state.status === "error") {
    return "Run interrupted";
  }

  if (state.currentStepId) {
    return STEP_COPY[state.currentStepId].kicker;
  }

  return "Workflow ready";
}

function titleText() {
  if (state.status === "validating") {
    return "Validating transcript";
  }

  if (state.status === "spinning") {
    return "Starting agents";
  }

  if (state.status === "completed") {
    return "Loop closed. Run complete.";
  }

  if (state.status === "error") {
    return "The run hit a clean stop.";
  }

  if (state.currentStepId) {
    return STEP_COPY[state.currentStepId].title;
  }

  return "Drop transcript file";
}

function bodyText() {
  if (state.status === "validating") {
    return "Checking the file shape before the graph comes online.";
  }

  if (state.status === "spinning") {
    return "Uploading the real file and preparing the Python pipeline.";
  }

  if (state.status === "completed") {
    const count = state.summary?.item_count ?? 0;
    return `${count} action${count === 1 ? "" : "s"} came back from the real run, and the graph closed cleanly.`;
  }

  if (state.status === "error") {
    return state.error ?? "Something stopped the run before the loop could close.";
  }

  if (state.currentStepId) {
    return STEP_COPY[state.currentStepId].body;
  }

  return "TXT or Markdown is enough for this demo.";
}

function pillText() {
  if (state.status === "validating") {
    return "Validating";
  }

  if (state.status === "spinning") {
    return "Uploading";
  }

  if (state.status === "completed") {
    return "Loop closed";
  }

  if (state.status === "error") {
    return "Stopped";
  }

  if (state.currentStepId) {
    return STEP_COPY[state.currentStepId].pill;
  }

  return "Ready";
}

function joinNatural(values) {
  if (values.length === 1) {
    return values[0];
  }

  if (values.length === 2) {
    return `${values[0]} and ${values[1]}`;
  }

  return `${values.slice(0, -1).join(", ")}, and ${values.at(-1)}`;
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
