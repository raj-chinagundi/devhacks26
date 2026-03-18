"""Slack Web API integration using requests."""

import json
import os

from src.models import ActionItem


def _is_dry_run() -> bool:
    return os.environ.get("DRY_RUN", "true").lower() == "true"


def _get_headers() -> dict[str, str]:
    token = os.environ["SLACK_BOT_TOKEN"]
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }


def _build_item_blocks(item: ActionItem) -> list[dict]:
    """Build Slack Block Kit blocks for a single action item message."""
    assignee_mention = f"<@{item['assignee_slack_id']}>" if item.get("assignee_slack_id") else item["assignee_name"]
    summary_text = item.get("slack_summary") or item["description"]

    # Main text section
    text_parts = [f"{assignee_mention}: {summary_text}"]
    if item.get("jira_ticket_url"):
        text_parts.append(f"*Jira:* <{item['jira_ticket_url']}|{item.get('jira_ticket_id', 'ticket')}>")
    text_parts.append(f"*Priority:* {item['priority']}")
    if item.get("github_branch_url"):
        text_parts.append(f"*Branch:* <{item['github_branch_url']}|{item.get('github_branch_name', 'branch')}>")

    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "\n".join(text_parts),
            },
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Mark Complete"},
                    "style": "primary",
                    "action_id": "mark_complete",
                    "value": json.dumps(
                        {
                            "action_item_id": item["id"],
                            "jira_ticket_id": item.get("jira_ticket_id"),
                        }
                    ),
                }
            ],
        },
    ]
    return blocks


def post_slack_thread(
    channel_id: str,
    meeting_title: str,
    meeting_date: str,
    items: list[ActionItem],
) -> tuple[str, list[str]]:
    """Post a thread header + one reply per item to Slack. Returns (thread_ts, [message_ts])."""
    if _is_dry_run():
        print(f"[DRY_RUN] post_slack_thread: would post to channel {channel_id}")
        print(f"[DRY_RUN]   header: Meeting: {meeting_title} - {meeting_date}")
        for i, item in enumerate(items):
            print(f"[DRY_RUN]   reply {i}: {item['title']} -> {item.get('assignee_name')}")
        return ("dry-thread-ts", [f"dry-msg-ts-{i}" for i in range(len(items))])

    import requests

    headers = _get_headers()
    slack_api = "https://slack.com/api"

    # Post thread header
    header_payload = {
        "channel": channel_id,
        "text": f"Meeting: {meeting_title} - {meeting_date}",
    }
    resp = requests.post(f"{slack_api}/chat.postMessage", json=header_payload, headers=headers)
    resp.raise_for_status()
    header_data = resp.json()
    if not header_data.get("ok"):
        raise RuntimeError(f"Slack API error: {header_data.get('error')}")
    thread_ts = header_data["ts"]

    # Post one reply per item
    message_ts_list: list[str] = []
    for item in items:
        blocks = _build_item_blocks(item)
        assignee_mention = f"<@{item['assignee_slack_id']}>" if item.get("assignee_slack_id") else item["assignee_name"]
        summary_text = item.get("slack_summary") or item["description"]
        fallback_text = f"{assignee_mention}: {summary_text}"

        reply_payload = {
            "channel": channel_id,
            "thread_ts": thread_ts,
            "text": fallback_text,
            "blocks": blocks,
        }
        resp = requests.post(f"{slack_api}/chat.postMessage", json=reply_payload, headers=headers)
        resp.raise_for_status()
        reply_data = resp.json()
        if not reply_data.get("ok"):
            raise RuntimeError(f"Slack API error: {reply_data.get('error')}")
        message_ts_list.append(reply_data["ts"])

    return (thread_ts, message_ts_list)


def update_slack_message_done(channel_id: str, message_ts: str) -> bool:
    """Update a Slack message to show task completed. Returns True on success."""
    if _is_dry_run():
        print(f"[DRY_RUN] update_slack_message_done: would update message {message_ts} in channel {channel_id}")
        return True

    import requests

    headers = _get_headers()
    slack_api = "https://slack.com/api"

    payload = {
        "channel": channel_id,
        "ts": message_ts,
        "text": "~Task completed~ :white_check_mark:",
    }
    resp = requests.post(f"{slack_api}/chat.update", json=payload, headers=headers)
    resp.raise_for_status()
    data = resp.json()
    return data.get("ok", False)
