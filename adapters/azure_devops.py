"""
Azure DevOps adapter.

Triggers Azure Pipelines runs and polls status via the Azure DevOps REST API.

Authentication: Personal Access Token (PAT) via env vars
  AZURE_DEVOPS_ORG     — organization name (e.g. "myorg")
  AZURE_DEVOPS_PROJECT — project name (e.g. "MyProject")
  AZURE_DEVOPS_PAT     — personal access token

API base: https://dev.azure.com/{org}/{project}/_apis/

Usage:
    adapter = AzureDevOpsAdapter(org="myorg", project="MyProject")
    run_id  = adapter.trigger_workflow("agentic-stlc-pipeline", "main", {"FULL_RUN": "true"})
    status  = adapter.get_workflow_status(run_id)

Git operations use Azure DevOps Git repos (adapter.clone / push are available
via the standard Git HTTPS remote with PAT authentication).
"""
from __future__ import annotations

import base64
import os
import subprocess
from typing import Any

from .base import CIAdapter, GitAdapter

try:
    import httpx
    _HAS_HTTPX = True
except ImportError:
    _HAS_HTTPX = False


def _auth_header(pat: str) -> dict[str, str]:
    """Azure DevOps uses Basic auth with a base64-encoded PAT."""
    encoded = base64.b64encode(f":{pat}".encode()).decode()
    return {
        "Authorization": f"Basic {encoded}",
        "Content-Type": "application/json",
    }


