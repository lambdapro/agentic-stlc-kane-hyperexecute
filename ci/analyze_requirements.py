import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from stage_utils import print_stage_header, print_stage_result

# On GitHub Actions: /home/runner/.testmuai/kaneai/sessions/
# On Windows local:  C:/Users/<user>/.testmuai/kaneai/sessions/
KANE_SESSIONS_DIR = Path.home() / ".testmuai" / "kaneai" / "sessions"
_KANE_PROJECT_CONFIGURED = False


def _parse_file_url(raw: str) -> str:
    """Convert a file:// URL (from Kane's CodeExport link) to an OS path.

    Handles both Linux  (file:///home/runner/...) and Windows
    (file:///C:/Users/...) formats that appear in Kane CLI terminal output.
    """
    token = raw.strip()
    if not token.lower().startswith("file://"):
        return token  # already a plain path
    # Strip the scheme — leaves ///home/... or ///C:/...
    no_scheme = token[7:]           # e.g.  /home/runner/... or /C:/Users/...
    if sys.platform == "win32":
        # file:///C:/path → /C:/path → strip leading slash → C:/path
        if no_scheme.startswith("/") and len(no_scheme) > 2 and no_scheme[2] == ":":
            no_scheme = no_scheme[1:]
    return no_scheme


def _resolve_code_export_path(raw_path: str) -> str:
    """Given a path that may point to a file or a directory, return the
    parent code-export directory only if it contains .py files."""
    p = Path(raw_path)
    # If it's already a directory, use it directly
    candidates = [p, p.parent]
    for c in candidates:
        if c.is_dir() and any(c.glob("*.py")):
            return str(c)
    return ""


def _find_code_export_by_session_id(session_id: str) -> str:
    """Construct and verify the code-export path from a known Kane session ID.

    This is the authoritative lookup on GitHub Actions where session IDs are
    available via NDJSON and the sessions directory is at a fixed location.
    The path is deterministic: KANE_SESSIONS_DIR/<session_id>/code-export/
    """
    if not session_id:
        return ""
    candidate = KANE_SESSIONS_DIR / session_id / "code-export"
    if candidate.is_dir() and any(candidate.glob("*.py")):
        return str(candidate)
    return ""


def _kane_exe():
    """Return the kane-cli executable, resolving .cmd wrapper on Windows."""
    exe = shutil.which("kane-cli")
    if exe is None and sys.platform == "win32":
        exe = shutil.which("kane-cli.cmd")
    return exe or "kane-cli"


KANE_EXE = _kane_exe()

TARGET_URL = os.environ.get("TARGET_URL", "https://ecommerce-playground.lambdatest.io/")


def _configure_kane_project():
    """Configure Kane CLI Test Manager project and folder once per process."""
    global _KANE_PROJECT_CONFIGURED
    if _KANE_PROJECT_CONFIGURED:
        return
    project_id = os.environ.get("KANE_PROJECT_ID", "")
    folder_id = os.environ.get("KANE_FOLDER_ID", "")
    if project_id:
        subprocess.run([KANE_EXE, "config", "project", project_id],
                       capture_output=True, text=True, check=False)
        print(f"[Stage 1] Kane project configured: {project_id}")
    if folder_id:
        subprocess.run([KANE_EXE, "config", "folder", folder_id],
                       capture_output=True, text=True, check=False)
        print(f"[Stage 1] Kane folder configured: {folder_id}")
    _KANE_PROJECT_CONFIGURED = True




def build_name():
    """Consistent build label shared by KaneAI and Playwright sessions in the same run."""
    run_number = os.environ.get("GITHUB_RUN_NUMBER", "")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"Agentic STLC #{run_number} | {today}" if run_number else f"Agentic STLC | {today}"


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--requirements", default="requirements")
    parser.add_argument("--output", default="requirements/analyzed_requirements.json")
    parser.add_argument("--kane-results", default="reports/kane_results.json")
    parser.add_argument("--skip-kane", action="store_true")
    parser.add_argument("--demo-mode", action="store_true",
                        help="Load pre-generated results from ci/demo_kane_results.json instead of calling Kane")
    return parser.parse_args()


