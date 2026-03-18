"""LLM interaction wrapper using langchain-openai ChatOpenAI."""

import json
import os
import uuid

from src.models import ActionItem


def _is_dry_run() -> bool:
    return os.environ.get("DRY_RUN", "true").lower() == "true"


def call_extraction_llm(transcript: str, prompt_template: str) -> list[ActionItem]:
    """Single LLM call with structured output. Returns list of ActionItem dicts."""
    if _is_dry_run():
        print("[DRY_RUN] call_extraction_llm: returning 2 fake action items")
        return [
            ActionItem(
                id=str(uuid.uuid4()),
                title="Refactor auth service to OAuth2",
                description="Refactor the authentication service to use OAuth2 as discussed in the meeting.",
                assignee_name="Alice",
                assignee_jira_id=None,
                assignee_slack_id=None,
                priority="high",
                tags=["engineering", "backend"],
                tools_to_invoke=[],
                status="extracted",
                jira_ticket_id=None,
                jira_ticket_url=None,
                github_branch_name=None,
                github_branch_url=None,
                slack_summary=None,
                slack_message_ts=None,
            ),
            ActionItem(
                id=str(uuid.uuid4()),
                title="Update Q3 marketing deck",
                description="Add new customer logos to the Q3 marketing presentation before Friday.",
                assignee_name="Bob",
                assignee_jira_id=None,
                assignee_slack_id=None,
                priority="medium",
                tags=["marketing"],
                tools_to_invoke=[],
                status="extracted",
                jira_ticket_id=None,
                jira_ticket_url=None,
                github_branch_name=None,
                github_branch_url=None,
                slack_summary=None,
                slack_message_ts=None,
            ),
        ]

    from langchain_openai import ChatOpenAI

    api_key = os.environ["OPENAI_API_KEY"]
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    llm = ChatOpenAI(model=model, api_key=api_key, temperature=0)
    prompt = prompt_template.format(transcript=transcript)
    response = llm.invoke(prompt)

    # Parse the JSON response
    content = response.content
    # Strip markdown code fences if present
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0]
    elif "```" in content:
        content = content.split("```")[1].split("```")[0]

    data = json.loads(content.strip())
    items: list[ActionItem] = []
    for raw in data.get("action_items", []):
        items.append(
            ActionItem(
                id=str(uuid.uuid4()),
                title=raw["title"],
                description=raw["description"],
                assignee_name=raw["assignee_name"],
                assignee_jira_id=None,
                assignee_slack_id=None,
                priority=raw["priority"],
                tags=raw.get("tags", []),
                tools_to_invoke=[],
                status="extracted",
                jira_ticket_id=None,
                jira_ticket_url=None,
                github_branch_name=None,
                github_branch_url=None,
                slack_summary=None,
                slack_message_ts=None,
            )
        )
    return items


def call_summary_llm(
    items: list[ActionItem], transcript: str, prompt_template: str
) -> list[str]:
    """Single LLM call returning one summary string per item."""
    if _is_dry_run():
        print("[DRY_RUN] call_summary_llm: returning mock summaries")
        return [f"[DRY_RUN] Summary for: {item['title']}" for item in items]

    from langchain_openai import ChatOpenAI

    api_key = os.environ["OPENAI_API_KEY"]
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    llm = ChatOpenAI(model=model, api_key=api_key, temperature=0)

    # Build action items JSON for the prompt
    items_for_prompt = [
        {
            "title": item["title"],
            "description": item["description"],
            "assignee_name": item["assignee_name"],
            "priority": item["priority"],
            "tags": item["tags"],
        }
        for item in items
    ]

    prompt = prompt_template.format(
        transcript=transcript,
        action_items=json.dumps(items_for_prompt, indent=2),
    )
    response = llm.invoke(prompt)

    content = response.content
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0]
    elif "```" in content:
        content = content.split("```")[1].split("```")[0]

    summaries = json.loads(content.strip())
    return summaries