class AzureDevOpsAdapter(CIAdapter):
    """Azure DevOps Pipelines CI adapter."""

    API_VERSION = "7.1"

    def __init__(
        self,
        org: str = "",
        project: str = "",
        pat: str = "",
    ) -> None:
        self.org     = org     or os.environ.get("AZURE_DEVOPS_ORG", "")
        self.project = project or os.environ.get("AZURE_DEVOPS_PROJECT", "")
        self.pat     = pat     or os.environ.get("AZURE_DEVOPS_PAT", "")

    @property
    def _base(self) -> str:
        return f"https://dev.azure.com/{self.org}/{self.project}/_apis"

    # ── CIAdapter interface ───────────────────────────────────────────────────

    def trigger_workflow(self, workflow_id: str, ref: str, inputs: dict) -> str:
        """
        Queue an Azure Pipeline run.

        workflow_id can be:
          - Pipeline definition ID (integer string, e.g. "42")
          - Pipeline definition name (will be resolved to ID)

        Returns the run ID as a string.
        """
        if not _HAS_HTTPX:
            raise RuntimeError("httpx is required for AzureDevOpsAdapter")

        definition_id = self._resolve_definition_id(workflow_id)

        # Build variables dict from inputs
        variables = {
            k: {"value": str(v), "isSecret": False}
            for k, v in (inputs or {}).items()
        }

        body: dict = {
            "definition": {"id": definition_id},
            "sourceBranch": f"refs/heads/{ref}" if not ref.startswith("refs/") else ref,
        }
        if variables:
            body["variables"] = variables

        resp = httpx.post(
            f"{self._base}/pipelines/{definition_id}/runs",
            headers=_auth_header(self.pat),
            json=body,
            params={"api-version": self.API_VERSION},
            timeout=30,
        )
        if resp.status_code in (200, 201):
            data = resp.json()
            return str(data.get("id", ""))
        raise RuntimeError(f"Azure Pipelines trigger failed: {resp.status_code} — {resp.text[:300]}")

    def get_workflow_status(self, run_id: str) -> dict:
        """Poll Azure Pipelines run status by run ID."""
        if not _HAS_HTTPX:
            return {"status": "unknown"}

        # Attempt to find the run across all pipeline definitions
        resp = httpx.get(
            f"{self._base}/pipelines/runs/{run_id}",
            headers=_auth_header(self.pat),
            params={"api-version": self.API_VERSION},
            timeout=30,
        )
        if resp.status_code != 200:
            return {"status": "unknown", "http_status": resp.status_code}

        data = resp.json()
        state  = data.get("state", "")      # inProgress | completed | canceling
        result = data.get("result")         # succeeded | failed | canceled | None

        return {
            "status":     "completed" if state == "completed" else "in_progress",
            "conclusion": self._map_result(result),
            "html_url":   data.get("_links", {}).get("web", {}).get("href", ""),
            "run_id":     run_id,
            "start_time": data.get("createdDate", ""),
            "finish_time": data.get("finishedDate", ""),
        }

    def download_artifacts(self, run_id: str, output_dir: str) -> list[dict]:
        """Download published artifacts from a pipeline run."""
        if not _HAS_HTTPX:
            return []

        # List artifacts
        resp = httpx.get(
            f"{self._base}/build/builds/{run_id}/artifacts",
            headers=_auth_header(self.pat),
            params={"api-version": self.API_VERSION},
            timeout=30,
        )
        if resp.status_code != 200:
            return []

        import io
        import zipfile
        from pathlib import Path
        results = []
        for artifact in resp.json().get("value", []):
            name    = artifact.get("name", "artifact")
            dl_url  = artifact.get("resource", {}).get("downloadUrl", "")
            if not dl_url:
                continue
            dl_resp = httpx.get(
                dl_url, headers=_auth_header(self.pat), timeout=120, follow_redirects=True
            )
            if dl_resp.status_code == 200:
                dest = Path(output_dir) / name
                dest.mkdir(parents=True, exist_ok=True)
                try:
                    with zipfile.ZipFile(io.BytesIO(dl_resp.content)) as zf:
                        zf.extractall(str(dest))
                except Exception:
                    (dest / f"{name}.bin").write_bytes(dl_resp.content)
                results.append({"name": name, "path": str(dest)})
        return results

    def list_recent_runs(self, workflow_id: str, limit: int = 10) -> list[dict]:
        """List recent pipeline runs for a given definition."""
        if not _HAS_HTTPX:
            return []

        definition_id = self._resolve_definition_id(workflow_id)
        resp = httpx.get(
            f"{self._base}/pipelines/{definition_id}/runs",
            headers=_auth_header(self.pat),
            params={"api-version": self.API_VERSION, "$top": limit},
            timeout=30,
        )
        return resp.json().get("value", []) if resp.status_code == 200 else []

    # ── Azure DevOps Git operations ───────────────────────────────────────────

    def clone(self, repo_name: str, branch: str, target_dir: str) -> dict:
        """Clone an Azure DevOps Git repository."""
        url = (
            f"https://{self.pat}@dev.azure.com/{self.org}/{self.project}/_git/{repo_name}"
        )
        cmd = ["git", "clone", "--branch", branch, "--depth", "1", url, target_dir]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            return {"success": result.returncode == 0, "stderr": result.stderr[:500]}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    # ── Azure DevOps extras ───────────────────────────────────────────────────

    def get_run_timeline(self, run_id: str) -> list[dict]:
        """Fetch the timeline (tasks + stages) for a run."""
        if not _HAS_HTTPX:
            return []
        resp = httpx.get(
            f"{self._base}/build/builds/{run_id}/timeline",
            headers=_auth_header(self.pat),
            params={"api-version": self.API_VERSION},
            timeout=30,
        )
        return resp.json().get("records", []) if resp.status_code == 200 else []

    def get_run_logs(self, run_id: str, log_id: int = 1) -> str:
        """Fetch log text for a specific log ID within a run."""
        if not _HAS_HTTPX:
            return ""
        resp = httpx.get(
            f"{self._base}/build/builds/{run_id}/logs/{log_id}",
            headers=_auth_header(self.pat),
            timeout=30,
        )
        return resp.text if resp.status_code == 200 else ""

    def cancel_run(self, run_id: str) -> bool:
        """Cancel an in-progress pipeline run."""
        if not _HAS_HTTPX:
            return False
        resp = httpx.patch(
            f"{self._base}/build/builds/{run_id}",
            headers=_auth_header(self.pat),
            json={"status": "cancelling"},
            params={"api-version": self.API_VERSION},
            timeout=15,
        )
        return resp.status_code == 200

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _resolve_definition_id(self, workflow_id: str) -> int:
        """Resolve pipeline name to integer definition ID."""
        if workflow_id.isdigit():
            return int(workflow_id)

        if not _HAS_HTTPX:
            raise ValueError("Cannot resolve pipeline name without httpx")

        resp = httpx.get(
            f"{self._base}/pipelines",
            headers=_auth_header(self.pat),
            params={"api-version": self.API_VERSION, "name": workflow_id},
            timeout=30,
        )
        if resp.status_code == 200:
            items = resp.json().get("value", [])
            if items:
                return int(items[0]["id"])
        raise ValueError(f"Pipeline '{workflow_id}' not found in Azure DevOps project '{self.project}'")

    @staticmethod
    def _map_result(azure_result: str | None) -> str | None:
        if azure_result is None:
            return None
        return {
            "succeeded":           "success",
            "failed":              "failure",
            "canceled":            "cancelled",
            "partiallySucceeded":  "failure",
        }.get(azure_result, "failure")
