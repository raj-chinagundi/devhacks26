# Frontend Demo

This folder contains a self-contained frontend for `auto-meet`.

## What Was Built

- A single-page drag-and-drop transcript experience
- Immediate `agents spinning up` feedback after file drop
- A graph-based progress visualization that activates nodes and edges in sequence
- A completion moment where the graph closes back into the transcript node
- Graceful idle, validating, processing, completed, and error states
- A small local bridge that uploads the dropped file and runs the real `main.py` script

The bridge lives entirely inside `frontend/`, so the existing backend code stays untouched. The dropped transcript is sent to the bridge, saved temporarily, and passed to the real CLI pipeline.

## Folder Structure

```text
frontend/
  index.html
  styles.css
  main.js
  graph.js
  api.js
  app.py
  README.md
```

- `index.html`
  The one-page shell and static copy.
- `styles.css`
  Layout, typography, motion, dropzone styling, and graph visuals.
- `main.js`
  The app state machine, drag-and-drop logic, validation, mock run timing, and status copy.
- `graph.js`
  The fixed SVG graph and the small controller that updates node and edge classes.
- `api.js`
  Thin browser calls for starting a run and polling its status.
- `app.py`
  Local FastAPI bridge that serves the frontend and runs `main.py` with the uploaded transcript.

## State Flow

The UI keeps one top-level state enum and a small graph step model. The browser does client-side validation first, then the bridge starts the real Python run and the frontend polls for updates.

### Top-level states

- `idle`
  Empty dropzone, ready for drag and drop or click-to-select.
- `validating`
  File is accepted and checked locally for type, size, and basic content.
- `spinning`
  The `agents spinning up` transition while the file is uploaded and the Python process starts.
- `processing`
  The graph view is active and steps advance in order.
- `completed`
  All steps are complete and the loop closes back to the transcript node.
- `error`
  The failed step stays visible and the user can retry or reset.

### Step model

The graph tracks these ordered steps:

1. `extract`
2. `resolve`
3. `review`
4. `route`
5. `jira`
6. `github`
7. `slack`

Each step is `pending`, `running`, `done`, or `failed`.

## Graph Animation

The graph is a fixed inline SVG with faint base rails and animated overlay rails.

- Nodes start quiet and low-contrast.
- When a step starts, its incoming edge draws first, then the node brightens and pulses.
- Completed nodes settle into a warm accent state instead of continuing to flash.
- The final state activates the return path from `Slack` back to the `Transcript` node so the graph visually closes the loop.

This intentionally avoids charting libraries or physics-based graph layouts. The whole thing is deterministic and easy to follow.

Because `main.py` is a CLI and does not emit structured node events, the bridge infers graph progress from real process output markers and the final summary. The transcript is real and the script run is real; only the fine-grained progress mapping is approximate.

## Validation And Error Handling

Client-side and bridge-side validation both accept one `.txt` or `.md` file, up to `2 MB`, with non-empty UTF-8 text.

The bridge auto-approves the CLI review prompt by sending `y` to `main.py` so the frontend can run end-to-end without a second manual terminal step.

## How To Run

Run the bridge server from the repo root:

```bash
python3 frontend/app.py
```

Then open `http://localhost:4173`.

## What Was Intentionally Left Out

- No framework, bundler, router, or state library
- No fake dashboard, review editor, settings, or tabs
- No fabricated action-item detail screen, to keep the experience focused on upload -> spin up -> graph -> closed loop