def extract_acceptance_criteria(text):
    """Extracts acceptance criteria using deterministic line parsing."""
    criteria = []
    lines = [line.strip() for line in text.splitlines()]
    capture = False
    for line in lines:
        if line.lower().strip().rstrip(":").startswith("acceptance criteria"):
            capture = True
            continue
        if capture:
            if not line or line.startswith("---") or line.lower().startswith("title") or \
               any(line.lower().startswith(p) for p in ["as a ", "i want to ", "so that ", "acceptance criteria"]):
                capture = False
                continue
            criteria.append(line)
    return [c for c in criteria if c.strip()]


def make_title(description):
    words = description.replace(".", "").replace(":", "").split()
    return " ".join(words[:10]).strip().capitalize()


EXIT_STATUS = {0: "passed", 1: "failed", 2: "error", 3: "timeout"}


def _run_kane_indexed(args):
    return run_kane(*args)


def run_kane(index, description):
    username = os.environ.get("LT_USERNAME", "")
    access_key = os.environ.get("LT_ACCESS_KEY", "")
    if not username or not access_key:
        return {
            "status": "skipped",
            "summary": "Skipped Kane run: LT credentials not available.",
            "one_liner": "",
            "steps": [],
            "final_state": {},
            "duration": None,
            "test_url": "",
        }

    playwright_version = ""
    try:
        result = subprocess.run(
            ["playwright", "--version"], capture_output=True, text=True, check=False
        )
        parts = result.stdout.strip().split()
        playwright_version = parts[1] if len(parts) >= 2 else ""
    except Exception:
        pass

    session_name = f"AC-{index:03d} | {description[:80].strip()}"

    caps = {
        "browserName": "Chrome",
        "browserVersion": "latest",
        "LT:Options": {
            "platform": "Windows 10",
            "build": build_name(),
            "name": session_name,
            "user": username,
            "accessKey": access_key,
            "network": True,
            "video": True,
            "console": True,
            "tunnel": False,
            "tunnelName": "",
            "playwrightClientVersion": playwright_version,
        },
    }
    ws_endpoint = (
        "wss://cdp.lambdatest.com/playwright?capabilities="
        + urllib.parse.quote(json.dumps(caps))
    )
    task = f"On {TARGET_URL} — {description}"
    command = [
        KANE_EXE, "run", task,
        "--username", username,
        "--access-key", access_key,
        "--ws-endpoint", ws_endpoint,
        "--agent",
        "--headless",
        "--timeout", "120",
        "--max-steps", "15",
        "--code-export",
        "--code-language", "python",
        "--skip-code-validation",
    ]
    run_start = time.time()
    completed = subprocess.run(command, capture_output=True, text=True, check=False, encoding="utf-8", errors="replace")

    exit_status = EXIT_STATUS.get(completed.returncode, "error")

    run_end = None
    step_summaries = []
    session_id = ""
    code_export_dir = ""
    combined = completed.stdout + "\n" + completed.stderr

    # ── Parse Kane NDJSON + plain-text output ──────────────────────────────
    # Kane CLI emits two kinds of output on stdout/stderr:
    #   1. NDJSON events  — one JSON object per line (step_end, run_end, …)
    #   2. Plain-text lines — the "links box" at session exit, e.g.:
    #        │  CodeExport   file:///home/runner/.testmuai/kaneai/sessions/UUID/code-export/  │
    #      or (without box borders):
    #        CodeExport  file:///home/runner/.testmuai/kaneai/sessions/UUID/code-export/
    #
    # Strategy:
    #   a) Try JSON parse first on every line.
    #   b) For non-JSON lines, scan for a "file://" token adjacent to "CodeExport".
    #   c) Also scan non-JSON lines for a bare UUID-shaped path segment that
    #      looks like a session directory path — this catches cases where Kane
    #      prints the path without the file:// scheme.
    # ────────────────────────────────────────────────────────────────────────
    import re as _re
    _UUID_RE = _re.compile(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        _re.IGNORECASE,
    )

    for raw in combined.splitlines():
        stripped = raw.strip()
        if not stripped:
            continue

        # ── Attempt JSON parse ─────────────────────────────────────────────
        try:
            event = json.loads(stripped)
        except (json.JSONDecodeError, ValueError):
            event = None

        if event is not None:
            event_type = event.get("type", "")
            if event_type in ("step_end", "stepEnd") and event.get("summary"):
                step_summaries.append(event["summary"])
            elif event_type in ("run_end", "runEnd"):
                run_end = event
                # session_id may be on run_end directly, or nested under data/metadata
                session_id = (
                    event.get("session_id")
                    or event.get("sessionId")
                    or event.get("data", {}).get("session_id", "")
                    or ""
                )
            # Some Kane versions emit a dedicated code_export event
            elif event_type in ("code_export", "codeExport"):
                raw_path = event.get("path") or event.get("directory") or ""
                if raw_path:
                    code_export_dir = _resolve_code_export_path(raw_path)
            # session_id can also appear on non-run_end events (e.g. session_start)
            if not session_id:
                session_id = (
                    event.get("session_id")
                    or event.get("sessionId")
                    or ""
                )
            continue

        # ── Plain-text line: look for CodeExport + file:// ─────────────────
        upper = stripped.upper()
        if "CODEEXPORT" in upper.replace(" ", "").replace("-", ""):
            # Extract any file:// token on this line
            for token in stripped.split():
                if token.lower().startswith("file://"):
                    path = _parse_file_url(token)
                    resolved = _resolve_code_export_path(path)
                    if resolved:
                        code_export_dir = resolved
                        break
            # Also try bare path (no file:// scheme) — e.g. /home/runner/...
            if not code_export_dir:
                for token in stripped.split():
                    if "code-export" in token.lower() or "kaneai/sessions" in token.lower():
                        resolved = _resolve_code_export_path(token)
                        if resolved:
                            code_export_dir = resolved
                            break

        # ── Extract session UUID from any line that mentions sessions dir ──
        if not session_id and "sessions" in stripped.lower():
            m = _UUID_RE.search(stripped)
            if m:
                session_id = m.group(0)

    # ── Resolve code-export path ────────────────────────────────────────────
    # Priority:
    #   1. Explicit code_export event or CodeExport link already resolved above
    #   2. Deterministic session-ID lookup (GitHub Actions authoritative path)
    # We do NOT fall back to timestamp-based scanning because concurrent sessions
    # running in the ThreadPoolExecutor would produce ambiguous results.
    if not code_export_dir and session_id:
        code_export_dir = _find_code_export_by_session_id(session_id)

    if not run_end:
        raw_output = (completed.stdout + completed.stderr).strip()
        diagnostic = raw_output[:500] if raw_output else "Kane CLI produced no output."
        return {
            "status": exit_status,
            "summary": diagnostic,
            "one_liner": "",
            "steps": [],
            "final_state": {},
            "duration": None,
            "test_url": "",
            "session_id": session_id,
            "code_export_dir": code_export_dir,
        }

    return {
        "status": run_end.get("status", exit_status),
        "summary": run_end.get("summary", ""),
        "one_liner": run_end.get("one_liner", ""),
        "steps": step_summaries,
        "final_state": run_end.get("final_state", {}),
        "duration": run_end.get("duration"),
        "test_url": run_end.get("test_url", ""),
        "session_id": session_id,
        "code_export_dir": code_export_dir,
    }


