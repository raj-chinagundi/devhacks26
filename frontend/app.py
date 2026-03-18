#!/usr/bin/env python3
"""Small frontend bridge that runs the existing CLI safely."""

from __future__ import annotations

import copy
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles

FRONTEND_DIR = Path(__file__).resolve().parent
ROOT_DIR = FRONTEND_DIR.parent
RUNTIME_DIR = FRONTEND_DIR / ".runtime"
UPLOAD_DIR = RUNTIME_DIR / "uploads"

ACCEPTED_EXTENSIONS = {".txt", ".md"}
MAX_FILE_SIZE = 2 * 1024 * 1024
STEP_IDS = ["extract", "resolve", "review", "route", "jira", "github", "slack"]

RUNS: dict[str, dict] = {}
RUNS_LOCK = threading.Lock()

app = FastAPI(title="auto-meet frontend bridge")


def _empty_step_states() -> dict[str, str]:
    return {step_id: "pending" for step_id in STEP_IDS}


def _summary_template() -> dict:
    return {
        "items": [],
        "item_count": 0,
        "ticket_count": 0,
        "branch_count": 0,
        "slack_summary_count": 0,
        "processing_errors": [],
        "stdout_tail": [],
        "command": f"{sys.executable} -u {ROOT_DIR / 'main.py'} --transcript <uploaded-file>",
        "dry_run": None,
        "duration_ms": None,
        "exit_code": None,
    }


def _default_dry_run_mode() -> bool:
    env_path = ROOT_DIR / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            if key.strip() == "DRY_RUN":
                cleaned = value.strip().strip("'").strip('"').lower()
                return cleaned in {"true", "1", "yes"}
    return os.environ.get("DRY_RUN", "true").lower() in {"true", "1", "yes"}


def _build_run(file_name: str) -> dict:
    return {
        "run_id": str(uuid.uuid4()),
        "file_name": file_name,
        "status": "spinning",
        "current_step_id": None,
        "failure_step_id": None,
        "step_states": _empty_step_states(),
        "loop_closed": False,
        "error": None,
        "retryable": False,
        "summary": _summary_template(),
        "created_at": time.time(),
        "updated_at": time.time(),
    }


def _snapshot(run_id: str) -> dict:
    with RUNS_LOCK:
        run = RUNS.get(run_id)
        if not run:
            raise KeyError(run_id)
        return copy.deepcopy(run)


def _mutate_run(run_id: str, mutate) -> None:
    with RUNS_LOCK:
        run = RUNS[run_id]
        mutate(run)
        run["updated_at"] = time.time()


def _append_output(run: dict, line: str) -> None:
    tail = run["summary"]["stdout_tail"]
    tail.append(line)
    if len(tail) > 120:
        del tail[: len(tail) - 120]


def _set_step(run: dict, step_id: str, state: str) -> None:
    if step_id in run["step_states"]:
        run["step_states"][step_id] = state


def _mark_running(run: dict, step_id: str) -> None:
    run["status"] = "processing"
    run["current_step_id"] = step_id
    if run["step_states"].get(step_id) == "pending":
        run["step_states"][step_id] = "running"


def _mark_done(run: dict, step_id: str) -> None:
    if step_id in run["step_states"]:
        run["step_states"][step_id] = "done"


def _mark_failed(run: dict, step_id: str, message: str) -> None:
    run["status"] = "error"
    run["current_step_id"] = step_id
    run["failure_step_id"] = step_id
    run["retryable"] = True
    run["error"] = message
    run["step_states"][step_id] = "failed"


def _finalize_success(run: dict, duration_ms: int, no_items: bool) -> None:
    if no_items:
        for step_id in ("extract", "resolve", "review"):
            if run["step_states"][step_id] in {"pending", "running"}:
                run["step_states"][step_id] = "done"
    else:
        for step_id in STEP_IDS:
            if run["step_states"][step_id] in {"pending", "running"}:
                run["step_states"][step_id] = "done"

    run["status"] = "completed"
    run["current_step_id"] = None
    run["loop_closed"] = True
    run["retryable"] = False
    run["summary"]["duration_ms"] = duration_ms


def _finalize_error(run: dict, duration_ms: int, message: str) -> None:
    run["status"] = "error"
    run["error"] = message
    run["retryable"] = True
    run["summary"]["duration_ms"] = duration_ms

    if not run["failure_step_id"]:
        failed_step = run["current_step_id"] or next(
            (step_id for step_id, state in run["step_states"].items() if state in {"pending", "running"}),
            "extract",
        )
        run["failure_step_id"] = failed_step
        run["current_step_id"] = failed_step
        run["step_states"][failed_step] = "failed"


def _parse_summary(line: str, state: dict) -> None:
    if "=== Final Summary ===" in line:
        state["in_summary"] = True
        state["current_item"] = None
        state["in_errors"] = False
        return

    if not state["in_summary"]:
        return

    if line.strip() == "Done.":
        if state["current_item"]:
            state["items"].append(state["current_item"])
            state["current_item"] = None
        state["in_summary"] = False
        state["in_errors"] = False
        return

    item_match = re.match(r"^\s*\d+\.\s+(.*)$", line)
    if item_match:
        if state["current_item"]:
            state["items"].append(state["current_item"])
        state["current_item"] = {"title": item_match.group(1).strip()}
        state["in_errors"] = False
        return

    if "Errors encountered:" in line:
        if state["current_item"]:
            state["items"].append(state["current_item"])
            state["current_item"] = None
        state["in_errors"] = True
        return

    error_match = re.match(r"^\s*-\s+(.*)$", line)
    if state["in_errors"] and error_match:
        state["processing_errors"].append(error_match.group(1).strip())
        return

    if not state["current_item"]:
        return

    field_patterns = {
        "Status:": "status",
        "Assignee:": "assignee",
        "Jira:": "jira",
        "GitHub Branch:": "github_branch",
        "Slack Summary:": "slack_summary",
    }

    stripped = line.strip()
    for prefix, field_name in field_patterns.items():
        if stripped.startswith(prefix):
            state["current_item"][field_name] = stripped[len(prefix) :].strip()
            return


