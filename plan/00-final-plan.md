# Meeting-to-Tasks MVP: Final Implementation Plan

## Lead Notes

**Revision 2.** This plan restores 5 architectural elements that were over-simplified in Revision 1. The previous version reduced the system to a linear pipeline where every action item got identical treatment (Jira + Slack), which eliminated the core value proposition: intelligent routing of different action item types to different downstream tools.

### Changes from Revision 1

1. **Routing node restored.** Added `route_action_items` — a deterministic node that tags each action item with which tools to invoke based on extracted tags/keywords. This is the reason LangGraph matters for this project. Without it, a simple script would suffice.

2. **GitHub integration restored (minimal).** Added `create_github_branches` — a deterministic tool node that creates feature branches for engineering-tagged items. ~30 lines of code. This is what makes the routing decision visible in the demo.

3. **Parallel fan-out restored.** After routing, the graph fans out to `create_jira_tickets`, `send_slack_notifications`, and `create_github_branches` in parallel. This is the LangGraph pattern worth demoing — a linear pipeline does not need LangGraph.

4. **AI-generated Slack messages restored.** `send_slack_notifications` now includes an LLM call that generates a contextual summary per action item referencing what was discussed in the meeting. This is the second place AI adds visible user-facing value.

5. **Group notification restored.** Slack messages now go to a shared channel thread (e.g., `#meeting-actions`) rather than isolated DMs. All assignees see each other's tasks from the same meeting.

### What stayed the same

Post-meeting transcript input, human review checkpoint, assignee resolution via roster lookup, Jira as system of record, explicit "Mark Complete" button, separate webhook handler for completion loop, single FastAPI service, MemorySaver persistence, CLI entry point for Phase 1.

### Node count: 7 (was 5)

The two additions (router + GitHub) are what make the demo meaningful. The graph now shows branching fan-out, not a straight line.

### LLM call count: 2 (was 1)

1. `extract_action_items` — extract structured action items with tags
2. `send_slack_notifications` — generate contextual message per action item (batchable)

Both are single-call, structured-output invocations. Neither is an agent loop.

---

## 1. Plain-English Restatement

This system takes a meeting transcript after the meeting ends, extracts action items using an LLM, intelligently routes each item to the appropriate downstream tools (Jira, Slack, and optionally GitHub), and notifies the team with AI-generated contextual summaries. The MVP proves that a LangGraph orchestrator can bridge the gap between "things people said in a meeting" and "tracked, routed work with owners" — with deterministic routing, parallel fan-out to multiple tools, and human oversight at ambiguous points.

## 2. MVP Goal

**Success for the first demo:** A user provides a meeting transcript containing both engineering and non-engineering tasks. The system extracts action items with tags, asks a human to confirm/correct, then routes each item to the appropriate tools: engineering tasks get Jira tickets + GitHub branches + Slack notifications; non-engineering tasks get Jira tickets + Slack notifications only. Slack messages include AI-generated contextual summaries posted to a shared team thread. When an assignee clicks "Done" in Slack, the corresponding Jira ticket is closed.

The demo must show:
- At least one engineering task routed to Jira + Slack + GitHub (branch created)
- At least one non-engineering task routed to Jira + Slack only (no branch)
- AI-generated Slack messages that reference what was actually discussed
- All tasks visible in a shared thread for team context

If that loop works end-to-end for one real meeting with 3–5 action items of mixed types, the MVP is proven.

## 3. Recommended MVP Scope

### Included in V1

- **Transcript ingestion**: Accept a plain-text or markdown transcript as input (pasted, uploaded, or sent via API). One transcript at a time.
- **Action item extraction**: LLM extracts structured action items (task title, description, suggested assignee, priority, tags) from transcript. Single LLM call with structured output. Tags include "engineering" for code-related tasks.
- **Assignee resolution**: Deterministic lookup against a hardcoded team roster mapping name variants to Jira/Slack user IDs. Flags unresolved assignees for human review.
- **Human confirmation step**: Before anything is created downstream, present extracted action items (including tags and routing preview) for review, edit, and approval.
- **Deterministic routing**: Rule-based routing per action item based on tags. Engineering-tagged items → Jira + Slack + GitHub. All others → Jira + Slack.
- **Jira ticket creation**: Create one Jira issue per confirmed action item. Jira is the single source of truth for task state.
- **GitHub branch creation**: For engineering-tagged items, create a feature branch from main named after the Jira ticket.
- **Slack notification with AI-generated summaries**: Post to a shared channel thread per meeting. Each action item gets an LLM-generated contextual message referencing what was discussed. Includes "Mark Complete" button.
- **Slack-driven completion**: Button click triggers a Jira status transition to Done and updates the Slack message.

