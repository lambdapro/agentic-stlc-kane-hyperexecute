"""
KaneAI functional test adapter.

Wraps the kane-cli Node.js package to run AI-driven browser tests.
Parses NDJSON output from `kane-cli run --output ndjson` into structured
result dicts compatible with analyzed_requirements.json format.

Prerequisites:
  npm install -g @testmuai/kane-cli
  kane-cli config project <project_id>
  kane-cli config folder <folder_id>
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from .base import FunctionalTestAdapter


class KaneAIAdapter(FunctionalTestAdapter):
    """KaneAI AI-driven browser test adapter."""

    def __init__(
        self,
        project_id: str = "",
        folder_id: str = "",
        timeout_s: int = 120,
        parallel_workers: int = 5,
    ) -> None:
        self.project_id      = project_id
        self.folder_id       = folder_id
        self.timeout_s       = timeout_s
        self.parallel_workers = parallel_workers

    def run_test(self, objective: str, target_url: str, timeout_s: int = 0) -> dict:
        """Run a single KaneAI test for the given objective."""
        wait = timeout_s or self.timeout_s
        cmd = [
            "kane-cli", "run",
            "--objective", objective,
            "--url", target_url,
            "--output", "ndjson",
            "--timeout", str(wait),
        ]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=wait + 30
            )
            return self._parse_ndjson(result.stdout or result.stderr)
        except FileNotFoundError:
            return {"status": "failed", "error": "kane-cli not installed", "session_url": ""}
        except subprocess.TimeoutExpired:
            return {"status": "failed", "error": "kane-cli timed out", "session_url": ""}
        except Exception as exc:
            return {"status": "failed", "error": str(exc), "session_url": ""}

    def run_batch(self, tests: list[dict], parallel_workers: int = 0) -> list[dict]:
        """
        Run multiple KaneAI tests concurrently.

        Each test dict must have: {"objective": str, "target_url": str, "requirement_id": str}
        """
        workers = parallel_workers or self.parallel_workers
        results: list[dict] = [{}] * len(tests)

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    self.run_test,
                    t["objective"],
                    t["target_url"],
                ): i
                for i, t in enumerate(tests)
            }
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    res = future.result()
                except Exception as exc:
                    res = {"status": "failed", "error": str(exc)}
                res["requirement_id"] = tests[idx].get("requirement_id", "")
                results[idx] = res

        return results

    # ── Configuration ─────────────────────────────────────────────────────────

    def configure(self, project_id: str = "", folder_id: str = "") -> bool:
        """Run kane-cli config commands. Returns True on success."""
        pid = project_id or self.project_id
        fid = folder_id  or self.folder_id
        if not pid or not fid:
            return False
        try:
            subprocess.run(["kane-cli", "config", "project", pid], check=True, capture_output=True)
            subprocess.run(["kane-cli", "config", "folder",  fid], check=True, capture_output=True)
            return True
        except Exception:
            return False

    def is_available(self) -> bool:
        """Check whether kane-cli is installed and accessible."""
        try:
            result = subprocess.run(
                ["kane-cli", "--version"], capture_output=True, text=True, timeout=10
            )
            return result.returncode == 0
        except Exception:
            return False

    # ── NDJSON parser ─────────────────────────────────────────────────────────

    def _parse_ndjson(self, output: str) -> dict:
        """Parse kane-cli NDJSON stream into a single result dict."""
        status = "failed"
        session_url = ""
        one_liner = ""
        steps: list[str] = []
        duration_ms = 0

        for line in output.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            event = obj.get("event") or obj.get("type", "")
            if event in ("run_complete", "test_complete", "complete"):
                status      = "passed" if obj.get("passed") or obj.get("status") == "passed" else "failed"
                session_url = obj.get("sessionUrl", obj.get("session_url", ""))
                one_liner   = obj.get("summary", obj.get("oneLiner", obj.get("one_liner", "")))
                duration_ms = int(obj.get("durationMs", obj.get("duration", 0)))
            elif event == "step":
                steps.append(obj.get("description", obj.get("action", "")))

        return {
            "status":       status,
            "session_url":  session_url,
            "one_liner":    one_liner,
            "steps":        steps,
            "duration_ms":  duration_ms,
            "kane_status":  status,
        }
