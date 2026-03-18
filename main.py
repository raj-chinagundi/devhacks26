#!/usr/bin/env python3
"""CLI entry point for Meeting-to-Tasks MVP."""

import argparse
import json
import os
import sys

from langgraph.types import Command


def main():
    parser = argparse.ArgumentParser(
        description="Meeting-to-Tasks: extract action items from a transcript and route them."
    )
    parser.add_argument(
        "--transcript",
        required=True,
        help="Path to a meeting transcript text file.",
    )
    args = parser.parse_args()

    # Load .env before checking DRY_RUN
    from dotenv import load_dotenv
    load_dotenv()

    # Ensure DRY_RUN defaults to true if not set
    if "DRY_RUN" not in os.environ:
        os.environ["DRY_RUN"] = "true"

    # Read transcript
    transcript_path = args.transcript
    if not os.path.isfile(transcript_path):
        print(f"Error: transcript file not found: {transcript_path}")
        sys.exit(1)

    with open(transcript_path, "r") as f:
        transcript_text = f.read()

    # Import graph after env is set
    from src.graph.builder import graph

    # Build initial state
    initial_state = {
        "meeting_id": "",
        "meeting_title": "",
        "meeting_date": "",
        "participants": [],
        "transcript": transcript_text,
        "action_items": [],
        "slack_channel_id": None,
        "slack_thread_ts": None,
        "human_review_complete": False,
        "processing_errors": [],
    }

    config = {"configurable": {"thread_id": "meeting-1"}}

    # First invoke -- runs until interrupt before human_review
    print("\n=== Running extraction and assignee resolution... ===\n")
    result = graph.invoke(initial_state, config)

    # Display action items for review
    items = result.get("action_items", [])
    if not items:
        print("No action items were extracted from the transcript.")
        sys.exit(0)

    print("\n=== Extracted Action Items ===\n")
    _print_items_with_routing(items)

    # Ask for human approval
    while True:
        choice = input("\nApprove these action items? (Y/n/edit): ").strip().lower()
        if choice in ("", "y", "yes"):
            break
        elif choice == "n":
            print("Aborted by user.")
            sys.exit(0)
        elif choice == "edit":
            print("\nCurrent items as JSON:")
            serializable_items = list(items)
            print(json.dumps(serializable_items, indent=2))
            print("\nPaste modified JSON (end with an empty line):")
            lines = []
            while True:
                line = input()
                if line.strip() == "":
                    break
                lines.append(line)
            try:
                edited_items = json.loads("\n".join(lines))
                # Update the state with edited items
                graph.update_state(config, {"action_items": edited_items})
                print("Items updated.")
            except json.JSONDecodeError as e:
                print(f"Invalid JSON: {e}. Keeping original items.")
        else:
            print("Please enter Y, n, or edit.")

    # Resume the graph past the interrupt
    print("\n=== Routing and executing actions... ===\n")
    result = graph.invoke(Command(resume=True), config)

    # Print final summary
    _print_summary(result)


def _print_items_with_routing(items):
    """Print action items with routing preview."""
    import re
    def _has_eng_kw(text):
        for kw in ["code", "repo", "branch", "deploy", "merge", "refactor", "bug fix"]:
            if re.search(r"\b" + re.escape(kw) + r"\b", text.lower()):
                return True
        if re.search(r"\bPR\b", text):
            return True
        return False

    for i, item in enumerate(items, 1):
        is_engineering = (
            "engineering" in item.get("tags", [])
            or _has_eng_kw(item.get("description", ""))
        )
        tools = ["jira", "slack", "github"] if is_engineering else ["jira", "slack"]

        print(f"  {i}. [{item.get('priority', 'medium').upper()}] {item.get('title', 'Untitled')}")
        print(f"     Assignee: {item.get('assignee_name', 'Unknown')}")
        print(f"     Description: {item.get('description', '')}")
        print(f"     Tags: {item.get('tags', [])}")
        print(f"     Jira ID: {item.get('assignee_jira_id', 'unresolved')}")
        print(f"     Slack ID: {item.get('assignee_slack_id', 'unresolved')}")
        print(f"     -> Will route to: {tools}")
        print()


def _print_summary(result):
    """Print final summary after graph completion."""
    print("\n=== Final Summary ===\n")
    items = result.get("action_items", [])
    errors = result.get("processing_errors", [])

    for i, item in enumerate(items, 1):
        print(f"  {i}. {item.get('title', 'Untitled')}")
        print(f"     Status: {item.get('status', 'unknown')}")
        print(f"     Assignee: {item.get('assignee_name', 'Unknown')}")
        jira_id = item.get("jira_ticket_id")
        if jira_id:
            print(f"     Jira: {jira_id} ({item.get('jira_ticket_url', '')})")
        branch = item.get("github_branch_name")
        if branch:
            print(f"     GitHub Branch: {branch}")
        summary = item.get("slack_summary")
        if summary:
            print(f"     Slack Summary: {summary[:80]}...")
        print()

    if errors:
        print("  Errors encountered:")
        for err in errors:
            print(f"    - {err}")

    print("Done.")


if __name__ == "__main__":
    main()