### Excluded from V1

- Live meeting listening / real-time transcription
- Multi-team / multi-project support
- Recurring meeting awareness or cross-meeting memory
- Complex Jira workflows (sub-tasks, epics, sprints, custom fields)
- Authentication / multi-user access control
- Dashboard or web UI (Slack is the UI)
- GitHub issue creation, PR creation, or scaffolding beyond branch creation
- Bidirectional Jira sync (V1 flows Slack → Jira only)

### Deferred (V2 Candidates)

- **Automatic assignee inference without human review**: V1 uses human confirmation.
- **Due date extraction**: V1 leaves due date blank or lets user set during confirmation.
- **Slack-native human review**: Start with CLI, upgrade to Slack interactive review later.
- **Meeting platform integration**: No Zoom/Google Meet/Teams API.
- **GitHub PRs, issue linking, or code scaffolding**: V1 only creates branches.
- **LLM-based routing**: V1 routing is rule-based. LLM-based routing is a V2 enhancement if tag coverage proves insufficient.

## 4. Simplified End-to-End Flow

### The MVP flow

```
Transcript → Extract action items (with tags) → Resolve assignees → Human confirms
                                                                         │
                                                                  Route action items
                                                                   ┌─────┼─────────┐
                                                                   │     │         │
                                                              Create   Send      Create
                                                              Jira    Slack     GitHub
                                                             tickets  notifs   branches
                                                                   └─────┼─────────┘
                                                                         │
                                                           User clicks "Done" in Slack
                                                                         │
                                                               Update Jira to Done
```

### Complexity trap evaluation

| Trap | Decision | Rationale |
|------|----------|-----------|
| Live meeting listening vs. post-meeting | **Post-meeting only.** | Live listening requires streaming infrastructure. The user provides a transcript. Biggest complexity cut. |
| Freeform assignee inference vs. human-confirmed | **Human-confirmed.** | LLM suggests assignees; roster lookup resolves IDs; human reviews and corrects. |
| Passive Slack listening vs. explicit action | **Explicit button click.** | Each notification has a "Mark Complete" button. Unambiguous, minimal setup. |
| Automatic Jira closure vs. confirmation | **Direct transition on click — no second confirmation.** | Button click is already explicit. |
| GitHub in V1 vs. deferred | **Included — branch creation only.** | Branch creation is ~30 lines and is what makes routing visible in the demo. Without a divergent path, the router has nothing to decide. |
| Template Slack messages vs. AI-generated | **AI-generated contextual summaries.** | A template message is indistinguishable from a Jira webhook. The LLM crafts a message referencing what was discussed — this is where AI adds visible user-facing value. |
| Individual DMs vs. shared thread | **Shared channel thread.** | Team just had a meeting together. Seeing each other's assignments in shared context is the natural UX. Simpler than per-user DMs too. |

## 5. LangGraph Design Recommendation

### Graph shape

**Linear pipeline through human review, then parallel fan-out to tool nodes.**

```
[extract] → [resolve] → [human_review] → [route] → ┬─[jira]───┐
                                                     ├─[slack]──┤→ END
                                                     └─[github]─┘
```

The fan-out after routing is the LangGraph pattern worth validating — parallel dispatch to multiple tools based on task type. The Slack "mark complete" callback remains a **separate webhook handler**.

### Centralized orchestrator vs. multi-agent

**Centralized orchestrator with specialist nodes. Not multi-agent.**

- Two LLM calls total (extraction + Slack message generation). Everything else is deterministic.
- No node has a tool-calling agent loop. Each node does exactly one thing.
- The routing node is deterministic `if/else`, not LLM delegation.
- Multi-agent coordination adds overhead with no benefit for this flow.

### Deterministic routing vs. LLM reasoning

