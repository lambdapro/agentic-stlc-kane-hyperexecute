"""
Fetch enriched job data from HyperExecute and Kane AI APIs.
Writes reports/api_details.json for use by write_github_summary.py.
"""
import base64
import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path


def load_json(path, default):
    p = Path(path)
    if not p.exists():
        return default
    content = p.read_text(encoding="utf-8").strip()
    return json.loads(content) if content else default


def basic_auth_header():
    username = os.environ.get("LT_USERNAME", "")
    access_key = os.environ.get("LT_ACCESS_KEY", "")
    if not username or not access_key:
        return {}
    encoded = base64.b64encode(f"{username}:{access_key}".encode()).decode()
    return {"Authorization": f"Basic {encoded}"}


def get(url, headers, timeout=30):
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def extract_he_job_id(failure_analysis_path="reports/hyperexecute_failure_analysis.md"):
    path = Path(failure_analysis_path)
    if not path.exists():
        return ""
    match = re.search(
        r"hyperexecute\.lambdatest\.com/hyperexecute/task\?jobId=([\w-]+)",
        path.read_text(encoding="utf-8"),
    )
    return match.group(1) if match else ""


def fetch_he_job(job_id, headers):
    """Fetch job summary and per-task results from HyperExecute API."""
    try:
        data = get(f"https://api.hyperexecute.cloud/v2.0/jobs/{job_id}", headers)
        return data
    except Exception:
        pass
    try:
        data = get(f"https://api.hyperexecute.cloud/v1.0/jobs/{job_id}", headers)
        return data
    except Exception:
        return {}


def fetch_he_tasks(job_id, headers):
    """Fetch individual task/test results for the job."""
    try:
        data = get(f"https://api.hyperexecute.cloud/v1.0/jobs/{job_id}/tasks", headers)
        return data.get("data", data) if isinstance(data, dict) else data
    except Exception:
        return []


def fetch_kane_session(session_id, headers):
    """Fetch Kane AI session details by session ID."""
    try:
        data = get(
            f"https://api.kaneai.lambdatest.com/api/v1/he-sessions/{session_id}",
            headers,
        )
        return data
    except Exception:
        pass
    try:
        data = get(
            f"https://api.kaneai.lambdatest.com/api/v1/sessions/{session_id}",
            headers,
        )
        return data
    except Exception:
        return {}


def extract_session_id(kane_link):
    """Extract session/run ID from a Kane AI URL."""
    if not kane_link:
        return ""
    match = re.search(r"[?&/](?:sessionId|runId|id)=?([\w-]+)", kane_link)
    return match.group(1) if match else ""


def main():
    headers = basic_auth_header()
    requirements = load_json("requirements/analyzed_requirements.json", [])

    job_id = extract_he_job_id()
    he_job = {}
    he_tasks = []

    if job_id and headers:
        print(f"Fetching HyperExecute job {job_id} via API...")
        he_job = fetch_he_job(job_id, headers)
        he_tasks = fetch_he_tasks(job_id, headers)
        print(f"  job keys: {list(he_job.keys())}")
        print(f"  tasks: {len(he_tasks)}")

    # ── Build per-task map ──────────────────────────────────────────────────
    task_results = []
    for task in (he_tasks if isinstance(he_tasks, list) else []):
        task_id = task.get("id") or task.get("taskId", "")
        name = task.get("testName") or task.get("name", "")
        status = task.get("status", "unknown")
        session_link = (
            task.get("sessionLink")
            or task.get("session_link")
            or task.get("videoLink")
            or ""
        )
        task_results.append({
            "task_id": task_id,
            "name": name,
            "status": status,
            "session_link": session_link,
        })

    # ── Fetch Kane AI session details ──────────────────────────────────────
    kane_sessions = []
    if headers:
        for req in requirements:
            for link in req.get("kane_links", []):
                if not link:
                    continue
                session_id = extract_session_id(link)
                detail = {}
                if session_id:
                    print(f"Fetching Kane session {session_id}...")
                    detail = fetch_kane_session(session_id, headers)
                kane_sessions.append({
                    "requirement_id": req["id"],
                    "link": link,
                    "session_id": session_id,
                    "detail": detail,
                })

    # ── HyperExecute summary from API ──────────────────────────────────────
    he_summary = {}
    if he_job:
        summary_block = he_job.get("summary") or he_job.get("data", {})
        if isinstance(summary_block, dict):
            he_summary = summary_block
        status = (
            he_job.get("status")
            or he_summary.get("status")
            or "unknown"
        )
        total = (
            he_job.get("totalTasks")
            or he_job.get("total_tasks")
            or he_summary.get("total_tasks")
            or len(he_tasks)
        )
        failed = (
            he_job.get("failedTasks")
            or he_job.get("failed_tasks")
            or he_summary.get("failed_tasks")
            or 0
        )
        he_summary = {
            "job_id": job_id,
            "job_link": f"https://hyperexecute.lambdatest.com/hyperexecute/task?jobId={job_id}",
            "selenium_reports_link": f"https://hyperexecute.lambdatest.com/artifact/view/{job_id}?artifactName=selenium-test-reports",
            "runtime_logs_link": f"https://hyperexecute.lambdatest.com/artifact/view/{job_id}?artifactName=hyperexecute-runtime",
            "status": status,
            "total_tasks": total,
            "failed_tasks": failed,
            "raw": he_job,
        }
    elif job_id:
        he_summary = {
            "job_id": job_id,
            "job_link": f"https://hyperexecute.lambdatest.com/hyperexecute/task?jobId={job_id}",
            "selenium_reports_link": f"https://hyperexecute.lambdatest.com/artifact/view/{job_id}?artifactName=selenium-test-reports",
            "runtime_logs_link": f"https://hyperexecute.lambdatest.com/artifact/view/{job_id}?artifactName=hyperexecute-runtime",
            "status": "unknown",
            "total_tasks": 0,
            "failed_tasks": 0,
        }

    out = {
        "he_summary": he_summary,
        "he_tasks": task_results,
        "kane_sessions": kane_sessions,
    }

    out_path = Path("reports/api_details.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {out_path}  (job_id={job_id}, tasks={len(task_results)}, kane_sessions={len(kane_sessions)})")


if __name__ == "__main__":
    main()
