# Integrations and Scope

## 1. Recommended MVP Scope

### Included in V1

- **Transcript ingestion**: Accept a plain-text or markdown transcript as input (pasted, uploaded, or sent via API). One transcript at a time.
- **Action item extraction**: LLM extracts structured action items (task description, suggested assignee, optional due date) from transcript.
- **Human confirmation step**: Before anything is created downstream, present extracted action items to the user (via Slack or a simple CLI/web form) for review, edit, and approval.
- **Jira ticket creation**: Create one Jira issue per confirmed action item. Jira is the single source of truth for task state.
- **Slack notification**: Post a summary message to a designated channel (or DM assignees) with the created tasks and Jira links.
- **Slack-driven completion**: A user clicks a button on the Slack message to mark a task done. This triggers a Jira status transition (e.g., move to "Done").

### Excluded from V1

- **Live meeting listening / real-time transcription**: Out of scope entirely. The system is post-meeting only.
- **Multi-team / multi-project support**: One team, one Jira project, one Slack channel.
- **Recurring meeting awareness or memory**: No cross-meeting context. Each transcript is independent.
- **Complex Jira workflows**: No sub-tasks, epics, sprint assignment, or custom field mapping beyond the basics (summary, description, assignee, status).
- **Authentication / multi-user access control**: Single-operator system. One set of API credentials.
- **Dashboard or web UI**: Slack is the UI. No custom frontend.

### Deferred (V2 candidates)

- **GitHub integration**: Creating branches or scaffolding for engineering tasks. This adds real complexity (repo selection, branch naming, template logic) for marginal MVP value. Defer entirely.
- **Assignee inference from transcript**: V1 uses explicit human confirmation. Automatic inference from names/context in transcript is a V2 enhancement once the core loop works.
- **Due date extraction**: Nice to have. V1 can leave due date blank or let the user set it during confirmation.
- **Bidirectional Jira sync**: Listening for Jira status changes and reflecting them back to Slack. V1 only flows Slack -> Jira, not the reverse.
- **Meeting platform integration**: No Zoom/Google Meet/Teams API. The user provides the transcript however they get it.

---

## 2. Simplified End-to-End Flow

### The MVP flow (5 steps)

```
Transcript in -> Extract action items -> Human confirms -> Create Jira tickets -> Notify via Slack
                                                                                        |
                                                                          User clicks "Done" in Slack
                                                                                        |
                                                                              Update Jira to Done
```

### Complexity trap evaluation

**Live meeting listening vs. transcript/post-meeting processing**
Decision: **Post-meeting only.** Live listening requires real-time transcription infrastructure, streaming APIs, partial-result handling, and always-on processes. None of that is needed. The user pastes or uploads a transcript after the meeting ends. This is the single biggest complexity cut.

**Freeform assignee inference vs. human-confirmed assignment**
Decision: **Human-confirmed assignment.** The LLM can suggest assignees extracted from the transcript, but these are suggestions only. The user reviews and corrects before anything is created. This avoids wrong-person bugs, hallucinated names, and the need for a name-to-Jira-user mapping layer. V1 presents a simple list: "Here are the action items I found. Confirm or edit assignees, then approve." A static mapping of team member names to Jira account IDs is sufficient (hardcoded config or a small lookup table).

**Passive Slack listening vs. explicit Slack completion action**
Decision: **Explicit Slack action (interactive button).** No ambient Slack monitoring. Each task notification includes a "Mark Complete" button. When clicked, it fires a webhook back to the system. This is simpler than parsing channel messages, requires no Slack event subscription beyond interactivity, and is unambiguous in intent.

**Automatic Jira closure vs. confirmation-based status update**
Decision: **Direct Jira transition on button click -- no second confirmation.** The user already made an explicit choice by clicking the button. Adding a "are you sure?" confirmation layer adds friction with no value for an internal team MVP. One click = task moved to Done in Jira.

**GitHub automation in V1 vs. deferred**
Decision: **Deferred entirely.** GitHub integration (branch creation, issue creation, scaffolding) is the lowest-value, highest-complexity integration for an MVP. It requires repo context, branch naming conventions, and template decisions. Cut it. If the team wants it later, it slots in as an additional node after Jira creation.

---

## 3. Tool and Integration Strategy

### Meeting transcript input

- **Mechanism**: The system accepts a transcript as a string input. No meeting platform API.
- **Format**: Plain text or markdown. No structured format required.
- **Entry point**: Either a Slack slash command (`/process-meeting` with a text attachment or pasted content), a simple HTTP endpoint, or a CLI invocation. For MVP, a Slack slash command is the most natural since Slack is already the interaction layer.
- **When called**: This is the trigger that starts the entire graph. Step 0.

### Jira

- **API**: Jira REST API v3 (Cloud) or v2 (Server). Use the `python-jira` library or direct HTTP requests.
- **Required API interactions (3 total)**:
  1. **Create issue** (`POST /rest/api/3/issue`): Called once per confirmed action item. Fields: project key, summary, description, assignee (Jira account ID), issue type (Task).
  2. **Transition issue** (`POST /rest/api/3/issue/{id}/transitions`): Called when a user clicks "Done" in Slack. Moves the issue to the Done status. Requires knowing the transition ID for the target project (fetch once at startup or hardcode).
  3. **Get transitions** (`GET /rest/api/3/issue/{id}/transitions`): Optional, called once to discover the "Done" transition ID if not hardcoded.
