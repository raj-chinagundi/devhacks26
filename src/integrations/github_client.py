"""GitHub REST API integration using requests."""

import os
import re

from src.models import ActionItem


def _is_dry_run() -> bool:
    return os.environ.get("DRY_RUN", "true").lower() == "true"


def _slugify(text: str, max_len: int = 50) -> str:
    """Lowercase, replace spaces/special chars with hyphens, truncate."""
    slug = text.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug[:max_len].rstrip("-")


def _get_headers() -> dict[str, str]:
    token = os.environ["GITHUB_TOKEN"]
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def create_github_branch(
    item: ActionItem, repo_owner: str, repo_name: str
) -> tuple[str, str]:
    """Create a feature branch from main. Returns (branch_name, branch_url). Supports DRY_RUN."""
    jira_id = item.get("jira_ticket_id") or "UNKNOWN"
    slug = _slugify(item["title"])
    branch_name = f"feature/{jira_id}-{slug}"

    if _is_dry_run():
        branch_url = f"https://github.com/dry-run/repo/tree/{branch_name}"
        print(f"[DRY_RUN] create_github_branch: would create branch '{branch_name}' in {repo_owner}/{repo_name}")
        return (branch_name, branch_url)

    import requests

    headers = _get_headers()
    api_base = "https://api.github.com"

    # Step 1: Get SHA of main branch
    resp = requests.get(
        f"{api_base}/repos/{repo_owner}/{repo_name}/git/ref/heads/main",
        headers=headers,
    )
    resp.raise_for_status()
    main_sha = resp.json()["object"]["sha"]

    # Step 2: Create the branch ref
    resp = requests.post(
        f"{api_base}/repos/{repo_owner}/{repo_name}/git/refs",
        json={
            "ref": f"refs/heads/{branch_name}",
            "sha": main_sha,
        },
        headers=headers,
    )
    resp.raise_for_status()

    branch_url = f"https://github.com/{repo_owner}/{repo_name}/tree/{branch_name}"
    return (branch_name, branch_url)
