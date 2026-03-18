# Meeting-to-Tasks MVP — Setup & Run Guide

## What This Does

Takes a meeting transcript, extracts action items using OpenAI, routes them to Jira/Slack/GitHub based on task type, and lets users mark tasks complete in Slack which closes the Jira ticket.

## Prerequisites

- Python 3.10+
- ngrok (`brew install ngrok`)
- A Jira Cloud project
- A Slack workspace with a bot app
- A GitHub repo

## 1. Environment Setup

```bash
cd ~/Desktop/devhack26
cp .env.example .env
```

Fill in `.env` with real values. Key fields:

| Variable | Where to get it |
|----------|----------------|
| OPENAI_API_KEY | OpenAI dashboard |
| JIRA_BASE_URL | e.g. `https://devhacks.atlassian.net` |
| JIRA_API_TOKEN | Atlassian account → Security → API tokens |
| JIRA_USER_EMAIL | Your Atlassian email |
| JIRA_PROJECT_KEY | The project key (e.g. `KAN`) |
| SLACK_BOT_TOKEN | Slack app → OAuth & Permissions → Bot User OAuth Token (`xoxb-...`) |
| SLACK_CHANNEL_ID | Right-click channel → View channel details → scroll to bottom for ID |
| GITHUB_TOKEN | GitHub → Settings → Developer settings → PATs → generate with `repo` scope |
| GITHUB_REPO_OWNER | e.g. `raj-chinagundi` |
| GITHUB_REPO_NAME | e.g. `devhacks-demo-repo` |
| DRY_RUN | `false` for real execution, `true` for mock |

## 2. Team Roster Setup

Edit `src/config/team_roster.yaml` with real user info:

```yaml
members:
  - name: "Tyler Brent"
    variants: ["tyler", "tyler b"]
    jira_id: "712020:5b271fd4-22c8-4587-a864-1861beb7c1b6"
    slack_id: "U0AMDU3VBP0"
```

### How to get Jira account ID

Use the Jira API to search by email:

```bash
curl -s -u "$JIRA_USER_EMAIL:$JIRA_API_TOKEN" \
  "https://YOUR-ORG.atlassian.net/rest/api/3/user/search?query=USER_EMAIL"
```

The `accountId` field in the response is what you need.

### How to get Slack member ID

In Slack: click the user's profile → three dots (⋯) → **Copy member ID**. Looks like `U07XXXXXXXX`.

## 3. Slack App Setup

Go to https://api.slack.com/apps → create or select your app.

### Required Bot Token Scopes (OAuth & Permissions)

- `chat:write` — post messages
- `commands` — slash commands (optional)

### Invite bot to channel

In your Slack channel, type:

```
/invite @YourBotName
```

### Interactivity (for "Mark Complete" button)

This is needed for the completion loop (Step 6 below). You can skip this for the initial run and come back to it.

1. Go to your Slack app → **Interactivity & Shortcuts**
2. Toggle **On**
3. Set Request URL to: `https://YOUR-NGROK-URL/slack/interact`
4. Save

## 4. GitHub Repo Setup

- The repo must exist and have a `main` branch
- The PAT needs `repo` scope (classic) or `contents:write` (fine-grained)
- The app creates feature branches like `feature/KAN-5-fix-password-reset-link` for engineering-tagged tasks

## 5. Running the App

### Transcript

Edit `tests/fixtures/sample_transcript.txt` with your meeting transcript. Use real participant names that match the roster.

### Run

```bash
python3 main.py --transcript tests/fixtures/sample_transcript.txt
```

What happens:
1. OpenAI extracts action items with tags from the transcript
2. Assignees are resolved against the roster
3. You see a review screen with routing preview:
   - Engineering tasks → `['jira', 'slack', 'github']`
   - Non-engineering tasks → `['jira', 'slack']`
4. Press `Y` to approve
5. Jira tickets are created for all items
6. GitHub branches are created for engineering items
7. Slack thread is posted with AI-generated summaries and "Mark Complete" buttons

### Verify after run

- **Jira**: Check your board for new tickets (e.g. KAN-8, KAN-9)
- **GitHub**: Check repo branches for `feature/KAN-X-...`
- **Slack**: Check your channel for the thread with all tasks

## 6. Completion Loop (Mark Complete → Close Jira)

This makes the Slack "Mark Complete" button work.

### Terminal 1: Start the webhook server

```bash
cd ~/Desktop/devhack26
python3 -m uvicorn server:app --port 8000
```

### Terminal 2: Start ngrok

```bash
ngrok http 8000
```

Copy the forwarding URL (e.g. `https://xxxxx.ngrok-free.dev`).

### Set Slack interactivity URL

1. Go to https://api.slack.com/apps → your app → **Interactivity & Shortcuts**
2. Toggle **On**
3. Request URL: `https://YOUR-NGROK-URL/slack/interact`
4. Save

### Test it

1. Go to the Slack channel
2. Click "Mark Complete" on a task
3. The Jira ticket should transition to Done
4. The Slack message should update to show completion

## 7. Graph Visualization

Generate the graph as PNG:

```bash
python3 -c "from src.graph.builder import graph; open('graph.png','wb').write(graph.get_graph().draw_mermaid_png())"
```

## 8. Running Tests

```bash
DRY_RUN=true python3 -m pytest tests/ -x --tb=short -v
```

## 9. Dry Run Mode

Set `DRY_RUN=true` in `.env` to test without hitting any real APIs. All integrations will log what they would do and return fake data.

## 10. Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `KeyError: '\n "meeting_title"'` | Prompt template has unescaped `{}`| Already fixed — `{{}}` in prompts.py |
| `400 Bad Request` on Jira | Labels with spaces (e.g. "bug fix") | Already fixed — spaces replaced with hyphens |
| `not_in_channel` on Slack | Bot not in the channel | `/invite @BotName` in the channel |
| `"repo"` matching `"report"` | Substring keyword matching | Already fixed — uses word-boundary regex |
| GitHub branch says `UNKNOWN` | Jira ticket creation failed first | Fix the Jira error, branch needs the ticket ID |
| Slack message missing branch link | Slack posted before GitHub finished | Already fixed — GitHub runs before Slack now |
| DRY_RUN not respected | `.env` not loaded before env check | Already fixed — `load_dotenv()` in main.py |

## Architecture

```
extract_action_items → resolve_assignees → human_review (interrupt)
    → route_action_items → create_jira_tickets → create_github_branches
    → send_slack_notifications → END

Separate: Slack "Mark Complete" → server.py → Jira transition + Slack update
```

- 7 graph nodes, 2 LLM calls (extraction + Slack summaries)
- Routing is deterministic (tag + keyword based, not LLM)
- Human review checkpoint before any actions
- Jira is system of record
