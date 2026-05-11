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


def _kane_exe():
    """Return the kane-cli executable, resolving .cmd wrapper on Windows."""
    exe = shutil.which("kane-cli")
    if exe is None and sys.platform == "win32":
        exe = shutil.which("kane-cli.cmd")
    return exe or "kane-cli"


KANE_EXE = _kane_exe()

TARGET_URL = os.environ.get("POWERAPPS_URL", "https://apps.powerapps.com/play/")


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
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False, encoding="utf-8", errors="replace")

    exit_status = EXIT_STATUS.get(completed.returncode, "error")

    run_end = None
    step_summaries = []
    combined = completed.stdout + "\n" + completed.stderr
    for raw in combined.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            continue
        event_type = event.get("type", "")
        if event_type in ("step_end", "stepEnd") and event.get("summary"):
            step_summaries.append(event["summary"])
        elif event_type in ("run_end", "runEnd"):
            run_end = event

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
        }

    return {
        "status": run_end.get("status", exit_status),
        "summary": run_end.get("summary", ""),
        "one_liner": run_end.get("one_liner", ""),
        "steps": step_summaries,
        "final_state": run_end.get("final_state", {}),
        "duration": run_end.get("duration"),
        "test_url": run_end.get("test_url", ""),
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
        } for _ in criteria]
        cache_hit = False
    else:
        print(f"[Stage 1] Running KaneAI in parallel (workers=5, {len(criteria)} criteria)...")
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
    print(f"\n[Stage 1] COMPLETE — {len(analyzed)} criteria | {mode_label} | {elapsed:.1f}s")
    emit_metrics("stage1_kane", elapsed, cache_hit=cache_hit, criteria_count=len(criteria))


if __name__ == "__main__":
    main()