| Decision | Approach | Rationale |
|----------|----------|-----------|
| Extracting action items from transcript | **LLM** | Genuinely unstructured. |
| Inferring assignees from transcript | **LLM** (within extraction node) | Names in transcripts are messy. Human review catches errors. |
| Resolving names to Jira/Slack IDs | **Deterministic** | Roster lookup table. |
| Deciding which tools to invoke per item | **Deterministic** | Rule-based on tags: if "engineering" → Jira + Slack + GitHub, else → Jira + Slack. |
| Generating Slack message content | **LLM** | Contextual summary referencing the meeting discussion. |
| Closing Jira on Slack callback | **Deterministic** | Direct API call. |

### Human-in-the-loop checkpoints

**One checkpoint: after assignee resolution, before routing and tool calls.**

The human reviews:
- Were the right action items extracted?
- Are tags correct? (especially "engineering" tag, since it drives routing)
- Are assignees correct?
- Are task descriptions reasonable?

Uses LangGraph's `interrupt()`. The graph pauses, the human edits state (including tags), and the graph resumes. The human can see the routing preview (which tools each item will trigger) before confirming.

### Preventing graph complexity growth

1. No agent delegation. Nodes call tools directly.
2. No dynamic tool selection. Tool set is hardcoded per node; the router just tags items.
3. No cycles in the main graph. Retries handled inside nodes with try/except.
4. Fan-out over action items happens inside nodes. The graph-level fan-out is tool-type parallelism (Jira / Slack / GitHub), not per-item parallelism.
5. The Slack completion callback is a separate entry point, not a graph cycle.
6. Routing logic is `if/else` on tags, not an LLM call. If routing needs to get smarter, upgrade the extraction prompt to produce better tags — don't add an LLM routing node.

## 6. LangGraph State Model

```python
from typing import TypedDict, Literal

class ActionItem(TypedDict):
    id: str                          # Generated UUID
    title: str                       # Short task title
    description: str                 # 1-2 sentence description
    assignee_name: str               # Extracted from transcript by LLM
    assignee_jira_id: str | None     # Resolved via roster lookup
    assignee_slack_id: str | None    # Resolved via roster lookup
    priority: Literal["high", "medium", "low"]
    tags: list[str]                  # Extracted by LLM (e.g., ["engineering", "backend"])
    tools_to_invoke: list[str]       # Set by router (e.g., ["jira", "slack", "github"])
    status: Literal["extracted", "resolved", "confirmed", "routed",
                     "jira_created", "notified", "done"]
    jira_ticket_id: str | None       # e.g., "PROJ-123"
    jira_ticket_url: str | None
    github_branch_name: str | None   # e.g., "feature/PROJ-123-task-title-slug"
    github_branch_url: str | None
    slack_summary: str | None        # LLM-generated contextual message
    slack_message_ts: str | None     # For updating the Slack message later

class MeetingState(TypedDict):
    # Meeting metadata
    meeting_id: str
    meeting_title: str
    meeting_date: str
    participants: list[str]          # Names extracted from transcript

    # Transcript
    transcript: str                  # Raw transcript text

    # Extracted work
    action_items: list[ActionItem]

    # Slack context
    slack_channel_id: str | None     # Channel where notifications are posted
    slack_thread_ts: str | None      # Thread timestamp for this meeting's items

    # Control flags
    human_review_complete: bool
    processing_errors: list[str]     # Collect errors, don't crash
```

## 7. Recommended Node Set

### Node 1: `extract_action_items`

| | |
|---|---|
| **Purpose** | Call an LLM to identify action items from the transcript. Return structured output including tags. Also extracts meeting metadata (title, date, participants). |
| **Inputs** | Raw transcript text. |
| **Outputs** | `MeetingState` populated with meeting metadata and `action_items` list with `status: "extracted"`. Each item has `tags` populated (e.g., `["engineering"]` for code-related tasks). |
| **MVP?** | Mandatory. |
| **Type** | **LLM-powered.** Single LLM call with structured output (Pydantic model). Prompt explicitly asks for tags and includes few-shot examples showing how to tag engineering vs. non-engineering tasks. |

### Node 2: `resolve_assignees`

| | |
|---|---|
| **Purpose** | Map extracted assignee names to Jira/Slack user IDs using a hardcoded team roster. Flag unresolved assignees. |
| **Inputs** | `action_items` from state, team roster config. |
| **Outputs** | `action_items` updated with `assignee_jira_id`, `assignee_slack_id`, `status: "resolved"`. Unresolved items flagged. |
| **MVP?** | Mandatory. |
| **Type** | **Deterministic.** Dictionary lookup with fuzzy name matching. |

