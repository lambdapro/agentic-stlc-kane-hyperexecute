"""
Skill 6: HyperExecute Monitoring

Submits a HyperExecute job and polls for completion.
Writes results to reports/api_details.json in the standard format
consumed by build_traceability.py.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from .base import AgentSkill


class HyperExecuteMonitoringSkill(AgentSkill):
    name = "hyperexecute_monitoring"
    description = "Submit HyperExecute job and poll until completion"
    version = "1.0.0"

    input_schema = {
        "selection_file": {"type": str, "required": False, "description": "Path to pytest_selection.txt"},
        "he_config":      {"type": str, "required": False, "description": "HyperExecute YAML config path"},
        "max_wait_s":     {"type": int, "required": False, "description": "Max wait for results (default 900)"},
    }

    def run(self, **inputs: Any) -> dict:
        selection_file = Path(
            inputs.get("selection_file", "reports/pytest_selection.txt")
        )
        he_config = inputs.get("he_config") or (
            self.config.hyperexecute.config_file if self.config else "hyperexecute.yaml"
        )
        max_wait_s = inputs.get("max_wait_s", 900)

        lt_user = os.environ.get("LT_USERNAME", "")
        lt_key  = os.environ.get("LT_ACCESS_KEY", "")

        if not selection_file.exists():
            return {"success": False, "error": "pytest_selection.txt not found", "job_id": ""}

        cli_path = self._resolve_cli()
        if not cli_path:
            return {"success": False, "error": "HyperExecute CLI not found", "job_id": ""}

        job_id = self._submit(cli_path, he_config, lt_user, lt_key)
        if not job_id:
            return {"success": False, "error": "Failed to submit HyperExecute job", "job_id": ""}

        results = self._poll(job_id, lt_user, lt_key, max_wait_s)
        self._write_api_details(job_id, results)

        return {
            "success": results.get("overall_status") != "failed",
            "job_id": job_id,
            "he_status": results.get("overall_status", "unknown"),
            "tasks": len(results.get("tasks", [])),
        }

    # ── Internal ──────────────────────────────────────────────────────────────

    def _resolve_cli(self) -> str | None:
        cli_path = self.config.hyperexecute.cli_path if self.config else "./hyperexecute"
        candidates = [cli_path, "./hyperexecute", "./hyperexecute.exe", "hyperexecute"]
        for c in candidates:
            if Path(c).exists():
                return c
        return None

    def _submit(self, cli: str, config: str, user: str, key: str) -> str:
        run_num = os.environ.get("GITHUB_RUN_NUMBER", "local")
        project = (self.config.hyperexecute.project if self.config else None) or "agentic-stlc"
        cmd = [
            cli, "--user", user, "--key", key,
            "--config", config,
            "--label", f"run-{run_num}",
            "--project", project,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            for line in (result.stdout + result.stderr).splitlines():
                if "job id" in line.lower() or "jobid" in line.lower():
                    parts = line.split()
                    for part in parts:
                        if part.startswith("HE") or (part.isalnum() and len(part) > 8):
                            return part
        except Exception as exc:
            print(f"[hyperexecute_monitoring] submit error: {exc}", file=sys.stderr)
        return ""

    def _poll(self, job_id: str, user: str, key: str, max_wait_s: int) -> dict:
        import httpx
        deadline = time.monotonic() + max_wait_s
        while time.monotonic() < deadline:
            try:
                resp = httpx.get(
                    f"https://api.hyperexecute.cloud/v2.0/job/{job_id}/sessions",
                    auth=(user, key),
                    timeout=30,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    status = data.get("data", {}).get("status", "")
                    if status in ("completed", "failed", "cancelled", "aborted"):
                        return data.get("data", {})
            except Exception:
                pass
            time.sleep(30)
        return {"overall_status": "timeout"}

    def _write_api_details(self, job_id: str, data: dict) -> None:
        out = {
            "job_id": job_id,
            "he_summary": data,
            "he_tasks": data.get("tasks", []),
            "parser_status": "api_ok" if data else "not_executed",
        }
        Path(self.reports_dir).mkdir(parents=True, exist_ok=True)
        Path(f"{self.reports_dir}/api_details.json").write_text(
            json.dumps(out, indent=2) + "\n", encoding="utf-8"
        )
