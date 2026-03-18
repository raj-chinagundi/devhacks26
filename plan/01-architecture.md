# Architecture: Meeting-to-Tasks MVP

## 1. Plain-English Restatement

This system takes a meeting transcript after the meeting ends, extracts action items from it using an LLM, and pushes those action items into Jira and Slack so nothing falls through the cracks. The MVP proves that a LangGraph orchestrator can reliably bridge the gap between "things people said in a meeting" and "tracked work with owners," with minimal human oversight at the ambiguous parts.

## 2. MVP Goal

**Success for the first demo:** A user pastes or uploads a meeting transcript. The system extracts action items, asks a human to confirm/correct assignees and task descriptions, then creates Jira tickets and sends Slack DMs to each assignee with a summary. When an assignee clicks "Done" in Slack, the corresponding Jira ticket is closed.

That's it. If that loop works end-to-end for one real meeting with 3-5 action items, the MVP is proven.

GitHub integration is out of scope for the first demo. Add it only after the core loop is solid.

## 3. LangGraph Design Recommendation

### Graph Shape

**Linear pipeline with one human-in-the-loop checkpoint and one external callback re-entry point.**

Not branching. Not cyclic. Not multi-agent. The core flow is:

```
Ingest -> Extract -> [Human Review] -> Route+Create -> Notify -> (wait) -> Close
```

The only "branching" is fan-out: after human review, each confirmed action item gets a Jira ticket and a Slack notification. This is a simple loop within a node, not graph-level branching.

The Slack "mark complete" callback is the one part that doesn't fit a pure linear pipeline. Handle it as a separate minimal graph (or a single handler) triggered by a Slack interaction event, not as a cycle in the main graph.

### Minimal Node Set

Five nodes in the primary graph, plus one separate handler:

1. **`ingest`** -- Parse and store the transcript. Deterministic.
2. **`extract_action_items`** -- LLM-powered. The only node that truly needs an LLM.
3. **`human_review`** -- Human-in-the-loop checkpoint. Pauses graph execution. Human confirms/edits extracted items and assignees.
4. **`create_jira_tickets`** -- Deterministic tool node. Iterates over confirmed action items, creates Jira tickets, writes ticket IDs back to state.
5. **`send_slack_notifications`** -- Deterministic tool node. Sends a DM per action item using a template (not LLM-generated -- a formatted message is fine for MVP).

Separate handler (not part of the main graph):

6. **`handle_slack_completion`** -- Triggered by Slack interactive callback. Looks up the Jira ticket ID from state/store, transitions the ticket to Done.

### What State Is Passed Through the Graph

A single `MeetingState` TypedDict flows through all nodes. See Section 4 for the exact model.

### Deterministic Routing vs. LLM Reasoning

| Decision | Approach | Rationale |
|---|---|---|
| Extracting action items from transcript | **LLM** | This is genuinely unstructured -- no way around it. |
| Inferring assignees from transcript | **LLM** (within the extraction node) | Names/roles in transcripts are messy. But the human review checkpoint catches errors. |
| Deciding which tools to invoke per item | **Deterministic** | Every confirmed action item gets a Jira ticket and a Slack notification. Period. No routing decision needed for MVP. |
| Generating Slack message content | **Deterministic template** | A formatted message with task title, description, assignee, and Jira link is sufficient. No LLM needed. |
| Closing Jira on Slack callback | **Deterministic** | Direct API call. |

**Key opinion:** The "decision layer" from the original sketch (step 3) is unnecessary for MVP. Every action item gets the same treatment: Jira + Slack. Remove it. If you later need items that skip Jira or route to GitHub, add a simple rule-based router then. Do not build a routing agent.

### Human-in-the-Loop Checkpoints

**One checkpoint: after extraction, before any tool calls.**