### Node 3: `human_review`

| | |
|---|---|
| **Purpose** | Pause execution. Present extracted action items (including tags and routing preview) for human confirmation/editing. |
| **Inputs** | `action_items` from state. |
| **Outputs** | Updated `action_items` (human may edit titles, tags, assignees, delete or add items). `human_review_complete: True`. All remaining items set to `status: "confirmed"`. |
| **MVP?** | Mandatory. |
| **Type** | **Human-in-the-loop interrupt.** Uses LangGraph's `interrupt()`. Start with CLI/file-based review. The review display shows which tools each item will trigger based on its tags. |

### Node 4: `route_action_items`

| | |
|---|---|
| **Purpose** | Determine which downstream tools to invoke for each confirmed action item based on tags. |
| **Inputs** | Confirmed `action_items` from state. |
| **Outputs** | Each item updated with `tools_to_invoke` list and `status: "routed"`. |
| **MVP?** | Mandatory. |
| **Type** | **Deterministic.** Rule-based `if/else`: if `"engineering"` in `tags` or description mentions code/repo/branch/deploy → `["jira", "slack", "github"]`; otherwise → `["jira", "slack"]`. No LLM call. |

**Routing rules (V1):**
```python
def route(item: ActionItem) -> list[str]:
    engineering_keywords = {"code", "repo", "branch", "deploy", "PR", "merge", "refactor", "bug fix"}
    is_engineering = (
        "engineering" in item["tags"]
        or any(kw in item["description"].lower() for kw in engineering_keywords)
    )
    if is_engineering:
        return ["jira", "slack", "github"]
    return ["jira", "slack"]
```

### Node 5: `create_jira_tickets`

| | |
|---|---|
| **Purpose** | For each routed action item (all items include "jira"), create a Jira ticket via the Jira REST API. |
| **Inputs** | Routed `action_items` from state. |
| **Outputs** | Each item updated with `jira_ticket_id`, `jira_ticket_url`, `status: "jira_created"`. Errors logged to `processing_errors`. |
| **MVP?** | Mandatory. |
| **Type** | **Deterministic tool node.** Loop over items, call Jira API, handle errors per-item. Supports DRY_RUN mode. |

### Node 6: `send_slack_notifications`

| | |
|---|---|
| **Purpose** | Post action items to a shared Slack channel thread with AI-generated contextual summaries and "Mark Complete" buttons. |
| **Inputs** | `action_items` with Jira (and optionally GitHub) info populated. `transcript` for context. |
| **Outputs** | Each item updated with `slack_summary`, `slack_message_ts`, `status: "notified"`. `slack_channel_id` and `slack_thread_ts` set on `MeetingState`. |
| **MVP?** | Mandatory. |
| **Type** | **LLM-powered + tool node.** One LLM call generates contextual summaries for all items (batched). Then posts a thread header + one reply per action item using Slack Block Kit. |

**LLM generates per item (2-3 sentences):**
- What was discussed in the meeting that led to this task
- What the assignee needs to do
- Any relevant context from the discussion

**Slack thread structure:**
```
[Thread header] Meeting: {meeting_title} — {meeting_date}
  ├── @assignee1: {AI-generated summary} | Jira: PROJ-123 | Priority: high | [Mark Complete]
  ├── @assignee2: {AI-generated summary} | Jira: PROJ-124 | Branch: feature/PROJ-124-... | [Mark Complete]
  └── @assignee3: {AI-generated summary} | Jira: PROJ-125 | Priority: medium | [Mark Complete]
```

### Node 7: `create_github_branches`

| | |
|---|---|
| **Purpose** | For action items routed to GitHub, create a feature branch from main. |
| **Inputs** | `action_items` where `"github"` in `tools_to_invoke`. `jira_ticket_id` for branch naming. |
| **Outputs** | Each GitHub-routed item updated with `github_branch_name`, `github_branch_url`. |
| **MVP?** | Mandatory (this is what proves routing works). |
| **Type** | **Deterministic tool node.** One API call per item: `POST /repos/{owner}/{repo}/git/refs`. Supports DRY_RUN mode. |

**Branch naming:** `feature/{jira_ticket_id}-{slugified-title}` (e.g., `feature/PROJ-124-migrate-auth-service`)

### Handler 8: `handle_slack_completion` (separate from graph)

