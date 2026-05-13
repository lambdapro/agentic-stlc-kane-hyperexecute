"""
Playwright test framework adapter.

Manages test file generation, pytest execution (local and via HyperExecute),
and result parsing. Framework-agnostic interface means you can swap
Playwright for Cypress or WebdriverIO by swapping the adapter.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from .base import ExecutionAdapter


class PlaywrightAdapter:
    """
    Playwright pytest runner adapter.

    Handles local test execution and building the selection file
    used by HyperExecute for distributed execution.
    """

    def __init__(
        self,
        test_dir: str = "tests/playwright",
        test_file: str = "tests/playwright/test_powerapps.py",
        reports_dir: str = "reports",
        browsers: list[str] | None = None,
    ) -> None:
        self.test_dir    = test_dir
        self.test_file   = test_file
        self.reports_dir = reports_dir
        self.browsers    = browsers or ["chromium"]

    def run_local(
        self,
        test_ids: list[str] | None = None,
        target_url: str = "",
        extra_args: list[str] | None = None,
    ) -> dict:
        """Run Playwright tests locally via pytest."""
        Path(self.reports_dir).mkdir(parents=True, exist_ok=True)
        junit_path = f"{self.reports_dir}/junit.xml"
        html_path  = f"{self.reports_dir}/report.html"

        cmd = [
            sys.executable, "-m", "pytest",
            *(test_ids or [self.test_file]),
            f"--junitxml={junit_path}",
            f"--html={html_path}",
            "--tb=short",
            "-v",
            *(extra_args or []),
        ]
        env = {**os.environ}
        if target_url:
            env["TARGET_URL"] = target_url

        try:
            result = subprocess.run(cmd, env=env, capture_output=True, text=True)
            return {
                "success": result.returncode == 0,
                "returncode": result.returncode,
                "junit_xml": junit_path,
                "html_report": html_path,
                "stdout": result.stdout[-2000:],
                "stderr": result.stderr[-1000:],
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def build_selection_file(self, scenario_ids: list[str]) -> str:
        """
        Write pytest_selection.txt with test node IDs for HyperExecute discovery.

        Returns path to the selection file.
        """
        Path(self.reports_dir).mkdir(parents=True, exist_ok=True)
        selection_path = f"{self.reports_dir}/pytest_selection.txt"

        # Map scenario IDs → test function names
        lines = []
        for sc_id in scenario_ids:
            fn_name = f"test_{sc_id.lower().replace('-', '_')}"
            lines.append(f"{self.test_file}::{fn_name}")

        Path(selection_path).write_text("\n".join(lines) + "\n", encoding="utf-8")
        return selection_path

    def install_browsers(self) -> bool:
        """Install Playwright browser binaries."""
        try:
            result = subprocess.run(
                [sys.executable, "-m", "playwright", "install", "--with-deps"],
                capture_output=True, text=True,
            )
            return result.returncode == 0
        except Exception:
            return False

    def parse_junit_results(self, junit_path: str) -> dict:
        """Parse JUnit XML and return summary dict."""
        import xml.etree.ElementTree as ET
        p = Path(junit_path)
        if not p.exists():
            return {"exists": False}
        try:
            tree = ET.parse(str(p))
            root = tree.getroot()
            suite = root if root.tag == "testsuite" else (root.find("testsuite") or root)
            tests    = int(suite.get("tests",    0))
            failures = int(suite.get("failures", 0))
            errors   = int(suite.get("errors",   0))
            skipped  = int(suite.get("skipped",  0))
            passed   = tests - failures - errors - skipped
            return {
                "exists":   True,
                "tests":    tests,
                "passed":   passed,
                "failures": failures,
                "errors":   errors,
                "skipped":  skipped,
                "pass_rate": round(passed / tests * 100, 1) if tests else 0.0,
            }
        except Exception as exc:
            return {"exists": True, "parse_error": str(exc)}


class GitLabCIAdapter:
    """GitLab CI adapter stub — extend for GitLab-hosted pipelines."""

    def trigger_pipeline(self, project_id: str, ref: str, variables: dict) -> str:
        raise NotImplementedError("GitLab CI adapter not yet implemented")


class AndroidAdapter:
    """Mobile/Android test adapter stub."""

    def run_appium_tests(self, app_path: str, device: dict, tests: list[str]) -> dict:
        raise NotImplementedError("Android adapter not yet implemented")

    def get_real_device_session(self, device_id: str) -> dict:
        raise NotImplementedError("Android adapter not yet implemented")
