import os
import re
import uuid
from pathlib import Path

import yaml
from langgraph.types import interrupt

from src.models import MeetingState
from src.contracts import (
    extract_items_from_transcript,
    resolve_assignee,
    create_jira_ticket,
    create_github_branch,
    generate_slack_summaries,
    post_slack_thread,
)

_ROSTER_PATH = Path(__file__).resolve().parent.parent / "config" / "team_roster.yaml"


def _load_roster() -> dict:
    with open(_ROSTER_PATH, "r") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Node 1: extract_action_items
# ---------------------------------------------------------------------------
def extract_action_items_node(state: MeetingState) -> dict:
    """Call LLM to extract action items from the transcript."""
    transcript = state["transcript"]
    items = extract_items_from_transcript(transcript)

    meeting_id = str(uuid.uuid4())

    # Ensure every item has status "extracted"
    for item in items:
        item["status"] = "extracted"

    return {
        "meeting_id": meeting_id,
        "action_items": items,
    }


# ---------------------------------------------------------------------------
# Node 2: resolve_assignees
# ---------------------------------------------------------------------------
def resolve_assignees_node(state: MeetingState) -> dict:
    """Resolve assignee names to Jira/Slack IDs via team roster."""
    roster = _load_roster()
    items = state["action_items"]
    errors: list[str] = list(state.get("processing_errors", []))
    updated_items = []

    for item in items:
        jira_id, slack_id = resolve_assignee(item["assignee_name"], roster)
        updated = {**item}
        updated["assignee_jira_id"] = jira_id
        updated["assignee_slack_id"] = slack_id
        updated["status"] = "resolved"
        if jira_id is None or slack_id is None:
            errors.append(
                f"Could not resolve assignee '{item['assignee_name']}' for item '{item['title']}'"
            )
        updated_items.append(updated)

    return {
        "action_items": updated_items,
        "processing_errors": errors,
    }


# ---------------------------------------------------------------------------
# Node 3: human_review
# ---------------------------------------------------------------------------
def human_review_node(state: MeetingState) -> dict:
    """Pause for human review using LangGraph interrupt."""
    items = state["action_items"]

    for item in items:
        is_engineering = (
            "engineering" in item["tags"]
            or _has_engineering_keyword(item["description"])
        )
        tools = ["jira", "slack", "github"] if is_engineering else ["jira", "slack"]
        print(f"\n  - [{item['priority'].upper()}] {item['title']}")
        print(f"    Assignee: {item['assignee_name']}")
        print(f"    Tags: {item['tags']}")
        print(f"    Tools: {tools}")

    # Interrupt — the interrupt value is the action items for review
    interrupt(items)

    # After resume, mark items confirmed
    updated_items = []
    for item in state["action_items"]:
        updated = {**item, "status": "confirmed"}
        updated_items.append(updated)

    return {
        "action_items": updated_items,
        "human_review_complete": True,
    }


# ---------------------------------------------------------------------------
# Node 4: route_action_items
# ---------------------------------------------------------------------------
def _has_engineering_keyword(text: str) -> bool:
    """Check for engineering keywords using word-boundary matching."""
    engineering_keywords = [
        "code", "repo", "branch", "deploy", "merge", "refactor", "bug fix",
        r"\bPR\b",
    ]
    text_lower = text.lower()
    for kw in engineering_keywords:
        if r"\b" in kw:
            if re.search(kw, text, re.IGNORECASE):
                return True
        else:
            if re.search(r"\b" + re.escape(kw) + r"\b", text_lower):
                return True
    return False


def route_action_items_node(state: MeetingState) -> dict:
    """Deterministic routing based on tags and keywords."""
    updated_items = []

    for item in state["action_items"]:
        is_engineering = (
            "engineering" in item["tags"]
            or _has_engineering_keyword(item["description"])
        )
        if is_engineering:
            tools = ["jira", "slack", "github"]
        else:
            tools = ["jira", "slack"]

        updated = {**item, "tools_to_invoke": tools, "status": "routed"}
        updated_items.append(updated)

    return {"action_items": updated_items}


# ---------------------------------------------------------------------------
# Node 5: create_jira_tickets
# ---------------------------------------------------------------------------
def create_jira_tickets_node(state: MeetingState) -> dict:
    """Create Jira tickets for all routed items."""
    project_key = os.environ.get("JIRA_PROJECT_KEY", "PROJ")
    errors: list[str] = list(state.get("processing_errors", []))
    updated_items = []

    for item in state["action_items"]:
        updated = {**item}
        try:
            ticket_id, ticket_url = create_jira_ticket(item, project_key)
            updated["jira_ticket_id"] = ticket_id
            updated["jira_ticket_url"] = ticket_url
            updated["status"] = "jira_created"
        except Exception as exc:
            errors.append(f"Jira creation failed for '{item['title']}': {exc}")
        updated_items.append(updated)

    return {
        "action_items": updated_items,
        "processing_errors": errors,
    }


# ---------------------------------------------------------------------------
# Node 6: send_slack_notifications
# ---------------------------------------------------------------------------
def send_slack_notifications_node(state: MeetingState) -> dict:
    """Generate AI summaries and post Slack thread."""
    channel_id = os.environ.get("SLACK_CHANNEL_ID", "C0001")
    items = state["action_items"]
    transcript = state["transcript"]
    errors: list[str] = list(state.get("processing_errors", []))

    # One LLM call for all summaries
    try:
        summaries = generate_slack_summaries(items, transcript)
    except Exception as exc:
        errors.append(f"Slack summary generation failed: {exc}")
        summaries = ["" for _ in items]

    # Attach summaries to items
    updated_items = []
    for i, item in enumerate(items):
        updated = {**item}
        updated["slack_summary"] = summaries[i] if i < len(summaries) else ""
        updated_items.append(updated)

    # Post thread
    try:
        thread_ts, message_ts_list = post_slack_thread(
            channel_id,
            state.get("meeting_title", "Meeting"),
            state.get("meeting_date", "unknown"),
            updated_items,
        )
    except Exception as exc:
        errors.append(f"Slack posting failed: {exc}")
        thread_ts = None
        message_ts_list = []

    # Attach message timestamps
    for i, item in enumerate(updated_items):
        item["slack_message_ts"] = message_ts_list[i] if i < len(message_ts_list) else None
        item["status"] = "notified"

    return {
        "action_items": updated_items,
        "slack_channel_id": channel_id,
        "slack_thread_ts": thread_ts,
        "processing_errors": errors,
    }


# ---------------------------------------------------------------------------
# Node 7: create_github_branches
# ---------------------------------------------------------------------------
def create_github_branches_node(state: MeetingState) -> dict:
    """Create GitHub branches for engineering-routed items."""
    repo_owner = os.environ.get("GITHUB_REPO_OWNER", "org")
    repo_name = os.environ.get("GITHUB_REPO_NAME", "repo")
    errors: list[str] = list(state.get("processing_errors", []))
    updated_items = []

    for item in state["action_items"]:
        updated = {**item}
        if "github" in item.get("tools_to_invoke", []):
            try:
                branch_name, branch_url = create_github_branch(item, repo_owner, repo_name)
                updated["github_branch_name"] = branch_name
                updated["github_branch_url"] = branch_url
            except Exception as exc:
                errors.append(f"GitHub branch failed for '{item['title']}': {exc}")
        updated_items.append(updated)

    return {
        "action_items": updated_items,
        "processing_errors": errors,
    }
