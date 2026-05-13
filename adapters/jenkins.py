"""
Jenkins CI adapter.

Triggers Jenkins builds via the Jenkins REST API (build-with-parameters).
Polls status using the build queue and build status endpoints.

Authentication: Jenkins username + API token via env vars
  JENKINS_URL       — base URL, e.g. https://jenkins.example.com
  JENKINS_USER      — Jenkins username
  JENKINS_API_TOKEN — Jenkins API token (not password)

Usage:
    adapter = JenkinsAdapter(base_url="https://jenkins.example.com")
    run_id  = adapter.trigger_workflow("agentic-stlc-pipeline", "main", {"FULL_RUN": "true"})
    status  = adapter.get_workflow_status(run_id)
"""
from __future__ import annotations

import os
import time
from typing import Any

from .base import CIAdapter

try:
    import httpx
    _HAS_HTTPX = True
except ImportError:
    _HAS_HTTPX = False


class JenkinsAdapter(CIAdapter):
    """Jenkins CI/CD adapter."""

    def __init__(
        self,
        base_url: str = "",
        username: str = "",
        api_token: str = "",
    ) -> None:
        self.base_url  = (base_url  or os.environ.get("JENKINS_URL", "")).rstrip("/")
        self.username  = username   or os.environ.get("JENKINS_USER", "")
        self.api_token = api_token  or os.environ.get("JENKINS_API_TOKEN", "")

    # ── CIAdapter interface ───────────────────────────────────────────────────

    def trigger_workflow(self, workflow_id: str, ref: str, inputs: dict) -> str:
        """
        Trigger a Jenkins job (workflow_id = job name, ref = branch/tag).

        For pipeline jobs with parameters, passes inputs as build parameters.
        Returns queue item URL (used as run_id for status polling).
        """
        if not _HAS_HTTPX:
            raise RuntimeError("httpx is required for JenkinsAdapter")

        params = {k: v for k, v in inputs.items()}
        if ref:
            params.setdefault("BRANCH", ref)

        url = f"{self.base_url}/job/{workflow_id}/buildWithParameters"
        resp = httpx.post(
            url,
            auth=(self.username, self.api_token),
            params=params,
            timeout=30,
        )

        if resp.status_code in (200, 201):
            # Jenkins returns Location header with queue item URL
            location = resp.headers.get("Location", "")
            if location:
                return location  # e.g. https://jenkins/queue/item/123/
            return "triggered"

        raise RuntimeError(f"Jenkins trigger failed: {resp.status_code} — {resp.text[:300]}")

    def get_workflow_status(self, run_id: str) -> dict:
        """
        Poll workflow/build status.
        run_id can be:
          - Queue item URL returned by trigger_workflow
          - Build URL (https://jenkins/job/name/42/)
        """
        if not _HAS_HTTPX:
            return {"status": "unknown"}

        # If it's a queue URL, resolve to actual build URL
        if "queue" in run_id:
            build_url = self._resolve_queue(run_id)
            if not build_url:
                return {"status": "queued", "conclusion": None}
        else:
            build_url = run_id.rstrip("/")

        resp = httpx.get(
            f"{build_url}/api/json",
            auth=(self.username, self.api_token),
            timeout=30,
        )
        if resp.status_code != 200:
            return {"status": "unknown", "http_status": resp.status_code}

        data = resp.json()
        building = data.get("building", False)
        result   = data.get("result")  # SUCCESS, FAILURE, ABORTED, UNSTABLE, None

        return {
            "status":     "in_progress" if building else "completed",
            "conclusion": self._map_result(result),
            "html_url":   build_url,
            "duration_ms": data.get("duration", 0),
            "build_number": data.get("number"),
        }

    def download_artifacts(self, run_id: str, output_dir: str) -> list[dict]:
        """Download archived artifacts from a completed Jenkins build."""
        if not _HAS_HTTPX:
            return []

        build_url = run_id.rstrip("/")
        resp = httpx.get(
            f"{build_url}/api/json?tree=artifacts[*]",
            auth=(self.username, self.api_token),
            timeout=30,
        )
        if resp.status_code != 200:
            return []

        import os as _os
        from pathlib import Path
        results = []
        for art in resp.json().get("artifacts", []):
            rel_path = art.get("relativePath", "")
            filename = art.get("fileName", rel_path.split("/")[-1])
            art_url  = f"{build_url}/artifact/{rel_path}"

            dl = httpx.get(art_url, auth=(self.username, self.api_token), timeout=60)
            if dl.status_code == 200:
                dest = Path(output_dir) / filename
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(dl.content)
                results.append({"name": filename, "path": str(dest)})
        return results

    def list_recent_runs(self, workflow_id: str, limit: int = 10) -> list[dict]:
        """List recent builds for a Jenkins job."""
        if not _HAS_HTTPX:
            return []

        resp = httpx.get(
            f"{self.base_url}/job/{workflow_id}/api/json?tree=builds[number,status,result,url,timestamp]{{{limit}}}",
            auth=(self.username, self.api_token),
            timeout=30,
        )
        if resp.status_code == 200:
            return resp.json().get("builds", [])
        return []

    # ── Jenkins-specific extras ───────────────────────────────────────────────

    def get_build_log(self, build_url: str, start: int = 0) -> str:
        """Stream build console log. Returns text from byte offset `start`."""
        if not _HAS_HTTPX:
            return ""
        resp = httpx.get(
            f"{build_url.rstrip('/')}/logText/progressiveText",
            auth=(self.username, self.api_token),
            params={"start": start},
            timeout=30,
        )
        return resp.text if resp.status_code == 200 else ""

    def abort_build(self, build_url: str) -> bool:
        """Abort a running build."""
        if not _HAS_HTTPX:
            return False
        resp = httpx.post(
            f"{build_url.rstrip('/')}/stop",
            auth=(self.username, self.api_token),
            timeout=15,
        )
        return resp.status_code in (200, 302)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _resolve_queue(self, queue_url: str, max_wait_s: int = 60) -> str:
        """Wait for queue item to become a build; return build URL."""
        if not _HAS_HTTPX:
            return ""
        deadline = time.monotonic() + max_wait_s
        while time.monotonic() < deadline:
            resp = httpx.get(
                f"{queue_url.rstrip('/')}/api/json",
                auth=(self.username, self.api_token),
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                executable = data.get("executable")
                if executable:
                    return executable.get("url", "")
            time.sleep(5)
        return ""

    @staticmethod
    def _map_result(jenkins_result: str | None) -> str | None:
        if jenkins_result is None:
            return None
        return {
            "SUCCESS":  "success",
            "FAILURE":  "failure",
            "ABORTED":  "cancelled",
            "UNSTABLE": "failure",
        }.get(jenkins_result, "failure")