This is where the human reviews:
- Were the right action items extracted? (Remove false positives, add missed items.)
- Are assignees correct? (The LLM's best guess may be wrong.)
- Are task descriptions reasonable?

Use LangGraph's built-in `interrupt()` mechanism. The graph pauses, the human edits state via a review UI or CLI prompt, and the graph resumes with the corrected state.

No other checkpoints are needed for MVP. Do not add confirmation before each individual Jira ticket -- that defeats the purpose.

### Preventing Graph Complexity Growth

Rules:
1. **No agent delegation.** Nodes call tools directly; they do not spawn sub-agents.
2. **No dynamic tool selection.** The tool set is hardcoded per node.
3. **No cycles in the main graph.** If you need retries, handle them inside the node with a simple try/except, not as graph edges.
4. **Fan-out over action items happens inside nodes, not as graph topology.** Do not create one sub-graph per action item.
5. **The Slack completion callback is a separate entry point**, not a cycle back into the main graph. This is critical -- trying to model "wait for Slack button click" as a graph edge will make the graph undebuggable.

### Centralized Orchestrator vs. Multi-Agent

**Centralized orchestrator with specialist nodes. Not multi-agent.**

Reasons:
- There is exactly one LLM call in the entire flow (extraction). Everything else is deterministic tool calls or templates.
- "Agents" imply autonomy and decision-making. The only decision here is "what are the action items?" -- a single LLM call with structured output.
- Multi-agent adds coordination overhead, makes debugging harder, and provides zero benefit when the workflow is linear.
- The nodes are plain workflow nodes, except `extract_action_items` which is a single LLM invocation (not an agent loop -- one call, structured output, done).

**No node in this graph should be an agent with a tool-calling loop.** If extraction needs to be refined, the human review step handles that. Do not let the LLM iterate on its own output.

## 4. Suggested LangGraph State Model

```python
from typing import TypedDict, Literal
from dataclasses import dataclass, field

class ActionItem(TypedDict):
    id: str                          # Generated UUID
    title: str                       # Short task title
    description: str                 # 1-2 sentence description
    assignee_name: str               # Extracted from transcript
    assignee_slack_id: str | None    # Resolved after human review or lookup
    priority: Literal["high", "medium", "low"]
    status: Literal["extracted", "confirmed", "jira_created", "notified", "done"]
    jira_ticket_id: str | None       # e.g., "PROJ-123"
    jira_ticket_url: str | None
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

    # Control flags
    human_review_complete: bool      # Set to True after human confirms
    processing_errors: list[str]     # Collect errors, don't crash
```

**What's intentionally excluded:**
- No summary field. The transcript is short enough for context; summarization is a separate feature, not MVP.
- No tool routing decisions. Every item gets the same treatment.
- No GitHub references. Out of scope.
- No approval flags per item. The human review is all-or-nothing: confirm the full batch, or edit and confirm.
- No conversation memory or agent scratchpad. There's one LLM call; it doesn't need memory.

## 5. Recommended Agent/Node Set

### Node 1: `ingest`

| | |
|---|---|
| **Purpose** | Parse raw transcript input, extract meeting metadata (title, date, participants if available), populate initial state. |
| **Inputs** | Raw transcript text (from user upload or API call). |
| **Outputs** | `MeetingState` with `meeting_id`, `meeting_title`, `meeting_date`, `participants`, `transcript` populated. |
| **MVP?** | Mandatory. |
| **Type** | Deterministic. Simple parsing -- regex or string splitting. If transcripts come in a structured format (e.g., from a transcription service API), just map fields. If plain text, do minimal best-effort parsing. |

### Node 2: `extract_action_items`

| | |
|---|---|
| **Purpose** | Call an LLM to identify action items from the transcript. Return structured output. |
| **Inputs** | `transcript`, `participants` from state. |
| **Outputs** | `action_items` list populated with `status: "extracted"`. |
| **MVP?** | Mandatory. |
| **Type** | LLM-powered. Single LLM call with structured output (use `with_structured_output` or a Pydantic model). Not an agent loop. Prompt should include participant names to help with assignee extraction. |

**Implementation note:** Use a focused prompt that asks for: task title, description, assignee name (from the participant list), and priority. Return as a JSON list. Do not let the LLM reason about tool routing or downstream actions.

### Node 3: `human_review`

| | |
|---|---|
| **Purpose** | Pause execution. Present extracted action items to a human for confirmation/editing. |
| **Inputs** | `action_items` from state. |
| **Outputs** | Updated `action_items` (human may edit titles, reassign, delete items, add items). `human_review_complete: True`. |
| **MVP?** | Mandatory. |
| **Type** | Human-in-the-loop interrupt. Uses LangGraph's `interrupt()`. For MVP, the review interface can be a CLI prompt or a simple web form -- doesn't matter. |

### Node 4: `create_jira_tickets`

| | |
|---|---|
| **Purpose** | For each confirmed action item, create a Jira ticket via the Jira REST API. |
| **Inputs** | Confirmed `action_items` from state. |
| **Outputs** | Each `ActionItem` updated with `jira_ticket_id`, `jira_ticket_url`, `status: "jira_created"`. |
| **MVP?** | Mandatory. |
| **Type** | Deterministic tool node. Simple loop: for each item, call Jira API, store the result. Handle errors per-item (log to `processing_errors`, continue with remaining items). |

### Node 5: `send_slack_notifications`

| | |
|---|---|
| **Purpose** | Send a Slack DM to each assignee with their task details and a "Mark Complete" button. |
| **Inputs** | `action_items` with Jira ticket info populated. |
| **Outputs** | Each `ActionItem` updated with `slack_message_ts`, `status: "notified"`. |
| **MVP?** | Mandatory. |
| **Type** | Deterministic tool node. Template-based message. Slack Block Kit for the interactive button. |

**Message template (not LLM-generated):**
```
New task from meeting: {meeting_title}
*{action_item.title}*
{action_item.description}
Priority: {action_item.priority}
Jira: {action_item.jira_ticket_url}
[Mark Complete]
```

### Handler 6: `handle_slack_completion`

| | |
|---|---|
| **Purpose** | When a user clicks "Mark Complete" in Slack, transition the Jira ticket to Done and update the Slack message. |
| **Inputs** | Slack interaction payload (contains `action_item.id` and `jira_ticket_id` embedded in the button value). |
| **Outputs** | Jira ticket transitioned. Slack message updated to show completion. |
| **MVP?** | Mandatory for the full loop. Can be deferred to second iteration if needed. |
| **Type** | Deterministic. Not part of the main graph. A standalone Slack event handler (webhook endpoint) that makes two API calls: Jira transition + Slack message update. |

## 6. Recommended Execution Pattern

### Two separate flows, not one graph with a long-lived wait.

**Flow A: Main processing graph (5 nodes)**

```
[ingest] -> [extract_action_items] -> [human_review (interrupt)] -> [create_jira_tickets] -> [send_slack_notifications]
```

Triggered by: transcript submission (API call, CLI command, or webhook from a transcription service).

The graph runs synchronously until `human_review`, where it pauses via `interrupt()`. When the human submits their review, the graph resumes and completes. Total wall-clock time for the automated parts: seconds. Human review: whenever they get to it.

**Flow B: Slack completion handler (standalone)**

```
Slack interaction webhook -> look up action item -> transition Jira ticket -> update Slack message
```

Triggered by: Slack interactive component callback (HTTP POST from Slack).

This is not a LangGraph graph. It's a simple webhook handler -- a single function. Using LangGraph here would add complexity for zero benefit. The handler needs access to the mapping of `action_item.id` -> `jira_ticket_id`, which can be stored in a simple key-value store, a database row, or LangGraph's built-in persistence (if you're using a checkpointer, you can look up the completed graph state by `meeting_id`).

### Why two flows instead of one graph with a long wait

The main graph completes in minutes. The Slack callbacks arrive hours or days later. Trying to keep a graph execution alive waiting for an external event adds complexity (you need durable execution, long-lived checkpoints, callback routing into the graph). For MVP, a separate webhook handler is simpler, easier to debug, and works fine.

If you later want to track overall meeting completion (all items done), add a simple check in the Slack handler: after closing a ticket, query whether all items for that meeting are now done, and if so, post a summary to a Slack channel.

### Step-by-step runtime

1. **Trigger:** User submits transcript via API/CLI.
2. **`ingest`:** Parses transcript, creates `MeetingState`, generates `meeting_id`.
3. **`extract_action_items`:** LLM call extracts action items with structured output. Writes `action_items` to state.
4. **`human_review`:** Graph pauses. Human is presented with extracted items (via CLI, web UI, or Slack message). Human edits and confirms. Graph resumes.
5. **`create_jira_tickets`:** Iterates over confirmed items, creates tickets, stores IDs in state.
6. **`send_slack_notifications`:** Iterates over items, sends DMs with Jira links and "Mark Complete" buttons.
7. **Graph complete.** State is persisted (via LangGraph checkpointer) for later reference.
8. **(Later) Slack callback:** User clicks "Mark Complete." Webhook handler fires, transitions Jira ticket, updates Slack message.

### Graph definition sketch

```python
from langgraph.graph import StateGraph, START, END

builder = StateGraph(MeetingState)

builder.add_node("ingest", ingest_node)
builder.add_node("extract_action_items", extract_action_items_node)
builder.add_node("human_review", human_review_node)
builder.add_node("create_jira_tickets", create_jira_tickets_node)
builder.add_node("send_slack_notifications", send_slack_notifications_node)

builder.add_edge(START, "ingest")
builder.add_edge("ingest", "extract_action_items")
builder.add_edge("extract_action_items", "human_review")
builder.add_edge("human_review", "create_jira_tickets")
builder.add_edge("create_jira_tickets", "send_slack_notifications")
builder.add_edge("send_slack_notifications", END)

graph = builder.compile(checkpointer=checkpointer, interrupt_before=["human_review"])
```

That's the entire graph. Five nodes, five edges, one interrupt, zero conditional routing.

### What was cut and why

| Original sketch item | Decision | Reason |
|---|---|---|
| Decision/routing layer per action item | **Cut** | Every item gets Jira + Slack. No routing needed. |
| GitHub branch creation | **Cut from MVP** | Adds integration complexity for marginal demo value. Add in iteration 2. |
| LLM-generated Slack messages | **Cut** | Template is clearer, faster, and more predictable. |
| Multi-agent coordination | **Cut** | One LLM call, four deterministic steps. No agents needed. |
| AI-generated summary | **Cut** | The extracted action item descriptions are the summary. A separate summary step is redundant for MVP. |
| Per-item human confirmation | **Cut** | Batch review is faster and simpler. |