- **Auth**: API token + email (Cloud) or PAT (Server). Stored as environment variables.
- **When called**: After human confirmation (create), and on Slack button click (transition).

### Slack

- **API**: Slack Web API + Slack Interactivity (Block Kit).
- **Required API interactions (3 total)**:
  1. **Post message with blocks** (`chat.postMessage`): Send the action item summary to a channel or DM. Include Block Kit buttons ("Mark Complete") per task. Each button payload carries the Jira issue key.
  2. **Handle slash command** (incoming webhook from Slack): Receive the `/process-meeting` command with transcript text. This triggers the graph.
  3. **Handle interactive action** (incoming webhook from Slack interactivity endpoint): Receive button click events. Extract the Jira issue key from the action payload, trigger the Jira transition.
- **Auth**: Bot token (xoxb-). Stored as environment variable.
- **Slack app setup**: One app with bot token scopes (`chat:write`, `commands`), interactivity URL pointed at the backend, and one slash command registered.
- **When called**: Slash command triggers the graph; message posted after Jira tickets are created; button clicks trigger Jira updates.

### GitHub (deferred)

- **Not integrated in V1.** When added in V2, the minimum integration would be:
  1. Create a branch from main (`POST /repos/{owner}/{repo}/git/refs`) per engineering-tagged task.
  2. Optionally create a GitHub issue linked to the Jira ticket.
- **This adds**: repo selection logic, branch naming logic, and a tagging/classification step. All of which is unnecessary for the MVP.

---

## 4. Minimal Architecture

### One service, one graph

```
+------------------------------------------------------------------+
|  Single Python service (FastAPI or Flask)                         |
|                                                                   |
|  Endpoints:                                                       |
|    POST /slack/commands    <- Slack slash command                  |
|    POST /slack/interact    <- Slack button clicks                  |
|                                                                   |
|  LangGraph orchestration:                                         |
|    [input] -> [extract] -> [confirm] -> [create_jira] -> [notify] |
|                                                                   |
|  Direct integrations:                                             |
|    - Jira REST API (via requests or python-jira)                  |
|    - Slack Web API (via slack_sdk)                                |
|    - OpenAI / Anthropic API (for extraction LLM)                  |
+------------------------------------------------------------------+
```

### LangGraph graph design

The graph has **5 nodes**. No sub-graphs, no agent delegation, no tool-calling agents.

| Node | Type | What it does |
|------|------|-------------|
| `parse_transcript` | LLM call | Takes raw transcript, returns structured action items (JSON list of {task, suggested_assignee, context_snippet}). Single prompt, structured output. |
| `await_confirmation` | Human-in-the-loop | Sends extracted items to Slack (or returns them for review). Pauses graph execution until the user confirms. User can edit assignees and remove items. |
| `create_jira_tickets` | Deterministic | Iterates over confirmed items, creates Jira issues via API. Returns list of created issue keys. |
| `notify_slack` | Deterministic | Posts a summary message to Slack with Jira links and "Mark Complete" buttons. |
| `handle_completion` | Deterministic | Triggered separately (not part of the main graph run) when a Slack button is clicked. Transitions the Jira issue to Done. |

Routing between nodes is **fully deterministic** -- there are no conditional edges based on LLM output. The graph is a straight pipeline for the main flow, with `handle_completion` as a separate entry point triggered by webhooks.

### Human-in-the-loop implementation

The `await_confirmation` node is the only tricky part. Two options, in order of simplicity:

1. **Preferred: Slack-native confirmation.** The node posts the extracted items to Slack as an interactive message with "Approve" / "Edit" / "Remove" buttons per item and a final "Confirm All" button. The graph checkpoints its state and halts. When the user clicks "Confirm All", the Slack interactivity webhook resumes the graph from the checkpoint with the confirmed items. LangGraph's `interrupt` / checkpoint mechanism supports this pattern directly.

2. **Simpler fallback: Auto-approve.** For the earliest prototype, skip confirmation entirely -- just create tickets from whatever the LLM extracts. Add confirmation once the core pipeline works end-to-end. This is a valid "V0.5" approach.

### Persistence

- **LangGraph checkpointer**: Use `MemorySaver` (in-memory) for the MVP. It is sufficient for one team with low usage. If the process restarts, in-flight runs are lost, which is acceptable.
- **No database.** Jira is the system of record. Slack messages are the notification record. There is no need for a separate database in V1.
- **Config file**: A simple YAML or JSON file mapping team member display names to Jira account IDs and Slack user IDs. Hardcoded for one team.

### Deployment

- One process. Run it anywhere: local machine, a single VM, or a container. No orchestration, no workers, no queues.
- The process runs a web server (FastAPI) to handle Slack webhooks and hosts the LangGraph graph in-process.
- Use `ngrok` or similar for local development to expose Slack webhook endpoints.

### What this architecture intentionally does not have

- No message queue or event bus.
- No separate worker processes.
- No database.
- No caching layer.
- No auth layer (single-operator, API keys in env vars).
- No GitHub integration.
- No custom frontend.
- No agent-style tool calling -- every node does exactly one thing.
- No retry/resilience logic beyond what `requests` provides by default.
