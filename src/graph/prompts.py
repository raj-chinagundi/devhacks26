EXTRACTION_PROMPT = """\
You are an expert meeting analyst. Given a raw meeting transcript, extract all action items discussed.

For each action item, return:
- title: A short task title (5-10 words)
- description: A 1-2 sentence description of what needs to be done
- assignee_name: The person assigned to do this (use the name as spoken in the meeting)
- priority: "high", "medium", or "low" based on urgency discussed
- tags: A list of tags. Include "engineering" if the task involves code, repos, branches, deployments, PRs, merges, refactoring, bug fixes, or any software development work. Use other descriptive tags as appropriate (e.g., "backend", "frontend", "design", "marketing", "operations", "documentation").

Also extract meeting metadata:
- meeting_title: A short title for the meeting
- meeting_date: The date of the meeting if mentioned, otherwise "unknown"
- participants: List of participant names mentioned in the transcript

Return your response as JSON with this exact structure:
{{
  "meeting_title": "...",
  "meeting_date": "...",
  "participants": ["..."],
  "action_items": [
    {{
      "title": "...",
      "description": "...",
      "assignee_name": "...",
      "priority": "high" | "medium" | "low",
      "tags": ["..."]
    }}
  ]
}}

Here are few-shot examples:

Example 1 (engineering task):
Transcript excerpt: "Alice, can you refactor the authentication service to use OAuth2 by next sprint?"
Action item:
{{
  "title": "Refactor auth service to OAuth2",
  "description": "Refactor the authentication service to replace the current auth mechanism with OAuth2. Target completion by next sprint.",
  "assignee_name": "Alice",
  "priority": "high",
  "tags": ["engineering", "backend"]
}}

Example 2 (non-engineering task):
Transcript excerpt: "Bob, please update the Q3 marketing deck with the new customer logos before Friday."
Action item:
{{
  "title": "Update Q3 marketing deck",
  "description": "Add new customer logos to the Q3 marketing presentation deck. Due by Friday.",
  "assignee_name": "Bob",
  "priority": "medium",
  "tags": ["marketing"]
}}

Example 3 (engineering task from keywords):
Transcript excerpt: "Carol, there's a bug in the checkout flow — can you fix it and deploy the fix today?"
Action item:
{{
  "title": "Fix checkout flow bug",
  "description": "Investigate and fix the bug in the checkout flow, then deploy the fix to production today.",
  "assignee_name": "Carol",
  "priority": "high",
  "tags": ["engineering", "bug fix", "frontend"]
}}

Now extract action items from the following transcript:

{transcript}
"""

SLACK_SUMMARY_PROMPT = """\
You are a helpful assistant that generates concise, contextual Slack notification summaries for action items from a meeting.

Given the original meeting transcript and a list of action items, generate a 2-3 sentence summary for each action item that:
1. References what was discussed in the meeting that led to this task
2. Explains what the assignee needs to do
3. Includes any relevant context from the discussion

Meeting transcript:
{transcript}

Action items (JSON):
{action_items}

Return a JSON array of strings, one summary per action item, in the same order as the input list. Each summary should be 2-3 sentences.

Example output:
["During the discussion about authentication issues, the team identified the need to migrate to OAuth2. Alice should refactor the auth service to support OAuth2 flows, targeting completion by next sprint. This was flagged as high priority due to upcoming security audit.", "Bob mentioned that the marketing deck is missing recent customer wins. He should update the Q3 presentation with the new logos from Acme Corp and TechStart before Friday's board meeting."]
"""
