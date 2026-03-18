"""FastAPI server for Slack interaction webhooks."""

import json

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request

app = FastAPI(title="Meeting-to-Tasks Webhook Server")


@app.post("/slack/interact")
async def slack_interact(request: Request):
    """Handle Slack interactive component callbacks (e.g., 'Mark Complete' button)."""
    # Slack sends form-encoded payload
    form = await request.form()
    payload = json.loads(form.get("payload", "{}"))

    # Extract action info from button value
    actions = payload.get("actions", [])
    if not actions:
        return {"ok": True}

    action_value = json.loads(actions[0].get("value", "{}"))
    action_item_id = action_value.get("action_item_id")  # noqa: F841
    jira_ticket_id = action_value.get("jira_ticket_id")
    channel_id = payload.get("channel", {}).get("id", "")
    message_ts = payload.get("message", {}).get("ts", "")

    # Call contracts to transition Jira and update Slack
    from src.contracts import transition_jira_to_done, update_slack_message_done

    transition_jira_to_done(jira_ticket_id)
    update_slack_message_done(channel_id, message_ts)

    return {"ok": True}