def load_demo_results(criteria):
    """Load pre-generated demo Kane results, mapped to the actual criteria list."""
    demo_path = Path("ci/demo_kane_results.json")
    if not demo_path.exists():
        raise FileNotFoundError(
            f"DEMO_MODE requires ci/demo_kane_results.json — file not found at {demo_path}"
        )
    demo_data = json.loads(demo_path.read_text(encoding="utf-8"))
    results = []
    for i, criterion in enumerate(criteria):
        if i < len(demo_data):
            results.append(demo_data[i])
        else:
            results.append({
                "status": "passed",
                "summary": f"Demo result for: {criterion[:60]}",
                "one_liner": f"Criterion verified (demo) — {criterion[:50]}",
                "steps": ["Demo step 1", "Demo step 2"],
                "final_state": {},
                "duration": 42,
                "test_url": "https://automation.lambdatest.com/test?testID=demo",
            })
    return results


def emit_metrics(stage, duration_seconds, cache_hit=False, criteria_count=0):
    """Append timing to pipeline_metrics.json — no-op if file absent."""
    metrics_path = Path("reports/pipeline_metrics.json")
    try:
        metrics = json.loads(metrics_path.read_text()) if metrics_path.exists() else {}
        metrics.setdefault("stages", {})[stage] = {
            "duration_seconds": round(duration_seconds, 2),
            "cache_hit": cache_hit,
            "criteria_count": criteria_count,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        metrics_path.parent.mkdir(parents=True, exist_ok=True)
        metrics_path.write_text(json.dumps(metrics, indent=2))
    except Exception:
        pass


def main():
    args = parse_args()
    demo_mode = args.demo_mode or os.environ.get("DEMO_MODE", "false").lower() == "true"

    Path("reports").mkdir(exist_ok=True)
    print_stage_header("1", "ANALYZE_REQUIREMENTS", "Parse requirements and run KaneAI functional verification")

    req_path = Path(args.requirements)
    criteria = []
    if req_path.is_dir():
        for req_file in sorted(req_path.glob("*.txt")):
            criteria.extend(extract_acceptance_criteria(req_file.read_text(encoding="utf-8")))
    else:
        criteria = extract_acceptance_criteria(req_path.read_text(encoding="utf-8"))

    today = datetime.now(timezone.utc).date().isoformat()
    stage_start = time.time()

    if demo_mode:
        print(f"[DEMO_MODE] Loading pre-generated Kane results for {len(criteria)} criteria")
        results = load_demo_results(criteria)
        cache_hit = True
    elif args.skip_kane:
        results = [{
            "status": "pending", "summary": "Kane run not attempted.",
            "one_liner": "", "steps": [], "final_state": {}, "duration": None, "test_url": "",
            "session_id": "", "code_export_dir": "",
        } for _ in criteria]
        cache_hit = False
    else:
        _configure_kane_project()
        print(f"[Stage 1] Running KaneAI in parallel (workers=5, {len(criteria)} criteria) — code export enabled...")
        with ThreadPoolExecutor(max_workers=5) as executor:
            results = list(executor.map(_run_kane_indexed, enumerate(criteria, start=1)))
        cache_hit = False

    analyzed = []
    kane_results = []

    for index, (description, kane) in enumerate(zip(criteria, results), start=1):
        test_url = kane.get("test_url", "")
        item = {
            "id": f"AC-{index:03d}",
            "title": make_title(description),
            "description": description,
            "url": TARGET_URL,
            "kane_status": kane["status"],
            "kane_one_liner": kane.get("one_liner", ""),
            "kane_summary": kane["summary"],
            "kane_steps": kane.get("steps", []),
            "kane_final_state": kane["final_state"],
            "kane_duration": kane["duration"],
            "kane_links": [test_url] if test_url else [],
            "kane_session_id": kane.get("session_id", ""),
            "kane_code_export_dir": kane.get("code_export_dir", ""),
            "last_analyzed": today,
        }
        analyzed.append(item)
        kane_results.append({
            "requirement_id": item["id"],
            "title": item["title"],
            "status": item["kane_status"],
            "one_liner": item["kane_one_liner"],
            "summary": item["kane_summary"],
            "steps": item["kane_steps"],
            "final_state": item["kane_final_state"],
            "duration": item["kane_duration"],
            "link": test_url,
            "url": item["url"],
        })

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(analyzed, indent=2) + "\n", encoding="utf-8")

    kane_path = Path(args.kane_results)
    kane_path.parent.mkdir(parents=True, exist_ok=True)
    kane_path.write_text(json.dumps(kane_results, indent=2) + "\n", encoding="utf-8")

    print(f"{'ID':8} {'Kane':<9} {'Title':<40} {'Link'}")
    for item in analyzed:
        link = item.get("kane_links", [""])[0] if item.get("kane_links") else ""
        print(f"{item['id']:8} {item['kane_status']:<9} {item['title']:40.40} {link}")

    elapsed = time.time() - stage_start
    mode_label = "demo" if demo_mode else ("cached" if cache_hit else "live")
    passed_count = sum(1 for a in analyzed if a["kane_status"] == "passed")
    failed_count = sum(1 for a in analyzed if a["kane_status"] == "failed")

    print_stage_result("1", "ANALYZE_REQUIREMENTS", {
        "Requirements parsed":  len(analyzed),
        "Criteria analyzed":    f"{len(analyzed)} ({mode_label}, workers=5)",
        "Kane passed":          f"{passed_count}/{len(analyzed)}",
        "Kane failed":          failed_count,
        "Pass rate":            f"{round(passed_count / len(analyzed) * 100, 1) if analyzed else 0}%",
        "Duration":             f"{elapsed:.1f}s",
        "Output":               args.output,
    })
    emit_metrics("stage1_kane", elapsed, cache_hit=cache_hit, criteria_count=len(criteria))


if __name__ == "__main__":
    main()
