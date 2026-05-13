"""
GitLab CI/CD adapter.

Triggers GitLab CI pipelines via the GitLab REST API and polls status.
Also provides GitLab repository operations (clone, push, merge requests).

Authentication:
  GITLAB_URL           — GitLab instance URL (default: https://gitlab.com)
  GITLAB_TOKEN         — personal access token or project access token
  GITLAB_PROJECT_ID    — project ID or "namespace/project" path (URL-encoded)

API base: https://gitlab.com/api/v4/projects/{project_id}/

Usage:
    adapter = GitLabAdapter(project_id="mygroup/myproject")
    run_id  = adapter.trigger_workflow(".gitlab-ci.yml", "main", {"FULL_RUN": "true"})
    status  = adapter.get_workflow_status(run_id)
"""
from __future__ import annotations

import os
import subprocess
import urllib.parse
from typing import Any

from .base import CIAdapter, GitAdapter

try:
    import httpx
    _HAS_HTTPX = True
except ImportError:
    _HAS_HTTPX = False


class GitLabAdapter(CIAdapter, GitAdapter):
    """
    GitLab CI/CD and repository adapter.

    Implements both CIAdapter (pipeline operations) and
    GitAdapter (repository operations) for GitLab projects.
    """

    def __init__(
        self,
        base_url: str = "",
        token: str = "",
        project_id: str = "",
    ) -> None:
        self.base_url   = (base_url  or os.environ.get("GITLAB_URL", "https://gitlab.com")).rstrip("/")
        self.token      = token      or os.environ.get("GITLAB_TOKEN", "")
        raw_project     = project_id or os.environ.get("GITLAB_PROJECT_ID", "")
        # URL-encode "namespace/project" → "namespace%2Fproject"
        self.project_id = urllib.parse.quote(raw_project, safe="") if "/" in raw_project else raw_project

    @property
    def _headers(self) -> dict[str, str]:
        return {"PRIVATE-TOKEN": self.token, "Content-Type": "application/json"}

    @property
    def _api(self) -> str:
        return f"{self.base_url}/api/v4/projects/{self.project_id}"

    # ── CIAdapter interface ───────────────────────────────────────────────────

    def trigger_workflow(self, workflow_id: str, ref: str, inputs: dict) -> str:
        """
        Create a GitLab pipeline run via pipeline triggers or the pipelines API.

        workflow_id is ignored (GitLab uses .gitlab-ci.yml implicitly).
        Returns the pipeline ID as a string.
        """
        if not _HAS_HTTPX:
            raise RuntimeError("httpx is required for GitLabAdapter")

        # Build variables list from inputs
        variables = [{"key": k, "value": str(v)} for k, v in (inputs or {}).items()]

        body: dict[str, Any] = {"ref": ref}
        if variables:
            body["variables"] = variables

        resp = httpx.post(
            f"{self._api}/pipeline",
            headers=self._headers,
            json=body,
            timeout=30,
        )
        if resp.status_code == 201:
            return str(resp.json().get("id", ""))
        raise RuntimeError(f"GitLab pipeline trigger failed: {resp.status_code} — {resp.text[:300]}")

    def get_workflow_status(self, run_id: str) -> dict:
        """Poll GitLab pipeline status by pipeline ID."""
        if not _HAS_HTTPX:
            return {"status": "unknown"}

        resp = httpx.get(
            f"{self._api}/pipelines/{run_id}",
            headers=self._headers,
            timeout=30,
        )
        if resp.status_code != 200:
            return {"status": "unknown", "http_status": resp.status_code}

        data   = resp.json()
        status = data.get("status", "")  # created | pending | running | success | failed | canceled
        web_url = data.get("web_url", "")

        return {
            "status":     "completed" if status in ("success", "failed", "canceled", "skipped") else "in_progress",
            "conclusion": self._map_status(status),
            "html_url":   web_url,
            "pipeline_id": run_id,
            "ref":         data.get("ref", ""),
            "sha":         data.get("sha", ""),
        }

    def download_artifacts(self, run_id: str, output_dir: str) -> list[dict]:
        """Download artifacts from all jobs in a GitLab pipeline."""
        if not _HAS_HTTPX:
            return []

        # Get jobs for this pipeline
        resp = httpx.get(
            f"{self._api}/pipelines/{run_id}/jobs",
            headers=self._headers,
            timeout=30,
        )
        if resp.status_code != 200:
            return []

        import io
        import zipfile
        from pathlib import Path
        results = []
        for job in resp.json():
            job_id   = job.get("id")
            job_name = job.get("name", str(job_id))
            if not job.get("artifacts"):
                continue

            dl_resp = httpx.get(
                f"{self._api}/jobs/{job_id}/artifacts",
                headers=self._headers,
                timeout=120,
                follow_redirects=True,
            )
            if dl_resp.status_code == 200:
                dest = Path(output_dir) / job_name
                dest.mkdir(parents=True, exist_ok=True)
                try:
                    with zipfile.ZipFile(io.BytesIO(dl_resp.content)) as zf:
                        zf.extractall(str(dest))
                except Exception:
                    (dest / "artifacts.bin").write_bytes(dl_resp.content)
                results.append({"name": job_name, "path": str(dest)})
        return results

    def list_recent_runs(self, workflow_id: str = "", limit: int = 10) -> list[dict]:
        """List recent pipelines for this project."""
        if not _HAS_HTTPX:
            return []
        resp = httpx.get(
            f"{self._api}/pipelines",
            headers=self._headers,
            params={"per_page": limit, "order_by": "id", "sort": "desc"},
            timeout=30,
        )
        return resp.json() if resp.status_code == 200 else []

    # ── GitAdapter interface ──────────────────────────────────────────────────

    def clone(self, url: str, branch: str, target_dir: str) -> dict:
        """Clone a GitLab repository (injects token for auth)."""
        auth_url = url.replace("https://", f"https://oauth2:{self.token}@")
        cmd = ["git", "clone", "--branch", branch, "--depth", "1", auth_url, target_dir]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            return {"success": result.returncode == 0, "stderr": result.stderr[:500]}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def push(self, branch: str, commit_message: str, files: list[str]) -> dict:
        """Stage, commit, and push files to a GitLab repository."""
        try:
            if files:
                subprocess.run(["git", "add"] + files, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", commit_message], check=True, capture_output=True)
            result = subprocess.run(
                ["git", "push", "origin", branch], capture_output=True, text=True, timeout=60
            )
            return {"success": result.returncode == 0, "branch": branch}
        except subprocess.CalledProcessError as exc:
            return {"success": False, "error": exc.stderr or str(exc)}

    def create_pull_request(self, title: str, body: str, head: str, base: str) -> dict:
        """Create a GitLab Merge Request."""
        if not _HAS_HTTPX:
            return {"success": False, "error": "httpx not installed"}

        resp = httpx.post(
            f"{self._api}/merge_requests",
            headers=self._headers,
            json={
                "source_branch": head,
                "target_branch": base,
                "title": title,
                "description": body,
                "remove_source_branch": False,
            },
            timeout=30,
        )
        if resp.status_code == 201:
            data = resp.json()
            return {"success": True, "pr_url": data.get("web_url", ""), "pr_number": data.get("iid")}
        return {"success": False, "status": resp.status_code, "body": resp.text[:300]}

    def get_file_content(self, path: str, ref: str = "HEAD") -> str:
        """Fetch raw file content from GitLab repository."""
        if not _HAS_HTTPX:
            return ""
        encoded_path = urllib.parse.quote(path, safe="")
        resp = httpx.get(
            f"{self._api}/repository/files/{encoded_path}/raw",
            headers=self._headers,
            params={"ref": ref},
            timeout=30,
        )
        return resp.text if resp.status_code == 200 else ""

    # ── GitLab-specific extras ────────────────────────────────────────────────

    def trigger_with_token(self, token: str, ref: str, variables: dict) -> str:
        """Alternative trigger via GitLab pipeline trigger token (CI/CD → Triggers)."""
        if not _HAS_HTTPX:
            return ""
        resp = httpx.post(
            f"{self._api}/trigger/pipeline",
            data={
                "token": token,
                "ref": ref,
                **{f"variables[{k}]": v for k, v in variables.items()},
            },
            timeout=30,
        )
        return str(resp.json().get("id", "")) if resp.status_code == 201 else ""

    def get_job_trace(self, job_id: str) -> str:
        """Fetch the raw trace (log) of a specific job."""
        if not _HAS_HTTPX:
            return ""
        resp = httpx.get(
            f"{self._api}/jobs/{job_id}/trace",
            headers=self._headers,
            timeout=30,
        )
        return resp.text if resp.status_code == 200 else ""

    def retry_pipeline(self, pipeline_id: str) -> str:
        """Retry a failed or cancelled pipeline. Returns new pipeline ID."""
        if not _HAS_HTTPX:
            return ""
        resp = httpx.post(
            f"{self._api}/pipelines/{pipeline_id}/retry",
            headers=self._headers,
            timeout=30,
        )
        return str(resp.json().get("id", "")) if resp.status_code == 201 else ""

    # ── Internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _map_status(gitlab_status: str) -> str | None:
        return {
            "success":  "success",
            "failed":   "failure",
            "canceled": "cancelled",
            "skipped":  "skipped",
            "running":  None,
            "pending":  None,
            "created":  None,
        }.get(gitlab_status)