| | |
|---|---|
| **Purpose** | When user clicks "Mark Complete" in Slack, transition the Jira ticket to Done and update the Slack message. |
| **Inputs** | Slack interaction payload (contains `action_item.id` and `jira_ticket_id` in button value). |
| **Outputs** | Jira ticket transitioned. Slack message updated to show completion (strikethrough + checkmark). |
| **MVP?** | Mandatory for full loop. |
| **Type** | **Deterministic.** Not part of the main graph. A standalone webhook endpoint. |

## 8. Recommended Execution Pattern

### Two separate flows, not one graph with a long-lived wait.

**Flow A: Main processing graph (7 nodes with fan-out)**

```
[extract_action_items] → [resolve_assignees] → [human_review (interrupt)] → [route_action_items] → ┬─[create_jira_tickets]───┐
                                                                                                     ├─[send_slack_notifications]┤→ END
                                                                                                     └─[create_github_branches]──┘
```

Triggered by: transcript submission (CLI command initially, Slack slash command later).

The graph runs synchronously until `human_review`, where it pauses via `interrupt()`. When the human confirms, the graph resumes: the router tags items, then the three tool nodes execute in parallel (or sequentially if parallel adds complexity — the graph topology should still show the fan-out).

**Important execution order note:** `create_jira_tickets` should complete before `send_slack_notifications` and `create_github_branches` begin, because Slack messages need Jira links and GitHub branches are named after Jira tickets. The actual execution is:

```
route → create_jira_tickets → [send_slack_notifications, create_github_branches] → END
```

Jira first (it produces IDs needed by the others), then Slack and GitHub in parallel.

**Flow B: Slack completion handler (standalone)**

```
Slack interaction webhook → look up action item → transition Jira ticket → update Slack message
```

Triggered by: Slack interactive component callback. Not a LangGraph graph.

### Why two flows

The main graph completes in minutes. Slack callbacks arrive hours or days later. A separate webhook handler is simpler and easier to debug.

### Graph definition

```python
from langgraph.graph import StateGraph, START, END

builder = StateGraph(MeetingState)

# Nodes
builder.add_node("extract_action_items", extract_action_items_node)
builder.add_node("resolve_assignees", resolve_assignees_node)
builder.add_node("human_review", human_review_node)
builder.add_node("route_action_items", route_action_items_node)
builder.add_node("create_jira_tickets", create_jira_tickets_node)
builder.add_node("send_slack_notifications", send_slack_notifications_node)
builder.add_node("create_github_branches", create_github_branches_node)

# Linear flow through review and routing
builder.add_edge(START, "extract_action_items")
builder.add_edge("extract_action_items", "resolve_assignees")
builder.add_edge("resolve_assignees", "human_review")
builder.add_edge("human_review", "route_action_items")

# Jira must complete first (produces IDs needed downstream)
builder.add_edge("route_action_items", "create_jira_tickets")

# Fan-out: Slack and GitHub run after Jira, in parallel
builder.add_edge("create_jira_tickets", "send_slack_notifications")
builder.add_edge("create_jira_tickets", "create_github_branches")

# Both fan-out branches converge to END
builder.add_edge("send_slack_notifications", END)
builder.add_edge("create_github_branches", END)

graph = builder.compile(
    checkpointer=checkpointer,
    interrupt_before=["human_review"]
)
```

Seven nodes, fan-out after Jira creation, one interrupt. The Mermaid visualization shows the branching structure.

## 9. Tool and Integration Strategy

### Meeting transcript input

- **Mechanism**: The system accepts a transcript as a string. No meeting platform API.
- **Format**: Plain text or markdown.
- **Entry point**: CLI invocation initially (`python run.py --transcript path/to/file.txt`). Add a Slack slash command (`/process-meeting`) later.
- **When called**: This is the trigger that starts the graph.

### Jira

- **API**: Jira REST API v3 (Cloud) or v2 (Server). Use `requests` directly or `python-jira`.
- **Required API interactions (3 total)**:
  1. **Create issue** (`POST /rest/api/3/issue`): Called once per confirmed action item. Fields: project key, summary, description, assignee (Jira account ID), issue type (Task), labels (from tags).
  2. **Transition issue** (`POST /rest/api/3/issue/{id}/transitions`): Called on Slack "Mark Complete" click. Moves issue to Done.
  3. **Get transitions** (`GET /rest/api/3/issue/{id}/transitions`): Optional. Discover the "Done" transition ID if not hardcoded.
