"""
Skill: Workflow Monitor

Real-time polling of GitHub Actions workflow runs with progress callbacks.
Used by ConversationalOrchestrator to stream execution updates to chat.

Polls at configurable intervals, emits status events via on_update callback,
and returns a structured summary including job-level results.
"""
from __future__ import annotations

import os
import time
import sys
from typing import Any, Callable

from .base import AgentSkill


class WorkflowMonitorSkill(AgentSkill):
    name = "workflow_monitor"
    description = "Poll GitHub Actions workflow until completion and stream updates"
    version = "1.0.0"

    input_schema = {
        "run_id":      {"type": str,  "required": True,  "description": "GitHub Actions workflow run ID"},
        "repo":        {"type": str,  "required": False, "description": "owner/repo slug"},
        "poll_interval_s": {"type": int, "required": False, "description": "Seconds between polls (default 30)"},
        "max_wait_s":  {"type": int,  "required": False, "description": "Max wait in seconds (default 1800)"},
        "on_update":   {"type": None, "required": False, "description": "Callable(str) for progress messages"},
    }

    output_schema = {
        "success":    {"type": bool},
        "status":     {"type": str},
        "conclusion": {"type": str},
        "html_url":   {"type": str},
        "jobs":       {"type": list},
        "duration_s": {"type": float},
    }

    def run(self, **inputs: Any) -> dict:
        run_id   = str(inputs.get("run_id", ""))
        repo     = inputs.get("repo") or self._repo_from_config()
        poll_s   = int(inputs.get("poll_interval_s", 30))
        max_wait = int(inputs.get("max_wait_s", 1800))
        on_update: Callable[[str], None] = inputs.get("on_update") or (lambda _: None)

        if not run_id:
            return {"success": False, "error": "run_id is required"}

        token = os.environ.get("GITHUB_TOKEN", "")
        if not token or not repo:
            return {"success": False, "error": "GITHUB_TOKEN and repo slug are required"}

        try:
            import httpx
        except ImportError:
            return {"success": False, "error": "httpx not installed"}

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        base = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}"

        start = time.monotonic()
        deadline = start + max_wait
        last_status = ""
        on_update(f"Monitoring workflow run #{run_id} ...")

        while time.monotonic() < deadline:
            try:
                resp = httpx.get(base, headers=headers, timeout=20)
                if resp.status_code == 200:
                    data       = resp.json()
                    status     = data.get("status", "")
                    conclusion = data.get("conclusion") or ""
                    html_url   = data.get("html_url", "")

                    if status != last_status:
                        on_update(f"Workflow status: {status.upper()}{' — ' + conclusion.upper() if conclusion else ''}")
                        last_status = status

                    if status in ("completed", "cancelled", "timed_out"):
                        elapsed = round(time.monotonic() - start, 1)
                        jobs = self._fetch_jobs(repo, run_id, headers)
                        on_update(f"Workflow finished: {conclusion.upper()} in {round(elapsed / 60, 1)}m")
                        return {
                            "success":    conclusion == "success",
                            "status":     status,
                            "conclusion": conclusion,
                            "html_url":   html_url,
                            "jobs":       jobs,
                            "duration_s": elapsed,
                        }
            except Exception as exc:
                print(f"[workflow_monitor] poll error: {exc}", file=sys.stderr)

            time.sleep(poll_s)

        return {
            "success":    False,
            "status":     "timeout",
            "conclusion": "timeout",
            "html_url":   "",
            "jobs":       [],
            "duration_s": round(time.monotonic() - start, 1),
        }

    # ── Internal ──────────────────────────────────────────────────────────────

    def _repo_from_config(self) -> str:
        if not self.config or not self.config.project:
            return ""
        repo = self.config.project.repository or ""
        if repo.startswith("https://github.com/"):
            return repo.removeprefix("https://github.com/").rstrip("/")
        return repo

    @staticmethod
    def _fetch_jobs(repo: str, run_id: str, headers: dict) -> list[dict]:
        try:
            import httpx
            resp = httpx.get(
                f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/jobs",
                headers=headers, timeout=20,
            )
            if resp.status_code == 200:
                return [
                    {
                        "name":       j.get("name"),
                        "status":     j.get("status"),
                        "conclusion": j.get("conclusion"),
                        "duration_s": (
                            (
                                _parse_iso(j.get("completed_at")) - _parse_iso(j.get("started_at"))
                            ).total_seconds()
                            if j.get("completed_at") and j.get("started_at") else 0
                        ),
                    }
                    for j in resp.json().get("jobs", [])
                ]
        except Exception:
            pass
        return []


def _parse_iso(s: str | None):
    if not s:
        return None
    from datetime import datetime, timezone
    return datetime.fromisoformat(s.replace("Z", "+00:00"))
