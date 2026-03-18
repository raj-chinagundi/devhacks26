from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from src.models import MeetingState
from src.graph.nodes import (
    extract_action_items_node,
    resolve_assignees_node,
    human_review_node,
    route_action_items_node,
    create_jira_tickets_node,
    send_slack_notifications_node,
    create_github_branches_node,
)

builder = StateGraph(MeetingState)

# Add nodes
builder.add_node("extract_action_items", extract_action_items_node)
builder.add_node("resolve_assignees", resolve_assignees_node)
builder.add_node("human_review", human_review_node)
builder.add_node("route_action_items", route_action_items_node)
builder.add_node("create_jira_tickets", create_jira_tickets_node)
builder.add_node("send_slack_notifications", send_slack_notifications_node)
builder.add_node("create_github_branches", create_github_branches_node)

# Linear flow through review and routing
builder.add_edge(START, "extract_action_items")
builder.add_edge("extract_action_items", "resolve_assignees")
builder.add_edge("resolve_assignees", "human_review")
builder.add_edge("human_review", "route_action_items")

# Jira first (produces IDs), then GitHub (produces branch URLs), then Slack (needs both)
builder.add_edge("route_action_items", "create_jira_tickets")
builder.add_edge("create_jira_tickets", "create_github_branches")
builder.add_edge("create_github_branches", "send_slack_notifications")
builder.add_edge("send_slack_notifications", END)

# Compile with checkpointer and interrupt
checkpointer = MemorySaver()
graph = builder.compile(
    checkpointer=checkpointer,
    interrupt_before=["human_review"],
)