- **Auth**: API token + email (Cloud) or PAT (Server). Environment variables.
- **When called**: After routing (create), on Slack button click (transition).
- **DRY_RUN**: When enabled, logs the API call that would be made without executing it.

### Slack

- **API**: Slack Web API + Slack Interactivity (Block Kit).
- **Required API interactions (4 total)**:
  1. **Post message** (`chat.postMessage`): Post the meeting thread header to `#meeting-actions` channel.
  2. **Post thread reply** (`chat.postMessage` with `thread_ts`): Post each action item as a threaded reply, tagged with assignee, including Block Kit "Mark Complete" button.
  3. **Handle interactive action** (incoming webhook): Receive button clicks. Extract Jira issue key, trigger transition.
  4. **Update message** (`chat.update`): Update the thread reply to show task as completed.
- **Auth**: Bot token (`xoxb-`). Environment variable.
- **Slack app setup**: One app with bot token scopes (`chat:write`, `commands`), interactivity URL pointed at backend. One channel (`#meeting-actions`) precreated.
- **When called**: Notifications posted after Jira tickets created; button clicks trigger Jira updates.

### GitHub

- **API**: GitHub REST API.
- **Required API interactions (2 total)**:
  1. **Get ref** (`GET /repos/{owner}/{repo}/git/ref/heads/main`): Get the SHA of main branch.
  2. **Create ref** (`POST /repos/{owner}/{repo}/git/refs`): Create feature branch from that SHA.
- **Auth**: Personal access token or GitHub App token. Environment variable.
- **When called**: After Jira ticket creation, only for items where `"github"` in `tools_to_invoke`.
- **Config**: Repository owner/name in config file. One repo for MVP.
- **DRY_RUN**: When enabled, logs the branch that would be created without executing.

## 10. Minimal Architecture

### One service, one graph

```
+------------------------------------------------------------------+
|  Single Python service (FastAPI)                                  |
|                                                                   |
|  Endpoints:                                                       |
|    POST /slack/commands    ← Slack slash command (later)          |
|    POST /slack/interact    ← Slack button clicks                  |
|                                                                   |
|  CLI entry point:                                                 |
|    python run.py --transcript <file>                              |
|                                                                   |
|  LangGraph orchestration:                                         |
|    [extract] → [resolve] → [confirm] → [route] → [jira] → ┬[slack] |
|                                                             └[github]|
|                                                                   |
|  Direct integrations:                                             |
|    - Jira REST API (via requests)                                 |
|    - Slack Web API (via slack_sdk)                                |
|    - GitHub REST API (via requests)                               |
|    - Anthropic / OpenAI API (for LLM calls)                      |
+------------------------------------------------------------------+
```

### Persistence

- **LangGraph checkpointer**: `MemorySaver` (in-memory) for MVP. Sufficient for one team.
- **No database.** Jira is the system of record. Slack messages are the notification record.
- **Config file**: YAML or JSON mapping team members to Jira/Slack IDs, plus GitHub repo info and Jira project key.

### Deployment

- One process. Run anywhere: local machine, VM, or container.
- FastAPI handles Slack webhooks. LangGraph runs in-process.
- Use `ngrok` or Slack Socket Mode for local development.

### What this architecture intentionally does not have

- No message queue or event bus
- No separate worker processes
- No database
- No caching layer
- No auth layer (single-operator, API keys in env vars)
- No custom frontend
- No agent-style tool calling — every node does exactly one thing
- No retry/resilience logic beyond basic try/except
- No LLM-based routing (tags + rules are sufficient)

## 11. Step-by-Step Implementation Plan

Phases are logical build order, not calendar time. This is a hackathon build.

### Phase 1: Extract + resolve + human review

**Objective:** Given a meeting transcript, produce a structured list of action items with tags and resolved assignees.

**Key tasks:**
- Define the `ActionItem` and `MeetingState` schemas (TypedDict/Pydantic)
- Build the `extract_action_items` node: single LLM call, structured output with tags, few-shot examples including engineering vs. non-engineering tasks
- Build the `resolve_assignees` node: deterministic lookup against hardcoded team roster
- Build the `human_review` node: CLI prompt showing items with tags and routing preview
- Wire into a LangGraph `StateGraph`: `extract_action_items` → `resolve_assignees` → `human_review`
- Create the team roster config file (`team.yaml`)

