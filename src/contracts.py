from src.models import ActionItem


def extract_items_from_transcript(transcript: str) -> list[ActionItem]:
    """Call LLM to extract structured action items with tags from a meeting transcript."""
    from src.integrations.llm import call_extraction_llm
    from src.graph.prompts import EXTRACTION_PROMPT
    return call_extraction_llm(transcript, EXTRACTION_PROMPT)


def resolve_assignee(name: str, roster: dict) -> tuple[str | None, str | None]:
    """Resolve an assignee name to (jira_id, slack_id) using the team roster.

    Roster format: {"members": [{"name": ..., "variants": [...], "jira_id": ..., "slack_id": ...}]}
    """
    name_lower = name.lower().strip()
    members = roster.get("members", [])

    # Exact name match
    for member in members:
        if member["name"].lower().strip() == name_lower:
            return (member["jira_id"], member["slack_id"])

    # Variant match
    for member in members:
        for variant in member.get("variants", []):
            if variant.lower().strip() == name_lower:
                return (member["jira_id"], member["slack_id"])

    # Partial / substring match (e.g., "Alice" matches "Alice Johnson")
    for member in members:
        if name_lower in member["name"].lower() or member["name"].lower() in name_lower:
            return (member["jira_id"], member["slack_id"])
        for variant in member.get("variants", []):
            if name_lower in variant.lower() or variant.lower() in name_lower:
                return (member["jira_id"], member["slack_id"])

    return (None, None)


def create_jira_ticket(item: ActionItem, project_key: str) -> tuple[str, str]:
    """Create a Jira issue. Returns (ticket_id, ticket_url). Supports DRY_RUN."""
    from src.integrations.jira_client import create_jira_ticket as _create
    return _create(item, project_key)


def create_github_branch(item: ActionItem, repo_owner: str, repo_name: str) -> tuple[str, str]:
    """Create a feature branch from main. Returns (branch_name, branch_url). Supports DRY_RUN."""
    from src.integrations.github_client import create_github_branch as _create
    return _create(item, repo_owner, repo_name)


def generate_slack_summaries(items: list[ActionItem], transcript: str) -> list[str]:
    """Call LLM to generate a contextual 2-3 sentence summary per action item."""
    from src.integrations.llm import call_summary_llm
    from src.graph.prompts import SLACK_SUMMARY_PROMPT
    return call_summary_llm(items, transcript, SLACK_SUMMARY_PROMPT)


def post_slack_thread(
    channel_id: str,
    meeting_title: str,
    meeting_date: str,
    items: list[ActionItem],
) -> tuple[str, list[str]]:
    """Post a thread header + one reply per item to Slack. Returns (thread_ts, [message_ts]). Supports DRY_RUN."""
    from src.integrations.slack_client import post_slack_thread as _post
    return _post(channel_id, meeting_title, meeting_date, items)


def transition_jira_to_done(ticket_id: str) -> bool:
    """Transition a Jira issue to Done. Returns True on success. Supports DRY_RUN."""
    from src.integrations.jira_client import transition_jira_to_done as _transition
    return _transition(ticket_id)


def update_slack_message_done(channel_id: str, message_ts: str) -> bool:
    """Update a Slack message to show task completed. Returns True on success. Supports DRY_RUN."""
    from src.integrations.slack_client import update_slack_message_done as _update
    return _update(channel_id, message_ts)
