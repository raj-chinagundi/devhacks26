# Implementation Plan: Meeting-to-Tasks MVP

## 1. Step-by-step implementation plan

### Phase 1: Extract and structure (Days 1-2)

**Objective:** Given a meeting transcript, produce a structured list of action items.

**Key tasks:**
- Define the `ActionItem` schema: `title`, `description`, `assignee_raw` (string from transcript), `assignee_resolved` (Jira user, nullable), `priority` (low/medium/high), `tags` (list of strings, e.g. `["engineering"]`).
- Build the `extract_action_items` node: single LLM call with a tightly constrained prompt that returns structured JSON. Use Pydantic for output parsing. No chain-of-thought agents, no multi-step extraction -- one prompt, one call, structured output.
- Build the `resolve_assignees` node: deterministic lookup against a hardcoded team roster (dict mapping name variants to Jira user IDs). Flag unresolved assignees for human review.
- Build the `human_review` node: for the MVP, this is a CLI prompt or a simple JSON file the user edits before continuing. Do not build a web UI. This node pauses the graph and waits for confirmation of the extracted action items (especially assignees).
- Wire these into a LangGraph `StateGraph` with the flow: `extract_action_items` -> `resolve_assignees` -> `human_review`.

**Deliverable:** A runnable script that takes a transcript file and outputs a confirmed list of action items as structured data.

**Demo:** Paste a sample transcript, get back a clean JSON list of action items with assignees.

---

### Phase 2: Jira + Slack integration (Days 3-5)

**Objective:** Create Jira tickets from confirmed action items and notify assignees via Slack.

**Key tasks:**
- Build the `create_jira_tickets` node: iterate over confirmed action items, call Jira REST API to create issues. Store the returned issue key on each action item in graph state. Use `requests` directly -- no Jira SDK unless it genuinely saves time.
- Build the `send_slack_notifications` node: for each action item, send a Slack message to the assignee's channel/DM with: task summary, Jira link, and a "Mark Complete" button (Slack Block Kit interactive message).
- Add a team config file (`team.yaml` or `team.json`): maps each person to their Jira user ID and Slack user ID. This is the single source of truth for routing. Keep it flat and simple.
- Add a `route_action_items` node (conditional edge): this is deterministic, not LLM-based. Every action item gets a Jira ticket and a Slack notification. No fancy routing logic needed for MVP -- the "decision layer" from the original sketch collapses to "always do both." If an action item has no resolved assignee, skip Slack and log a warning.
- Extend the graph: `human_review` -> `create_jira_tickets` -> `send_slack_notifications`.

**Deliverable:** End-to-end flow from transcript to Jira tickets + Slack DMs.

**Demo:** Run the pipeline on a transcript, show tickets appearing in Jira, show Slack messages arriving with correct summaries and links.

---

### Phase 3: Slack completion loop (Days 6-7)

**Objective:** When a user clicks "Mark Complete" in Slack, close the Jira ticket.