**Deliverable:** Runnable script that takes a transcript and outputs confirmed, tagged action items.

**Demo:** Paste a transcript, see action items extracted with correct tags (engineering vs. non-engineering), review and confirm.

### Phase 2: Routing + Jira + GitHub

**Objective:** Route action items and prove the fan-out — engineering tasks get branches, others don't.

**Key tasks:**
- Build the `route_action_items` node: deterministic tag-based routing
- Build the `create_jira_tickets` node: iterate items, call Jira REST API, store issue keys
- Build the `create_github_branches` node: for GitHub-routed items, create feature branches named after Jira tickets
- Wire the fan-out: `route_action_items` → `create_jira_tickets` → `create_github_branches`
- Implement DRY_RUN mode for both Jira and GitHub
- Set up config for Jira project and GitHub repo

**Deliverable:** Transcript → tagged items → Jira tickets for all + GitHub branches for engineering items only.

**Demo:** Show that engineering tasks produce both Jira tickets and GitHub branches, while non-engineering tasks produce only Jira tickets. The routing is visible.

### Phase 3: Slack notifications + completion loop

**Objective:** AI-generated Slack messages in a shared thread + completion webhook.

**Key tasks:**
- Build the `send_slack_notifications` node: LLM call for contextual summaries, post thread to `#meeting-actions` with per-item replies
- Wire the full fan-out: `create_jira_tickets` → [`send_slack_notifications`, `create_github_branches`] → END
- Build the `handle_slack_completion` webhook handler
- Set up FastAPI server with Slack interactivity endpoint
- Set up `#meeting-actions` channel and Slack app

**Deliverable:** Full notification flow with AI-generated messages + completion loop.

**Demo:** Shared Slack thread shows all tasks with contextual summaries. Engineering tasks include branch links. Click "Mark Complete" → Jira ticket closes.

### Phase 4: End-to-end wiring + dry-run verification

**Objective:** Full pipeline working end-to-end with real APIs.

**Key tasks:**
- Wire all phases together into the complete graph
- Run end-to-end with DRY_RUN to verify flow
- Run end-to-end with real APIs against test Jira project, Slack channel, and GitHub repo
- Verify graph visualization (`draw_mermaid()`) shows the fan-out structure
- Verify logging captures each node's input/output for debugging

**Deliverable:** Complete, working MVP.

**Demo:** Full cycle with a real transcript: extraction → review → routing → Jira + GitHub + Slack → completion → Jira closed. Graph visualization shows the branching topology.

## 12. Risks, Caveats, and Simplifications

### Risk: LLM extraction quality is inconsistent
Action items and tags extracted from transcripts will vary. Vague transcripts produce vague tasks with wrong tags.
**Fix:** Rigid output schema + 3–4 few-shot examples (including examples of engineering vs. non-engineering tagging). Human review catches misclassifications. If a tag is wrong, the human fixes it before routing executes.

### Risk: Routing logic is too simple
The rule-based router (tag + keyword matching) may not cover all cases.
**Fix:** This is intentional for MVP. If coverage is insufficient, improve the extraction prompt to produce better tags — don't add an LLM routing node. The extraction LLM is where the intelligence belongs.

### Risk: GitHub branch creation fails
Branch names may conflict, or the repo may not be accessible.
**Fix:** DRY_RUN mode for testing. Slugify branch names and truncate to Git limits. Log errors to `processing_errors` and continue — a failed branch should not block Jira or Slack.

### LangGraph mistakes to avoid
- **Using agents where a function call suffices.** Jira, Slack, and GitHub integrations are deterministic API calls, not agents.
- **Modeling Slack completion as part of the graph.** The graph runs once per transcript. The callback is a separate event handler.
- **Over-abstracting tool management.** No "tool registry" — just call APIs directly in each node.
- **Complex state management.** One TypedDict with a list of action items. No state machine within the state machine.
- **LLM-based routing.** The router is `if/else` on tags. Resist the urge to make it an LLM call.
- **Per-item sub-graphs.** Fan-out over items happens inside nodes. The graph-level fan-out is tool-type parallelism.

### Caveat: Assignee resolution is brittle
Matching transcript names to Jira/Slack IDs is fuzzy. Hardcoded roster handles 80% of cases.
**Fix:** Human review is the safety net. Flag unresolved or low-confidence assignees.

