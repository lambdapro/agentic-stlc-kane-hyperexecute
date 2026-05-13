"""
HyperExecute execution adapter.

Submits jobs via the HyperExecute CLI and polls results via the
HyperExecute REST API. Falls back to the LambdaTest Automation API
when the HE API returns 403 (access-level restriction).
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from .base import ExecutionAdapter

try:
    import httpx
    _HAS_HTTPX = True
except ImportError:
    _HAS_HTTPX = False

_HE_API_BASE = "https://api.hyperexecute.cloud/v2.0"
_LT_API_BASE = "https://api.lambdatest.com/automation/api/v1"


class HyperExecuteAdapter(ExecutionAdapter):
    """HyperExecute test execution adapter."""

    def __init__(
        self,
        username: str = "",
        access_key: str = "",
        cli_path: str = "./hyperexecute",
    ) -> None:
        self.username   = username   or os.environ.get("LT_USERNAME", "")
        self.access_key = access_key or os.environ.get("LT_ACCESS_KEY", "")
        self.cli_path   = cli_path

    # ── ExecutionAdapter interface ────────────────────────────────────────────

    def submit_job(self, config_path: str, test_list: list[str], labels: dict) -> str:
        cli = self._resolve_cli()
        if not cli:
            print("[hyperexecute] CLI not found", file=sys.stderr)
            return ""

        run_num = os.environ.get("GITHUB_RUN_NUMBER", "local")
        label_str = ",".join(f"{k}={v}" for k, v in labels.items())

        cmd = [
            cli,
            "--user",   self.username,
            "--key",    self.access_key,
            "--config", config_path,
        ]
        if label_str:
            cmd += ["--label", label_str]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            output = result.stdout + result.stderr
            for line in output.splitlines():
                if "job" in line.lower() and ("id" in line.lower() or ":" in line):
                    parts = line.split()
                    for part in parts:
                        if len(part) > 8 and part.replace("-", "").replace("_", "").isalnum():
                            return part
        except Exception as exc:
            print(f"[hyperexecute] submit error: {exc}", file=sys.stderr)
        return ""

    def get_job_status(self, job_id: str) -> dict:
        if not _HAS_HTTPX:
            return {"status": "unknown", "error": "httpx not installed"}
        try:
            resp = httpx.get(
                f"{_HE_API_BASE}/job/{job_id}",
                auth=(self.username, self.access_key),
                timeout=30,
            )
            if resp.status_code == 200:
                data = resp.json().get("data", {})
                return {"status": data.get("status", ""), "progress": data.get("progress", 0)}
            return {"status": "unknown", "http_status": resp.status_code}
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    def get_job_results(self, job_id: str) -> dict:
        if not _HAS_HTTPX:
            return {}
        try:
            resp = httpx.get(
                f"{_HE_API_BASE}/job/{job_id}/sessions",
                auth=(self.username, self.access_key),
                timeout=30,
            )
            if resp.status_code == 200:
                return resp.json().get("data", {})
            if resp.status_code == 403:
                return self._fallback_lt_api(job_id)
        except Exception:
            pass
        return {}

    def get_session_url(self, session_id: str) -> str:
        return f"https://automation.lambdatest.com/test-details/{session_id}"

    # ── Polling helper ────────────────────────────────────────────────────────

    def poll_until_complete(self, job_id: str, max_wait_s: int = 900, interval_s: int = 30) -> dict:
        deadline = time.monotonic() + max_wait_s
        while time.monotonic() < deadline:
            status = self.get_job_status(job_id)
            if status.get("status") in ("completed", "failed", "cancelled", "aborted"):
                return self.get_job_results(job_id)
            time.sleep(interval_s)
        return {"overall_status": "timeout"}

    # ── Internal ──────────────────────────────────────────────────────────────

    def _resolve_cli(self) -> str | None:
        candidates = [self.cli_path, "./hyperexecute", "./hyperexecute.exe", "hyperexecute"]
        for c in candidates:
            if Path(c).exists():
                return c
        return None

    def _fallback_lt_api(self, job_id: str) -> dict:
        """LambdaTest Automation API fallback for HE 403."""
        if not _HAS_HTTPX:
            return {}
        try:
            resp = httpx.get(
                f"{_LT_API_BASE}/builds",
                auth=(self.username, self.access_key),
                params={"limit": 5},
                timeout=30,
            )
            if resp.status_code == 200:
                builds = resp.json().get("data", {}).get("builds", [])
                return {"fallback": True, "builds": builds[:3], "overall_status": "completed"}
        except Exception:
            pass
        return {}
