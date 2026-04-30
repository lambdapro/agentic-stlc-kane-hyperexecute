import argparse
import json
import os
import subprocess
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path


TARGET_URL = "https://ecommerce-playground.lambdatest.io/"


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--requirements", default="requirements")
    parser.add_argument("--output", default="requirements/analyzed_requirements.json")
    parser.add_argument("--kane-results", default="reports/kane_results.json")
    parser.add_argument("--skip-kane", action="store_true")
    return parser.parse_args()


def extract_acceptance_criteria(text):
    """Extracts acceptance criteria using deterministic line parsing."""
    criteria = []
    lines = [line.strip() for line in text.splitlines()]
    capture = False
    for line in lines:
        # Match "Acceptance Criteria" with or without trailing colon
        if line.lower().strip().rstrip(":").startswith("acceptance criteria"):
            capture = True
            continue
        if capture:
            # Stop capturing if we hit a separator, a new story, or user story narrative
            if not line or line.startswith("---") or line.lower().startswith("title") or \
               any(line.lower().startswith(p) for p in ["as a ", "i want to ", "so that ", "acceptance criteria"]):
                capture = False
                continue
            criteria.append(line)
    return [c for c in criteria if c.strip()]


def make_title(description):
    lowered = description.lower()
    if "view a list of available products" in lowered or "product section" in lowered:
        return "Navigate to products section and view product list"
    if "use filters" in lowered or "refine results" in lowered:
        return "Use filters to refine product results"
    if "click on a product" in lowered or "view details" in lowered:
        return "Click a product to view details including price and description"
    if "without logging in" in lowered:
        return "View product highlights without logging in"
    if "selected filters or search criteria" in lowered:
        return "Relevant results based on selected filters"
    words = description.replace(".", "").replace(":", "").split()
    return " ".join(words[:10]).strip().capitalize()


EXIT_STATUS = {0: "passed", 1: "failed", 2: "error", 3: "timeout"}


def run_kane(description):
    username = os.environ.get("LT_USERNAME", "")
    access_key = os.environ.get("LT_ACCESS_KEY", "")
    if not username or not access_key:
        return {
            "status": "skipped",
            "summary": "Skipped Kane run: LT credentials not available.",
            "final_state": {},
            "duration": None,
            "link": "",
        }

    # Credentials are passed inline on every run command.
    # kane-cli login must NOT be used in CI; it opens an OAuth browser flow.
    # Browser runs on LambdaTest's infrastructure via the Playwright WSS endpoint
    # so no local Chrome installation is needed on the CI runner.
    # LambdaTest Playwright CDP requires capabilities as a URL query parameter.
    # Embedding user:key@ in the host causes a 400 "unable to parse capabilities".
    playwright_version = ""
    try:
        result = subprocess.run(
            ["playwright", "--version"], capture_output=True, text=True, check=False
        )
        parts = result.stdout.strip().split()
        playwright_version = parts[1] if len(parts) >= 2 else ""
    except Exception:
        pass

    caps = {
        "browserName": "Chrome",
        "browserVersion": "latest",
        "LT:Options": {
            "platform": "Windows 10",
            "build": "Kane AI Requirement Verification",
            "name": "Requirement Analysis",
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
    command = [
        "kane-cli", "run", description,
        TARGET_URL,
        "--username", username,
        "--access-key", access_key,
        "--ws-endpoint", ws_endpoint,
        "--agent",
        "--headless",
        "--timeout", "120",
        "--max-steps", "15",
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)

    # Map standard Kane CLI exit codes (0 pass, 1 fail, 2 error, 3 timeout)
    exit_status = EXIT_STATUS.get(completed.returncode, "error")

    # Parse the full NDJSON stream from both stdout and stderr.
    # Some Kane CLI versions write the agent stream to stderr.
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
        # Surface the raw output so the CI log shows what Kane actually emitted
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
        # summary is the full narrative; one_liner is the short title
        "summary": run_end.get("summary", ""),
        "one_liner": run_end.get("one_liner", ""),
        # step_end summaries become the scenario steps in manage_scenarios.py
        "steps": step_summaries,
        "final_state": run_end.get("final_state", {}),
        "duration": run_end.get("duration"),
        # test_url links directly to the TestMu AI dashboard session
        "test_url": run_end.get("test_url", ""),
    }


def main():
    args = parse_args()
    req_path = Path(args.requirements)
    criteria = []
    
    if req_path.is_dir():
        for req_file in sorted(req_path.glob("*.txt")):
            criteria.extend(extract_acceptance_criteria(req_file.read_text(encoding="utf-8")))
    else:
        criteria = extract_acceptance_criteria(req_path.read_text(encoding="utf-8"))
        
    today = datetime.now(timezone.utc).date().isoformat()

    analyzed = []
    kane_results = []

    if args.skip_kane:
        results = [{
            "status": "pending",
            "summary": "Kane run not attempted.",
            "one_liner": "",
            "steps": [],
            "final_state": {},
            "duration": None,
            "test_url": "",
        } for _ in criteria]
    else:
        with ThreadPoolExecutor(max_workers=5) as executor:
            results = list(executor.map(run_kane, criteria))

    for index, (description, kane) in enumerate(zip(criteria, results), start=1):
        test_url = kane.get("test_url", "")
        item = {
            "id": f"AC-{index:03d}",
            "title": make_title(description),
            "description": description,
            "url": TARGET_URL,
            "kane_status": kane["status"],
            # one_liner: short scenario title derived from what Kane AI observed
            "kane_one_liner": kane.get("one_liner", ""),
            # summary: full narrative; used as expected_result in scenarios
            "kane_summary": kane["summary"],
            # steps: step_end summaries; used as scenario steps in manage_scenarios.py
            "kane_steps": kane.get("steps", []),
            "kane_final_state": kane["final_state"],
            "kane_duration": kane["duration"],
            # test_url links to the TestMu AI dashboard session for this criterion
            "kane_links": [test_url] if test_url else [],
            "last_analyzed": today,
        }
        analyzed.append(item)
        kane_results.append(
            {
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
            }
        )

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


if __name__ == "__main__":
    main()