def _refresh_summary_from_items(run: dict, parser_state: dict) -> None:
    items = list(parser_state["items"])
    if parser_state["current_item"]:
        items = items + [parser_state["current_item"]]

    run["summary"]["items"] = items
    run["summary"]["item_count"] = len(items)
    run["summary"]["ticket_count"] = sum(1 for item in items if item.get("jira"))
    run["summary"]["branch_count"] = sum(1 for item in items if item.get("github_branch"))
    run["summary"]["slack_summary_count"] = sum(1 for item in items if item.get("slack_summary"))
    run["summary"]["processing_errors"] = list(parser_state["processing_errors"])


def _apply_output_markers(run: dict, line: str) -> None:
    if "=== Running extraction and assignee resolution... ===" in line:
        _mark_running(run, "extract")
        return

    if "=== Extracted Action Items ===" in line:
        _mark_done(run, "extract")
        _mark_done(run, "resolve")
        _mark_running(run, "review")
        return

    if "=== Routing and executing actions... ===" in line:
        _mark_done(run, "review")
        _mark_done(run, "route")
        _mark_running(run, "jira")
        return

    if "[DRY_RUN] create_jira_ticket:" in line or re.match(r"^\s*Jira:\s+", line):
        _mark_done(run, "jira")
        _mark_running(run, "github")
        return

    if "[DRY_RUN] create_github_branch:" in line or "GitHub Branch:" in line:
        _mark_done(run, "github")
        _mark_running(run, "slack")
        return

    if "[DRY_RUN] post_slack_thread:" in line or "Slack Summary:" in line:
        _mark_done(run, "slack")
        return


def _execute_run(run_id: str, transcript_path: Path) -> None:
    started = time.time()
    parser_state = {
        "in_summary": False,
        "in_errors": False,
        "items": [],
        "processing_errors": [],
        "current_item": None,
    }
    no_items = False

    command = [sys.executable, "-u", str(ROOT_DIR / "main.py"), "--transcript", str(transcript_path)]
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    try:
        process = subprocess.Popen(
            command,
            cwd=ROOT_DIR,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except Exception as exc:
        _mutate_run(run_id, lambda run: _finalize_error(run, 0, f"Could not start main.py: {exc}"))
        transcript_path.unlink(missing_ok=True)
        return

    try:
        if process.stdin:
            process.stdin.write("y\n")
            process.stdin.flush()
            process.stdin.close()

        assert process.stdout is not None
        for raw_line in process.stdout:
            line = raw_line.rstrip("\n")

            def _update(run: dict) -> None:
                _append_output(run, line)

                if "No action items were extracted from the transcript." in line:
                    nonlocal no_items
                    no_items = True

                if run["summary"]["dry_run"] is None and "[DRY_RUN]" in line:
                    run["summary"]["dry_run"] = True

                _apply_output_markers(run, line)
                _parse_summary(line, parser_state)
                _refresh_summary_from_items(run, parser_state)

            _mutate_run(run_id, _update)

        exit_code = process.wait()
        duration_ms = int((time.time() - started) * 1000)

        def _finish(run: dict) -> None:
            run["summary"]["exit_code"] = exit_code
            if run["summary"]["dry_run"] is None:
                run["summary"]["dry_run"] = _default_dry_run_mode()

            if exit_code == 0:
                _finalize_success(run, duration_ms, no_items)
            else:
                last_line = run["summary"]["stdout_tail"][-1] if run["summary"]["stdout_tail"] else "main.py failed."
                _finalize_error(run, duration_ms, last_line)

        _mutate_run(run_id, _finish)
    finally:
        transcript_path.unlink(missing_ok=True)


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.post("/api/runs")
async def create_run(file: UploadFile = File(...)) -> dict:
    file_name = file.filename or "transcript.txt"
    suffix = Path(file_name).suffix.lower()
    if suffix not in ACCEPTED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Use a .txt or .md transcript file.")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="Keep the transcript under 2 MB.")

    try:
        decoded = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="The transcript must be UTF-8 text.") from exc

    if not decoded.strip():
        raise HTTPException(status_code=400, detail="The transcript is empty.")

    if len(decoded.strip()) < 100:
        raise HTTPException(status_code=400, detail="The transcript is too short for a real run.")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    run = _build_run(file_name)
    transcript_path = UPLOAD_DIR / f"{run['run_id']}{suffix}"
    transcript_path.write_bytes(content)

    with RUNS_LOCK:
        RUNS[run["run_id"]] = run

    thread = threading.Thread(target=_execute_run, args=(run["run_id"], transcript_path), daemon=True)
    thread.start()

    return {"run_id": run["run_id"]}


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict:
    try:
        return _snapshot(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found.") from exc


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=4173)
