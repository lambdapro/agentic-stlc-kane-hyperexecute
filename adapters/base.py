"""
Adapter base interfaces.

All adapters implement one of these abstract base classes.
Third-party adapters (GitLab, Jenkins, Cypress, etc.) extend these
interfaces and register themselves via AdapterRegistry.

Design principles:
  - Each adapter handles exactly one integration concern
  - All methods return plain dicts (JSON-serializable)
  - Credentials come from environment variables, never hardcoded
  - Adapters are stateless; state lives in the context dict
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class GitAdapter(ABC):
    """Adapter for Git hosting providers (GitHub, GitLab, Bitbucket)."""

    @abstractmethod
    def clone(self, url: str, branch: str, target_dir: str) -> dict:
        """Clone repository branch to target_dir. Returns {"success": bool, ...}"""

    @abstractmethod
    def push(self, branch: str, commit_message: str, files: list[str]) -> dict:
        """Stage, commit, and push listed files. Returns {"success": bool, "sha": str}"""

    @abstractmethod
    def create_pull_request(self, title: str, body: str, head: str, base: str) -> dict:
        """Create PR/MR. Returns {"success": bool, "pr_url": str, "pr_number": int}"""

    @abstractmethod
    def get_file_content(self, path: str, ref: str = "HEAD") -> str:
        """Fetch raw file content from remote. Returns content string."""


class CIAdapter(ABC):
    """Adapter for CI/CD pipeline providers (GitHub Actions, GitLab CI, Jenkins)."""

    @abstractmethod
    def trigger_workflow(self, workflow_id: str, ref: str, inputs: dict) -> str:
        """Trigger a workflow/pipeline run. Returns run_id string."""

    @abstractmethod
    def get_workflow_status(self, run_id: str) -> dict:
        """Poll run status. Returns {"status": str, "conclusion": str, "html_url": str}"""

    @abstractmethod
    def download_artifacts(self, run_id: str, output_dir: str) -> list[dict]:
        """Download artifacts for a run. Returns list of {"name": str, "path": str}"""

    @abstractmethod
    def list_recent_runs(self, workflow_id: str, limit: int = 10) -> list[dict]:
        """List recent runs. Returns list of run summary dicts."""


class ExecutionAdapter(ABC):
    """Adapter for test execution providers (HyperExecute, LambdaTest Grid, BrowserStack)."""

    @abstractmethod
    def submit_job(self, config_path: str, test_list: list[str], labels: dict) -> str:
        """Submit a test job. Returns job_id."""

    @abstractmethod
    def get_job_status(self, job_id: str) -> dict:
        """Poll job status. Returns {"status": str, "progress": float, ...}"""

    @abstractmethod
    def get_job_results(self, job_id: str) -> dict:
        """Fetch complete job results. Returns {"tasks": [...], "summary": {...}}"""

    @abstractmethod
    def get_session_url(self, session_id: str) -> str:
        """Return direct link to session video/log."""


class FunctionalTestAdapter(ABC):
    """Adapter for functional/AI-driven browser testing (KaneAI, Mabl, Testim)."""

    @abstractmethod
    def run_test(self, objective: str, target_url: str, timeout_s: int) -> dict:
        """
        Run a single functional test.

        Returns:
            {"status": "passed"|"failed", "session_url": str, "one_liner": str, "steps": list}
        """

    @abstractmethod
    def run_batch(self, tests: list[dict], parallel_workers: int) -> list[dict]:
        """
        Run multiple tests in parallel.

        Args:
            tests: list of {"objective": str, "target_url": str, "requirement_id": str}
            parallel_workers: max concurrent workers

        Returns:
            list of per-test result dicts
        """


class ReportingAdapter(ABC):
    """Adapter for reporting sinks (GitHub Summary, Slack, Email, Grafana)."""

    @abstractmethod
    def write_summary(self, content: str, format: str = "markdown") -> dict:
        """Write summary to reporting sink. Returns {"success": bool}"""

    @abstractmethod
    def attach_artifact(self, name: str, path: str) -> dict:
        """Attach file artifact. Returns {"success": bool, "url": str}"""
