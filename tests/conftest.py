"""Pytest fixtures for Meeting-to-Tasks tests."""

import os
from pathlib import Path

import pytest
import yaml

from src.models import ActionItem, MeetingState

_ROSTER_PATH = Path(__file__).resolve().parent.parent / "src" / "config" / "team_roster.yaml"
_TRANSCRIPT_PATH = Path(__file__).resolve().parent / "fixtures" / "sample_transcript.txt"


@pytest.fixture
def sample_action_items() -> list[ActionItem]:
    """Four realistic ActionItems: 2 engineering, 2 non-engineering."""
    return [
        ActionItem(
            id="item-1",
            title="Refactor auth token validation module",
            description="Refactor the token validation module and deploy it to staging. Create a feature branch off main and start with the unit tests.",
            assignee_name="Bob Smith",
            assignee_jira_id="def456",
            assignee_slack_id="U0002",
            priority="high",
            tags=["engineering", "backend"],
            tools_to_invoke=["jira", "slack", "github"],
            status="routed",
            jira_ticket_id="PROJ-101",
            jira_ticket_url="https://yourorg.atlassian.net/browse/PROJ-101",
            github_branch_name="feature/PROJ-101-refactor-auth-token-validation",
            github_branch_url="https://github.com/yourorg/yourrepo/tree/feature/PROJ-101-refactor-auth-token-validation",
            slack_summary="During sprint planning, the team discussed the legacy auth middleware. Bob needs to refactor the token validation module, deploy to staging, and write unit tests.",
            slack_message_ts="1234567890.000100",
        ),
        ActionItem(
            id="item-2",
            title="Fix CI pipeline GitHub Actions workflow",
            description="Debug the CI pipeline and push a fix to the repo. Likely a caching issue in the build step.",
            assignee_name="Bob Smith",
            assignee_jira_id="def456",
            assignee_slack_id="U0002",
            priority="high",
            tags=["engineering", "devops"],
            tools_to_invoke=["jira", "slack", "github"],
            status="routed",
            jira_ticket_id="PROJ-102",
            jira_ticket_url="https://yourorg.atlassian.net/browse/PROJ-102",
            github_branch_name="feature/PROJ-102-fix-ci-pipeline",
            github_branch_url="https://github.com/yourorg/yourrepo/tree/feature/PROJ-102-fix-ci-pipeline",
            slack_summary="Alice flagged that the deployment pipeline has been flaky. Bob should investigate the GitHub Actions workflow and fix the failing test stage.",
            slack_message_ts="1234567890.000200",
        ),
        ActionItem(
            id="item-3",
            title="Update API documentation on Confluence",
            description="Update the API documentation on Confluence once Bob's new auth endpoints are finalized. Notify partner team about breaking changes.",
            assignee_name="Carol Chen",
            assignee_jira_id="ghi789",
            assignee_slack_id="U0003",
            priority="medium",
            tags=["documentation"],
            tools_to_invoke=["jira", "slack"],
            status="routed",
            jira_ticket_id="PROJ-103",
            jira_ticket_url="https://yourorg.atlassian.net/browse/PROJ-103",
            github_branch_name=None,
            github_branch_url=None,
            slack_summary="Carol needs to update the API docs once the new auth endpoints are stable and reach out to the partner team about breaking changes.",
            slack_message_ts="1234567890.000300",
        ),
        ActionItem(
            id="item-4",
            title="Draft revised onboarding email sequence",
            description="Put together a revised onboarding email draft and loop in marketing by end of week based on sales team feedback.",
            assignee_name="Carol Chen",
            assignee_jira_id="ghi789",
            assignee_slack_id="U0003",
            priority="medium",
            tags=["marketing"],
            tools_to_invoke=["jira", "slack"],
            status="routed",
            jira_ticket_id="PROJ-104",
            jira_ticket_url="https://yourorg.atlassian.net/browse/PROJ-104",
            github_branch_name=None,
            github_branch_url=None,
            slack_summary="The sales team gave feedback that the onboarding emails need revision. Carol should draft a new version and send it to marketing for review.",
            slack_message_ts="1234567890.000400",
        ),
    ]


@pytest.fixture
def sample_meeting_state(sample_action_items) -> MeetingState:
    """Full MeetingState with sample action items and transcript from fixture file."""
    transcript = ""
    if _TRANSCRIPT_PATH.exists():
        transcript = _TRANSCRIPT_PATH.read_text()

    return MeetingState(
        meeting_id="test-meeting-001",
        meeting_title="Q1 Sprint Planning",
        meeting_date="2026-03-15",
        participants=["Alice Johnson", "Bob Smith", "Carol Chen"],
        transcript=transcript,
        action_items=sample_action_items,
        slack_channel_id="C0001",
        slack_thread_ts="1234567890.000000",
        human_review_complete=True,
        processing_errors=[],
    )


@pytest.fixture
def dry_run_env():
    """Set DRY_RUN=true for the duration of the test, then restore."""
    original = os.environ.get("DRY_RUN")
    os.environ["DRY_RUN"] = "true"
    yield
    if original is None:
        os.environ.pop("DRY_RUN", None)
    else:
        os.environ["DRY_RUN"] = original


@pytest.fixture
def sample_roster() -> dict:
    """Load the roster from src/config/team_roster.yaml."""
    with open(_ROSTER_PATH, "r") as f:
        return yaml.safe_load(f)