### Caveat: Slack interactivity requires a public URL
**Fix:** Use Slack Socket Mode for development (avoids needing a public URL).

### Simplification: No persistence layer
Graph state lives in memory. Process crash = re-run from transcript.
**Fix:** Acceptable for MVP. LangGraph's SQLite checkpointer is the upgrade path.

### Simplification: No retry logic
API failure = node failure = run failure.
**Fix:** Wrap API calls in try/except with per-item error logging. A single item's failure should not block the others.

## 13. MVP Acceptance Criteria

Pass/fail criteria for a successful proof of concept:

1. **Transcript to action items:** Given a sample transcript (10+ minutes, 3+ action items including at least one engineering task), the system extracts action items with title, description, suggested assignee, and tags. Captures ≥80% of items a human would identify.

2. **Assignee resolution:** Extracted names are matched to Jira/Slack IDs via roster lookup. Unresolved assignees are flagged.

3. **Human review gate:** Before any downstream action, the system presents extracted items with tags and routing preview for confirmation. Human can edit tags, reassign, remove, or approve. No downstream actions without explicit approval.

4. **Routing works:** Given a transcript with both engineering and non-engineering tasks, engineering tasks are routed to Jira + Slack + GitHub. Non-engineering tasks are routed to Jira + Slack only. Routing decisions are visible in state.

5. **Jira ticket creation:** For each confirmed item, a Jira issue is created with correct summary, description, assignee, and labels. Verified on the Jira board.

6. **GitHub branches exist:** For engineering-tagged items, a feature branch exists in the target repo with the naming convention `feature/{JIRA-ID}-{slug}`. Non-engineering items have no branches.

7. **AI-generated Slack messages are contextual:** Slack messages reference what was actually discussed in the meeting, not just the task title. Each message is a 2-3 sentence contextual summary.

8. **Group visibility:** All action items from one meeting are visible in a shared Slack channel thread (`#meeting-actions`). Assignees can see each other's tasks. Engineering tasks include branch links.

9. **Completion loop:** Clicking "Mark Complete" transitions the Jira issue to Done and updates the Slack message. Verified end-to-end.

10. **Graph shows fan-out:** `graph.get_graph().draw_mermaid()` shows the branching structure after the router node, not a straight line.

11. **Inspectable:** Each node's input/output can be logged for debugging.

12. **Single-command execution:** The pipeline runs from: `python run.py --transcript path/to/transcript.txt`.

## 14. Final Recommendation

**Build this graph:**

```
extract_action_items → resolve_assignees → human_review → route_action_items → create_jira_tickets → ┬─ send_slack_notifications ─┐
                                                                                                      └─ create_github_branches ──┘→ END
```

Seven nodes, fan-out after Jira, one interrupt, deterministic routing, two LLM calls (extraction + Slack summaries). The routing and fan-out are what make this a LangGraph project rather than a script.

Run the Slack completion callback as a separate FastAPI endpoint. It is not part of the graph.

**Shortest path to demo:**
1. Get extraction working with tags on 2–3 sample transcripts (Phase 1)
2. Wire routing + Jira + GitHub — prove engineering tasks get branches, others don't (Phase 2)
3. Wire Slack with AI-generated messages + completion webhook (Phase 3)
4. End-to-end with real APIs (Phase 4)

### What was changed from the original sketch

| Original sketch item | Decision | Reason |
|---|---|---|
| Decision/routing layer | **Restored — deterministic, tag-based** | This is the core intelligence. Without routing, every item is identical and LangGraph adds no value. |
| GitHub branch creation | **Restored — minimal, branch only** | ~30 lines. Makes routing visible in the demo. |
| AI-generated Slack messages | **Restored** | Template messages are indistinguishable from a Jira webhook. The LLM adds visible value here. |
| Group notification | **Restored — shared channel thread** | Team context. Assignees see each other's tasks. |
| Parallel fan-out | **Restored** | Jira first (produces IDs), then Slack + GitHub in parallel. This is the LangGraph pattern worth demoing. |
| Live meeting listening | **Still cut** | Post-meeting only. Biggest complexity cut. |
| Multi-agent coordination | **Still cut** | Centralized orchestrator with specialist nodes. No agent loops. |
| Per-item human confirmation | **Still cut** | Batch review is faster and simpler. |
