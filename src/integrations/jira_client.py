"""Jira REST API integration using requests."""

import base64
import os

from src.models import ActionItem


def _is_dry_run() -> bool:
    return os.environ.get("DRY_RUN", "true").lower() == "true"


def _get_auth_header() -> dict[str, str]:
    email = os.environ["JIRA_USER_EMAIL"]
    token = os.environ["JIRA_API_TOKEN"]
    credentials = base64.b64encode(f"{email}:{token}".encode()).decode()
    return {
        "Authorization": f"Basic {credentials}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def create_jira_ticket(item: ActionItem, project_key: str) -> tuple[str, str]:
    """Create a Jira issue. Returns (ticket_id, ticket_url). Supports DRY_RUN."""
    if _is_dry_run():
        short_id = item["id"][:4]
        ticket_id = f"DRY-{short_id}"
        ticket_url = f"https://dry-run.atlassian.net/browse/DRY-{short_id}"
        print(f"[DRY_RUN] create_jira_ticket: would create ticket for '{item['title']}' in project {project_key}")
        print(f"[DRY_RUN]   assignee: {item.get('assignee_jira_id')}, priority: {item['priority']}, tags: {item['tags']}")
        return (ticket_id, ticket_url)

    import requests

    base_url = os.environ["JIRA_BASE_URL"].rstrip("/")
    headers = _get_auth_header()

    payload = {
        "fields": {
            "project": {"key": project_key},
            "summary": item["title"],
            "description": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {"type": "text", "text": item["description"]},
                        ],
                    }
                ],
            },
            "issuetype": {"name": "Task"},
            "labels": [t.replace(" ", "-") for t in item.get("tags", [])],
        }
    }

    if item.get("assignee_jira_id"):
        payload["fields"]["assignee"] = {"accountId": item["assignee_jira_id"]}

    resp = requests.post(f"{base_url}/rest/api/3/issue", json=payload, headers=headers)
    resp.raise_for_status()
    data = resp.json()
    ticket_id = data["key"]
    ticket_url = f"{base_url}/browse/{ticket_id}"
    return (ticket_id, ticket_url)


def transition_jira_to_done(ticket_id: str) -> bool:
    """Transition a Jira issue to Done. Returns True on success. Supports DRY_RUN."""
    if _is_dry_run():
        print(f"[DRY_RUN] transition_jira_to_done: would transition {ticket_id} to Done")
        return True

    import requests

    base_url = os.environ["JIRA_BASE_URL"].rstrip("/")
    headers = _get_auth_header()

    # First, get available transitions to find "Done"
    resp = requests.get(
        f"{base_url}/rest/api/3/issue/{ticket_id}/transitions",
        headers=headers,
    )
    resp.raise_for_status()
    transitions = resp.json().get("transitions", [])

    done_transition_id = None
    for t in transitions:
        if t["name"].lower() == "done":
            done_transition_id = t["id"]
            break

    if not done_transition_id:
        print(f"Warning: no 'Done' transition found for {ticket_id}. Available: {[t['name'] for t in transitions]}")
        return False

    resp = requests.post(
        f"{base_url}/rest/api/3/issue/{ticket_id}/transitions",
        json={"transition": {"id": done_transition_id}},
        headers=headers,
    )
    resp.raise_for_status()
    return True
