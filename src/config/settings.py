from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv
import os

load_dotenv()

_ROSTER_PATH = Path(__file__).resolve().parent / "team_roster.yaml"


def _load_roster() -> list:
    """Load the team roster from the YAML config file."""
    if _ROSTER_PATH.exists():
        with open(_ROSTER_PATH, "r") as f:
            data = yaml.safe_load(f)
            return data.get("members", []) if data else []
    return []


@dataclass
class Settings:
    openai_api_key: str = ""
    jira_base_url: str = ""
    jira_api_token: str = ""
    jira_user_email: str = ""
    jira_project_key: str = "PROJ"
    slack_bot_token: str = ""
    slack_channel_id: str = ""
    github_token: str = ""
    github_repo_owner: str = ""
    github_repo_name: str = ""
    dry_run: bool = True
    roster: list = field(default_factory=list)


def _build_settings() -> Settings:
    """Build Settings from environment variables and roster file."""
    dry_run_raw = os.environ.get("DRY_RUN", "true")
    dry_run = dry_run_raw.lower() in ("true", "1", "yes")

    return Settings(
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        jira_base_url=os.environ.get("JIRA_BASE_URL", ""),
        jira_api_token=os.environ.get("JIRA_API_TOKEN", ""),
        jira_user_email=os.environ.get("JIRA_USER_EMAIL", ""),
        jira_project_key=os.environ.get("JIRA_PROJECT_KEY", "PROJ"),
        slack_bot_token=os.environ.get("SLACK_BOT_TOKEN", ""),
        slack_channel_id=os.environ.get("SLACK_CHANNEL_ID", ""),
        github_token=os.environ.get("GITHUB_TOKEN", ""),
        github_repo_owner=os.environ.get("GITHUB_REPO_OWNER", ""),
        github_repo_name=os.environ.get("GITHUB_REPO_NAME", ""),
        dry_run=dry_run,
        roster=_load_roster(),
    )


settings = _build_settings()