**Key tasks:**
- Build a lightweight Slack event listener (Flask or FastAPI endpoint) that receives Slack interactivity payloads when a user clicks the "Mark Complete" button.
- On button click: call Jira REST API to transition the issue to "Done" (or your board's equivalent closed status). Update the Slack message to show the task as completed.
- This is **not** a LangGraph node. It's a standalone webhook handler. Do not try to model this as a graph re-entry or a long-running graph. The graph's job is done after Phase 2. The completion loop is a simple request handler.

**Deliverable:** Clicking "Mark Complete" in Slack closes the Jira ticket and updates the Slack message.

**Demo:** Show the full cycle: transcript -> action items -> Jira ticket -> Slack notification -> click complete -> Jira ticket closed.

---

### Phase 4 (Optional/Deferred): GitHub integration

**Objective:** For engineering-tagged tasks, create a branch or stub PR.

**Tasks:**
- Add a conditional check in the graph: if `"engineering"` in `action_item.tags`, call GitHub API to create a branch named after the Jira key.
- This is one additional API call inside or after the `create_jira_tickets` node. It does not need its own node.

**Recommendation:** Skip this for the initial demo. It adds integration complexity for minimal POC value. Build it only if you have time left and the demo audience cares.

---

## 2. Risks, caveats, and simplifications

### Risk: LLM extraction quality is inconsistent
Action items extracted from transcripts will vary in quality. Vague transcripts produce vague tasks.
**Fix:** Use a rigid output schema. Include 3-4 few-shot examples in the extraction prompt covering common edge cases (implicit tasks, unclear assignees, multi-part action items). Accept that extraction won't be perfect -- the human review step catches the rest.

### Risk: Overengineering the LangGraph structure
The original sketch implies a "decision layer" node that routes action items to different tools. This is unnecessary for MVP. Every action item gets a Jira ticket and a Slack message. There is no routing decision to make.
**Fix:** Remove the decision/routing node entirely. If you later need conditional routing (e.g., some items go to Asana instead), add a conditional edge at that point.

### Common LangGraph mistakes to avoid:
- **Too many nodes.** The graph should have 4-5 nodes max, not 10+. Each node should do one concrete thing. If you're creating a node for "parse LLM output" separate from "call LLM," merge them.
- **Using agents where a function call suffices.** The Jira and Slack integrations are deterministic API calls. They are nodes (plain functions), not agents. Do not give an LLM the ability to "decide" how to call the Jira API.
- **Modeling the Slack completion callback as part of the graph.** The graph runs once, synchronously, per transcript. The Slack callback is a separate, independent event handler. Trying to keep the graph "alive" waiting for Slack events adds massive complexity for no gain.
- **Over-abstracting tool management.** Do not build a "tool registry" or "tool executor" abstraction. Just call the APIs directly in each node function.
- **Complex state management.** The graph state should be a single TypedDict with a list of action items and some metadata. Do not build a state machine within the state machine.

### Caveat: Assignee resolution is brittle
Matching transcript names ("John said he'd handle it") to Jira/Slack user IDs is inherently fuzzy. The hardcoded roster with name variants handles 80% of cases.
**Fix:** The human review step is the safety net. Flag any unresolved or low-confidence assignees. Do not try to solve this with a more complex NLP pipeline.

### Caveat: Slack interactivity requires a public URL
The "Mark Complete" button needs Slack to POST to your server. For local development, use ngrok or Slack's socket mode.
**Fix:** Use Slack Socket Mode for development. It avoids the need for a public URL entirely.

### Simplification: No persistence layer
Graph state lives in memory for the duration of a single run. There is no database. If the process crashes mid-run, you re-run from the transcript.
**Fix:** This is fine for MVP. If you need run history later, LangGraph's built-in checkpointing with SQLite is the simplest path.

### Simplification: No retry logic
If the Jira or Slack API call fails, the node fails and the run fails.
**Fix:** Acceptable for POC. Wrap API calls in a simple try/except with logging so you know what failed.

---

## 3. MVP acceptance criteria

These are pass/fail criteria for a successful proof of concept:

1. **Transcript to action items:** Given a sample meeting transcript (minimum 10 minutes, 3+ action items), the system extracts action items with title, description, and attempted assignee. Extraction captures at least 80% of action items a human would identify.

2. **Human review gate:** Before any downstream action, the system presents extracted items for human confirmation. The human can edit, remove, or approve items. No tickets are created without explicit approval.

3. **Jira ticket creation:** For each confirmed action item, a Jira issue is created in the target project with the correct summary, description, and assignee. Verified by checking the Jira board.

4. **Slack notification:** For each action item with a resolved assignee, a Slack message is sent to that user containing: task summary, Jira issue link, and a "Mark Complete" button. Verified by checking the Slack channel/DM.

5. **Completion loop:** Clicking "Mark Complete" in Slack transitions the corresponding Jira issue to Done and updates the Slack message to reflect completion. Verified end-to-end.

6. **Inspectable graph:** The LangGraph graph can be visualized (using `graph.get_graph().draw_mermaid()` or equivalent) and each node's input/output can be logged for debugging.

7. **Single-command execution:** The full pipeline (excluding the Slack callback server) runs from a single CLI command: `python run.py --transcript path/to/transcript.txt`.

---

## 4. Final recommendation

**Build this graph first:**

```
extract_action_items -> resolve_assignees -> human_review -> create_jira_tickets -> send_slack_notifications
```

Five nodes, linear flow, no conditional edges, no parallelism, no agents. The only LLM call is in `extract_action_items`. Everything else is deterministic Python.

Run the Slack completion callback as a separate FastAPI/Flask server with one endpoint. It is not part of the graph.

**Drop from v1:** GitHub integration, the "decision layer" routing node, any form of persistence or retry logic, any web UI for human review (use CLI or file-based review).

**Shortest path to demo:**
1. Get the extraction prompt working with 2-3 sample transcripts (day 1).
2. Wire Jira ticket creation with hardcoded test data, then connect it to extraction output (day 2-3).
3. Wire Slack notifications and the completion webhook (day 4-5).
4. Polish the human review step and do an end-to-end run (day 6).
5. Demo on day 7.

The entire system should be under 500 lines of Python (excluding config/prompts). If it's significantly more, you're overbuilding.
