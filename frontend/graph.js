const TRANSCRIPT_NODE = {
  id: "transcript",
  label: "Transcript",
  x: 360,
  y: 92,
  radius: 34,
};

export const STEP_SEQUENCE = [
  { id: "extract", label: "Extract", x: 552, y: 152, radius: 22 },
  { id: "resolve", label: "Resolve", x: 598, y: 286, radius: 22 },
  { id: "review", label: "Review", x: 500, y: 418, radius: 28 },
  { id: "route", label: "Route", x: 342, y: 474, radius: 22 },
  { id: "jira", label: "Jira", x: 182, y: 420, radius: 22 },
  { id: "github", label: "GitHub", x: 104, y: 282, radius: 22 },
  { id: "slack", label: "Slack", x: 166, y: 146, radius: 22 },
];

const NODE_BY_ID = new Map([TRANSCRIPT_NODE, ...STEP_SEQUENCE].map((node) => [node.id, node]));

const EDGE_SEQUENCE = [
  { id: "transcript-extract", from: "transcript", to: "extract", curve: 30 },
  { id: "extract-resolve", from: "extract", to: "resolve", curve: 24 },
  { id: "resolve-review", from: "resolve", to: "review", curve: 24 },
  { id: "review-route", from: "review", to: "route", curve: 18 },
  { id: "route-jira", from: "route", to: "jira", curve: 18 },
  { id: "jira-github", from: "jira", to: "github", curve: 20 },
  { id: "github-slack", from: "github", to: "slack", curve: 22 },
  { id: "slack-transcript", from: "slack", to: "transcript", loop: true },
];

function buildCurvedPath(from, to, curve) {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const distance = Math.hypot(dx, dy) || 1;
  const midX = (from.x + to.x) / 2;
  const midY = (from.y + to.y) / 2;
  const normalX = -dy / distance;
  const normalY = dx / distance;
  const controlX = midX + normalX * curve;
  const controlY = midY + normalY * curve;

  return `M ${from.x} ${from.y} Q ${controlX} ${controlY} ${to.x} ${to.y}`;
}

function buildLoopPath() {
  return "M 166 146 C 102 104 148 44 264 50 C 314 54 340 67 360 92";
}

function pathForEdge(edge) {
  if (edge.loop) {
    return buildLoopPath();
  }

  return buildCurvedPath(NODE_BY_ID.get(edge.from), NODE_BY_ID.get(edge.to), edge.curve);
}

function edgeMarkup(edge) {
  const d = pathForEdge(edge);

  return `
    <g class="graph-edge-wrap">
      <path class="graph-edge graph-edge--base" d="${d}" />
      <path
        class="graph-edge graph-edge--active"
        data-edge="${edge.id}"
        data-target="${edge.to}"
        d="${d}"
        pathLength="100"
      />
    </g>
  `;
}

function nodeMarkup(node, isTranscript = false) {
  const className = isTranscript ? "graph-node graph-node--transcript" : "graph-node";
  const labelOffset = isTranscript ? 60 : node.radius + 28;

  return `
    <g
      class="${className}"
      data-node="${node.id}"
      transform="translate(${node.x} ${node.y})"
    >
      <circle class="graph-node__halo" r="${node.radius + 12}" />
      <circle class="graph-node__pulse" r="${node.radius + 5}" />
      <circle class="graph-node__shell" r="${node.radius}" />
      <circle class="graph-node__core" r="${Math.max(8, node.radius - 14)}" />
      <text class="graph-node__label" y="${labelOffset}">${node.label}</text>
    </g>
  `;
}

function graphMarkup() {
  return `
    <div class="graph-canvas">
      <svg class="graph-svg" viewBox="0 0 720 560" role="img" aria-label="Workflow progress graph">
        <defs>
          <filter id="graph-node-shadow" x="-50%" y="-50%" width="200%" height="200%">
            <feDropShadow dx="0" dy="6" stdDeviation="10" flood-opacity="0.08" />
          </filter>
        </defs>

        <rect class="graph-svg__backdrop" x="1" y="1" width="718" height="558" rx="28" />
        ${EDGE_SEQUENCE.map(edgeMarkup).join("")}
        ${nodeMarkup(TRANSCRIPT_NODE, true)}
        ${STEP_SEQUENCE.map((node) => nodeMarkup(node)).join("")}
      </svg>
    </div>
  `;
}

function setNodeState(element, state) {
  element.classList.remove(
    "graph-node--pending",
    "graph-node--running",
    "graph-node--done",
    "graph-node--failed",
    "graph-node--loop-closed"
  );
  element.classList.add(`graph-node--${state}`);
}

function setEdgeState(element, state) {
  element.classList.remove(
    "graph-edge--pending",
    "graph-edge--running",
    "graph-edge--done",
    "graph-edge--failed"
  );
  element.classList.add(`graph-edge--${state}`);
}

export function createGraphController(container) {
  container.innerHTML = graphMarkup();

  const nodeMap = new Map(
    [...container.querySelectorAll("[data-node]")].map((element) => [element.dataset.node, element])
  );
  const edgeMap = new Map(
    [...container.querySelectorAll("[data-edge]")].map((element) => [element.dataset.edge, element])
  );

  return {
    update(graphState) {
      const stepStates = graphState.stepStates ?? {};

      for (const step of STEP_SEQUENCE) {
        const stepState = stepStates[step.id] ?? "pending";
        const nodeElement = nodeMap.get(step.id);
        if (nodeElement) {
          setNodeState(nodeElement, stepState);
        }
      }

      const transcriptNode = nodeMap.get("transcript");
      if (transcriptNode) {
        setNodeState(transcriptNode, graphState.loopClosed ? "done" : "pending");
        transcriptNode.classList.toggle("graph-node--loop-closed", Boolean(graphState.loopClosed));
      }

      for (const edge of EDGE_SEQUENCE) {
        const edgeElement = edgeMap.get(edge.id);
        if (!edgeElement) {
          continue;
        }

        let edgeState = "pending";

        if (edge.loop) {
          edgeState = graphState.loopClosed ? "done" : "pending";
        } else {
          const targetState = stepStates[edge.to] ?? "pending";
          if (targetState === "done") {
            edgeState = "done";
          } else if (targetState === "running") {
            edgeState = "running";
          } else if (targetState === "failed") {
            edgeState = "failed";
          }
        }

        setEdgeState(edgeElement, edgeState);
      }
    },
  };
}
