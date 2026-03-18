from typing import Annotated, TypedDict, Literal


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
    status: Literal[
        "extracted", "resolved", "confirmed", "routed",
        "jira_created", "notified", "done"
    ]
    jira_ticket_id: str | None       # e.g., "PROJ-123"
    jira_ticket_url: str | None
    github_branch_name: str | None   # e.g., "feature/PROJ-123-task-title-slug"
    github_branch_url: str | None
    slack_summary: str | None        # LLM-generated contextual message
    slack_message_ts: str | None     # For updating the Slack message later


def _merge_action_items(
    existing: list[ActionItem], updates: list[ActionItem]
) -> list[ActionItem]:
    """Merge action items by id — updates win for any field that changed.

    This reducer is required because the parallel fan-out after
    create_jira_tickets means send_slack_notifications and
    create_github_branches both write to action_items concurrently.
    """
    if not existing:
        return updates
    if not updates:
        return existing

    merged: dict[str, ActionItem] = {item["id"]: dict(item) for item in existing}  # type: ignore[misc]
    for item in updates:
        item_id = item["id"]
        if item_id in merged:
            # Merge: update fields that are non-None in the incoming item
            base = merged[item_id]
            for key, value in item.items():
                if value is not None or key not in base:
                    base[key] = value
            merged[item_id] = base
        else:
            merged[item_id] = dict(item)  # type: ignore[misc]
    return list(merged.values())


def _merge_errors(existing: list[str], updates: list[str]) -> list[str]:
    """Append-only merge for processing errors from parallel branches."""
    seen = set(existing)
    result = list(existing)
    for err in updates:
        if err not in seen:
            result.append(err)
            seen.add(err)
    return result


class MeetingState(TypedDict):
    # Meeting metadata
    meeting_id: str
    meeting_title: str
    meeting_date: str
    participants: list[str]          # Names extracted from transcript

    # Transcript
    transcript: str                  # Raw transcript text

    # Extracted work — uses reducer for parallel fan-out merge
    action_items: Annotated[list[ActionItem], _merge_action_items]

    # Slack context
    slack_channel_id: str | None     # Channel where notifications are posted
    slack_thread_ts: str | None      # Thread timestamp for this meeting's items

    # Control flags
    human_review_complete: bool
    processing_errors: Annotated[list[str], _merge_errors]
