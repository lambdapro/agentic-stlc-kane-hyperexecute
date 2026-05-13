"""
GitHub + GitHub Actions adapters.

GitHubAdapter       — repository operations (clone, push, PR)
GitHubActionsAdapter — workflow operations (trigger, poll, artifacts)

Both use the GitHub REST API v3. Auth via GITHUB_TOKEN env var.
"""
from __future__ import annotations

import os
import subprocess
import time
from typing import Any

from .base import CIAdapter, GitAdapter

try:
    import httpx
    _HAS_HTTPX = True
except ImportError:
    _HAS_HTTPX = False


def _api(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _repo_slug(repository: str) -> str:
    """Extract 'owner/repo' from full URL or slug."""
    if repository.startswith("https://github.com/"):
        return repository.removeprefix("https://github.com/").rstrip("/")
    return repository.strip("/")


class GitHubAdapter(GitAdapter):
    """GitHub repository adapter."""

    def __init__(self, token: str = "", repo: str = "") -> None:
        self.token = token or os.environ.get("GITHUB_TOKEN", "")
        self.repo  = _repo_slug(repo)
        self.base_url = "https://api.github.com"

    def clone(self, url: str, branch: str, target_dir: str) -> dict:
        cmd = ["git", "clone", "--branch", branch, "--depth", "1", url, target_dir]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            return {"success": result.returncode == 0, "stderr": result.stderr[:500]}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def push(self, branch: str, commit_message: str, files: list[str]) -> dict:
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
        if not _HAS_HTTPX:
            return {"success": False, "error": "httpx not installed"}
        resp = httpx.post(
            f"{self.base_url}/repos/{self.repo}/pulls",
            headers=_api(self.token),
            json={"title": title, "body": body, "head": head, "base": base},
            timeout=30,
        )
        if resp.status_code == 201:
            data = resp.json()
            return {"success": True, "pr_url": data["html_url"], "pr_number": data["number"]}
        return {"success": False, "status": resp.status_code, "body": resp.text[:300]}

    def get_file_content(self, path: str, ref: str = "HEAD") -> str:
        if not _HAS_HTTPX:
            return ""
        import base64
        resp = httpx.get(
            f"{self.base_url}/repos/{self.repo}/contents/{path}",
            headers=_api(self.token),
            params={"ref": ref},
            timeout=30,
        )
        if resp.status_code == 200:
            content = resp.json().get("content", "")
            return base64.b64decode(content).decode("utf-8")
        return ""


class GitHubActionsAdapter(CIAdapter):
    """GitHub Actions workflow adapter."""

    def __init__(self, token: str = "", repo: str = "") -> None:
        self.token = token or os.environ.get("GITHUB_TOKEN", "")
        self.repo  = _repo_slug(repo)
        self.base_url = "https://api.github.com"

    def trigger_workflow(self, workflow_id: str, ref: str, inputs: dict) -> str:
        if not _HAS_HTTPX:
            return ""
        resp = httpx.post(
            f"{self.base_url}/repos/{self.repo}/actions/workflows/{workflow_id}/dispatches",
            headers=_api(self.token),
            json={"ref": ref, "inputs": inputs},
            timeout=30,
        )
        if resp.status_code == 204:
            time.sleep(3)
            runs = self.list_recent_runs(workflow_id, limit=1)
            return str(runs[0].get("id", "")) if runs else ""
        return ""

    def get_workflow_status(self, run_id: str) -> dict:
        if not _HAS_HTTPX:
            return {}
        resp = httpx.get(
            f"{self.base_url}/repos/{self.repo}/actions/runs/{run_id}",
            headers=_api(self.token),
            timeout=30,
        )
        if resp.status_code == 200:
            data = resp.json()
            return {
                "status":     data.get("status"),
                "conclusion": data.get("conclusion"),
                "html_url":   data.get("html_url"),
                "run_id":     run_id,
            }
        return {"error": resp.status_code}

    def download_artifacts(self, run_id: str, output_dir: str) -> list[dict]:
        if not _HAS_HTTPX:
            return []
        resp = httpx.get(
            f"{self.base_url}/repos/{self.repo}/actions/runs/{run_id}/artifacts",
            headers=_api(self.token),
            timeout=30,
        )
        if resp.status_code != 200:
            return []
        import io
        import zipfile
        from pathlib import Path
        results = []
        for artifact in resp.json().get("artifacts", []):
            name     = artifact["name"]
            dl_url   = artifact["archive_download_url"]
            dl_resp  = httpx.get(dl_url, headers=_api(self.token), timeout=60, follow_redirects=True)
            if dl_resp.status_code == 200:
                dest = Path(output_dir) / name
                dest.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(io.BytesIO(dl_resp.content)) as zf:
                    zf.extractall(str(dest))
                results.append({"name": name, "path": str(dest)})
        return results

    def list_recent_runs(self, workflow_id: str, limit: int = 10) -> list[dict]:
        if not _HAS_HTTPX:
            return []
        resp = httpx.get(
            f"{self.base_url}/repos/{self.repo}/actions/workflows/{workflow_id}/runs",
            headers=_api(self.token),
            params={"per_page": limit},
            timeout=30,
        )
        if resp.status_code == 200:
            return resp.json().get("workflow_runs", [])
        return []
