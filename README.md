# auto-meet

`auto-meet` turns a meeting transcript into reviewed action items, Jira tickets, GitHub branches for engineering work, and Slack updates.

## What it does

- reads a meeting transcript
- extracts action items
- lets you review or edit them before anything is created
- creates Jira tickets
- creates GitHub branches for engineering tasks
- posts Slack notifications
- can close Jira tickets from a Slack `Mark Complete` button

## Architecture

![Logo](./arch-diagram.png)

## Quick setup

### 1. Install dependencies

```bash
cd ~/Desktop/devhack26
pip3 install -r requirements.txt
```

### 2. Choose how you want to run it

#### Simple local test

Create a `.env` file with:

```env
DRY_RUN=true
```

This runs the pipeline in mock mode and does not call real APIs.

#### Real run

Copy the example file:

```bash
cp .env.example .env
```

Then replace the values in `.env` with your own:

```env
OPENAI_API_KEY=...
JIRA_BASE_URL=https://yourorg.atlassian.net
JIRA_API_TOKEN=...
JIRA_USER_EMAIL=you@example.com
JIRA_PROJECT_KEY=KAN
SLACK_BOT_TOKEN=xoxb-...
SLACK_CHANNEL_ID=C0XXXXXXXX
GITHUB_TOKEN=ghp_...
GITHUB_REPO_OWNER=your-name
GITHUB_REPO_NAME=your-repo
DRY_RUN=false
```

Your Slack app should have `chat:write`, your GitHub token should be able to create branches, and the GitHub repo should already have a `main` branch.

### 3. Update the team roster

Edit `src/config/team_roster.yaml`.

The names in the transcript should match the people listed in the roster. Each person needs a Jira account ID and a Slack member ID.

```yaml
members:
  - name: "Tyler Brent"
    variants: ["tyler", "tyler b"]
    jira_id: "your-jira-account-id"
    slack_id: "U0XXXXXXXX"
```

## Run the app

### Run with the sample transcript

```bash
python3 main.py --transcript tests/fixtures/sample_transcript.txt
```

### Run with your own transcript

```bash
python3 main.py --transcript path/to/your_transcript.txt
```

The CLI will stop and ask:

```text
Approve these action items? (Y/n/edit):
```

- `Y` continues
- `n` stops
- `edit` lets you paste updated JSON before continuing

## Project structure

- `main.py` - CLI entry point
- `server.py` - Slack webhook server for the `Mark Complete` button
- `src/graph/` - LangGraph workflow nodes, prompts, and graph builder
- `src/integrations/` - Jira, Slack, GitHub, and LLM integrations
- `src/config/` - environment loading and team roster
- `tests/` - tests and sample transcript fixtures

## Optional Slack button setup

Only do this if you want Slack button clicks to close Jira tickets.

### 1. Start the webhook server

```bash
python3 -m uvicorn server:app --port 8000
```

### 2. Expose it with ngrok

```bash
ngrok http 8000
```

### 3. Set the Slack interactivity URL

In your Slack app, set the Request URL to:

```text
https://YOUR-NGROK-URL/slack/interact
```

## Notes

- `DRY_RUN=true` is the easiest way to test the flow.
- In dry-run mode, extraction and Slack summaries are mocked.
- The checked-in dry-run mock items use names like `Alice` and `Bob`, so unresolved assignee warnings in dry-run mode are expected unless your roster includes those names.
