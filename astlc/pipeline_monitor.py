"""
PipelineMonitor — concurrent real-time observer for GitHub Actions + HyperExecute.

Polls both APIs simultaneously (using threading) and streams live updates
via an on_update callback. Returns a structured summary when the pipeline
completes (or times out).

Usage:
    monitor = PipelineMonitor(
        github_token=os.environ["GITHUB_TOKEN"],
        lt_username=os.environ["LT_USERNAME"],
        lt_access_key=os.environ["LT_ACCESS_KEY"],
        repo_slug="org/repo",
        on_update=print,
    )
    summary = monitor.run(run_id="12345678", he_job_id="job-abc")
"""
from __future__ import annotations

import os
import sys
import time
import threading
from datetime import datetime, timezone
from typing import Any, Callable, Optional

UpdateFn = Callable[[str], None]


class PipelineMonitor:
    """Concurrent observer for GitHub Actions workflow + HyperExecute job."""

    _GITHUB_API = "https://api.github.com"
    _HE_API     = "https://api.hyperexecute.cloud"

    def __init__(
        self,
        github_token: str = "",
        lt_username:  str = "",
        lt_access_key: str = "",
        repo_slug: str = "",
        on_update: UpdateFn | None = None,
    ) -> None:
        self._gh_token   = github_token or os.environ.get("GITHUB_TOKEN", "")
        self._lt_user    = lt_username  or os.environ.get("LT_USERNAME", "")
        self._lt_key     = lt_access_key or os.environ.get("LT_ACCESS_KEY", "")
        self._repo       = repo_slug
        self._on_update  = on_update or (lambda _: None)

    # ── Public ────────────────────────────────────────────────────────────────

    def wait_for_completion(self, run_id: str, he_job_id: str = "") -> dict:
        """Alias for run() — used by ProgrammaticExecutionEngine._stage_monitor()."""
        return self.run(run_id=run_id, he_job_id=he_job_id)

    def run(
        self,
        run_id: str,
        he_job_id: str = "",
        poll_interval_s: int = 90,
        max_wait_s: int = 1800,
    ) -> dict:
        """
        Poll GitHub Actions and (optionally) HyperExecute concurrently.

        Returns a summary dict:
          {
            "github": { "conclusion", "duration_s", "jobs": [...] },
            "hyperexecute": { "status", "passed", "failed", "flaky", "shards", "duration_s" },
            "overall_passed": bool,
          }
        """
        result: dict[str, Any] = {"github": {}, "hyperexecute": {}, "overall_passed": False}
        errors: list[str] = []

        gh_done   = threading.Event()
        he_done   = threading.Event()
        lock      = threading.Lock()

        def _gh_thread():
            try:
                gh_result = self._poll_github(run_id, poll_interval_s, max_wait_s, gh_done)
                with lock:
                    result["github"] = gh_result
            except Exception as exc:
                errors.append(f"GitHub monitor error: {exc}")
                print(f"[pipeline_monitor] github thread error: {exc}", file=sys.stderr)
            finally:
                gh_done.set()

        def _he_thread():
            if not he_job_id:
                he_done.set()
                return
            try:
                he_result = self._poll_hyperexecute(he_job_id, poll_interval_s, max_wait_s, he_done)
                with lock:
                    result["hyperexecute"] = he_result
            except Exception as exc:
                errors.append(f"HyperExecute monitor error: {exc}")
                print(f"[pipeline_monitor] he thread error: {exc}", file=sys.stderr)
            finally:
                he_done.set()

        threads = [
            threading.Thread(target=_gh_thread, name="gh-monitor", daemon=True),
            threading.Thread(target=_he_thread, name="he-monitor", daemon=True),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=max_wait_s + 60)

        gh  = result.get("github", {})
        he  = result.get("hyperexecute", {})
        result["overall_passed"] = (
            gh.get("conclusion") == "success"
            and (not he_job_id or he.get("status") in ("completed", "passed", ""))
        )
        if errors:
            result["errors"] = errors
        return result

    # ── GitHub Actions polling ────────────────────────────────────────────────

    def _poll_github(self, run_id: str, interval: int, max_wait: int, stop_event: threading.Event) -> dict:
        try:
            import httpx
        except ImportError:
            self._emit("httpx not installed — cannot monitor GitHub Actions")
            return {"error": "httpx not installed"}

        headers = {
            "Authorization": f"Bearer {self._gh_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        url      = f"{self._GITHUB_API}/repos/{self._repo}/actions/runs/{run_id}"
        start    = time.monotonic()
        deadline = start + max_wait
        last_status = ""
        last_jobs_emitted: set[str] = set()

        self._emit(f"[GitHub] Monitoring workflow run #{run_id} ...")
        not_found_retries = 0
        _MAX_404_RETRIES  = 6  # wait up to ~9 min for run to appear before giving up

        while time.monotonic() < deadline and not stop_event.is_set():
            try:
                resp = httpx.get(url, headers=headers, timeout=20)
                if resp.status_code == 200:
                    not_found_retries = 0
                    data       = resp.json()
                    status     = data.get("status", "")
                    conclusion = data.get("conclusion") or ""
                    html_url   = data.get("html_url", "")

                    if status != last_status:
                        suffix = f" ({conclusion.upper()})" if conclusion else ""
                        self._emit(f"[GitHub] Workflow status: {status.upper()}{suffix}")
                        last_status = status

                    # Emit per-job updates
                    jobs = self._fetch_gh_jobs(run_id, headers)
                    for j in jobs:
                        key = f"{j['name']}:{j['status']}:{j.get('conclusion','')}"
                        if key not in last_jobs_emitted:
                            jstatus = j["status"].upper()
                            if j.get("conclusion"):
                                jstatus += f" ({j['conclusion'].upper()})"
                            self._emit(f"[GitHub]   Job '{j['name']}': {jstatus}")
                            last_jobs_emitted.add(key)

                    if status in ("completed", "cancelled", "timed_out"):
                        elapsed = round(time.monotonic() - start, 1)
                        self._emit(
                            f"[GitHub] Workflow finished: {conclusion.upper()} "
                            f"in {round(elapsed / 60, 1)}m  {html_url}"
                        )
                        return {
                            "run_id":     run_id,
                            "status":     status,
                            "conclusion": conclusion,
                            "html_url":   html_url,
                            "jobs":       jobs,
                            "duration_s": elapsed,
                        }
                elif resp.status_code == 404:
                    not_found_retries += 1
                    if not_found_retries >= _MAX_404_RETRIES:
                        self._emit(f"[GitHub] Run #{run_id} still not found after {not_found_retries} retries — giving up.")
                        break
                    self._emit(f"[GitHub] Run #{run_id} not visible yet (retry {not_found_retries}/{_MAX_404_RETRIES})...")
            except Exception as exc:
                self._emit(f"[GitHub] Poll error: {exc}")

            time.sleep(interval)

        elapsed = round(time.monotonic() - start, 1)
        return {
            "run_id": run_id, "status": "timeout", "conclusion": "timeout",
            "html_url": "", "jobs": [], "duration_s": elapsed,
        }

    def _fetch_gh_jobs(self, run_id: str, headers: dict) -> list[dict]:
        try:
            import httpx
            resp = httpx.get(
                f"{self._GITHUB_API}/repos/{self._repo}/actions/runs/{run_id}/jobs",
                headers=headers, timeout=20,
            )
            if resp.status_code == 200:
                jobs = []
                for j in resp.json().get("jobs", []):
                    started   = _parse_iso(j.get("started_at"))
                    completed = _parse_iso(j.get("completed_at"))
                    dur = (completed - started).total_seconds() if completed and started else 0
                    jobs.append({
                        "name":       j.get("name", ""),
                        "status":     j.get("status", ""),
                        "conclusion": j.get("conclusion") or "",
                        "duration_s": dur,
                    })
                return jobs
        except Exception:
            pass
        return []

    # ── HyperExecute polling ──────────────────────────────────────────────────

    def _poll_hyperexecute(self, job_id: str, interval: int, max_wait: int, stop_event: threading.Event) -> dict:
        try:
            import httpx
        except ImportError:
            self._emit("httpx not installed — cannot monitor HyperExecute")
            return {"error": "httpx not installed"}

        import base64
        creds   = base64.b64encode(f"{self._lt_user}:{self._lt_key}".encode()).decode()
        headers = {"Authorization": f"Basic {creds}"}
        url     = f"{self._HE_API}/v2.0/job/{job_id}"
        start   = time.monotonic()
        deadline = start + max_wait
        last_status = ""
        last_shard_emit: dict[str, str] = {}

        self._emit(f"[HyperExecute] Monitoring job {job_id} ...")

        while time.monotonic() < deadline and not stop_event.is_set():
            try:
                resp = httpx.get(url, headers=headers, timeout=20)
                if resp.status_code == 200:
                    data   = resp.json()
                    status = data.get("status", data.get("jobStatus", ""))

                    if status != last_status:
                        self._emit(f"[HyperExecute] Job status: {status.upper()}")
                        last_status = status

                    # Shard-level progress
                    tasks = data.get("tasks", data.get("shards", []))
                    passed = failed = flaky = pending = 0
                    for task in tasks:
                        ts = task.get("status", "")
                        tc = task.get("conclusion", "") or task.get("result", "")
                        tid = task.get("taskId") or task.get("id", "")
                        key = f"{tid}:{ts}:{tc}"
                        if key != last_shard_emit.get(str(tid)):
                            self._emit(f"[HyperExecute]   Shard {tid}: {ts.upper()}{' (' + tc.upper() + ')' if tc else ''}")
                            last_shard_emit[str(tid)] = key
                        if tc in ("passed", "success") or ts == "completed" and tc == "":
                            passed += 1
                        elif tc in ("failed", "error"):
                            failed += 1
                        elif tc == "flaky":
                            flaky += 1
                        else:
                            pending += 1

                    if status in ("completed", "passed", "failed", "cancelled", "timed_out", "error"):
                        elapsed = round(time.monotonic() - start, 1)
                        self._emit(
                            f"[HyperExecute] Job finished: {status.upper()} in {round(elapsed / 60, 1)}m "
                            f"| Passed: {passed}, Failed: {failed}, Flaky: {flaky}"
                        )
                        return {
                            "job_id":   job_id,
                            "status":   status,
                            "shards":   len(tasks),
                            "passed":   passed,
                            "failed":   failed,
                            "flaky":    flaky,
                            "pending":  pending,
                            "duration_s": elapsed,
                            "dashboard": f"https://hyperexecute.lambdatest.com/task-queue/{job_id}",
                        }
                elif resp.status_code in (401, 403):
                    self._emit("[HyperExecute] Auth error (401/403) — check LT_USERNAME and LT_ACCESS_KEY")
                    break
                elif resp.status_code == 404:
                    self._emit(f"[HyperExecute] Job {job_id} not found (404)")
                    break
            except Exception as exc:
                self._emit(f"[HyperExecute] Poll error: {exc}")

            time.sleep(interval)

        elapsed = round(time.monotonic() - start, 1)
        return {
            "job_id": job_id, "status": "timeout", "shards": 0,
            "passed": 0, "failed": 0, "flaky": 0, "duration_s": elapsed,
        }

    # ── Utility ───────────────────────────────────────────────────────────────

    def _emit(self, msg: str) -> None:
        self._on_update(f"> {msg}")


def _parse_iso(s: str | None):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
