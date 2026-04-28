import argparse
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path


TARGET_URL = "https://ecommerce-playground.lambdatest.io/"


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--requirements", default="requirements/search.txt")
    parser.add_argument("--output", default="requirements/analyzed_requirements.json")
    parser.add_argument("--kane-results", default="reports/kane_results.json")
    parser.add_argument("--skip-kane", action="store_true")
    return parser.parse_args()


def extract_acceptance_criteria(text):
    lines = [line.strip() for line in text.splitlines()]
    try:
        start = lines.index("Acceptance Criteria:") + 1
    except ValueError:
        start = len(lines)

    criteria = [line for line in lines[start:] if line]
    combined = []
    i = 0
    while i < len(criteria):
        current = criteria[i]
        next_line = criteria[i + 1] if i + 1 < len(criteria) else None
        if (
            next_line
            and "navigate to the products section" in current.lower()
            and "view a list of available products" in next_line.lower()
        ):
            combined.append(
                "User can navigate to the products section of the site and view a list of available products"
            )
            i += 2
            continue
        combined.append(current)
        i += 1
    return combined


def make_title(description):
    lowered = description.lower()
    if "view a list of available products" in lowered:
        return "Navigate to products section and view product list"
    if "use filters" in lowered:
        return "Use filters to refine product results"
    if "click on a product" in lowered:
        return "Click a product to view details including price and description"
    if "without logging in" in lowered:
        return "View product highlights without logging in"
    if "selected filters or search criteria" in lowered:
        return "Relevant results based on selected filters"
    words = description.replace(".", "").split()
    return " ".join(words[:10]).strip().capitalize()


def run_kane(description):
    username = os.environ.get("LT_USERNAME", "")
    access_key = os.environ.get("LT_ACCESS_KEY", "")
    if not username or not access_key:
        return {
            "status": "skipped",
            "summary": "Skipped Kane run because LT credentials were not available.",
            "final_state": {},
            "duration": None,
            "link": ""
        }

    command = [
        "npx",
        "-y",
        "@testmuai/kane-cli@latest",
        "run",
        description,
        "--url",
        TARGET_URL,
        "--username",
        username,
        "--access-key",
        access_key,
        "--agent",
        "--headless",
        "--timeout",
        "120",
        "--max-steps",
        "15",
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        stderr = completed.stderr.strip() or "Kane CLI did not emit a parseable result."
        return {
            "status": "failed",
            "summary": stderr,
            "final_state": {},
            "duration": None,
            "link": ""
        }

    try:
        payload = json.loads(lines[-1])
    except json.JSONDecodeError:
        return {
            "status": "failed",
            "summary": lines[-1],
            "final_state": {},
            "duration": None,
            "link": ""
        }

    return {
        "status": payload.get("status", "unknown"),
        "summary": payload.get("one_liner", ""),
        "final_state": payload.get("final_state", {}),
        "duration": payload.get("duration"),
        "link": payload.get("link", ""),
    }


def main():
    args = parse_args()
    text = Path(args.requirements).read_text(encoding="utf-8")
    criteria = extract_acceptance_criteria(text)
    today = datetime.now(timezone.utc).date().isoformat()

    analyzed = []
    kane_results = []

    if args.skip_kane:
        results = [{
            "status": "pending",
            "summary": "Kane run not attempted.",
            "final_state": {},
            "duration": None,
            "link": ""
        } for _ in criteria]
    else:
        with ThreadPoolExecutor(max_workers=5) as executor:
            results = list(executor.map(run_kane, criteria))

    for index, (description, kane) in enumerate(zip(criteria, results), start=1):
        item = {
            "id": f"AC-{index:03d}",
            "title": make_title(description),
            "description": description,
            "url": TARGET_URL,
            "kane_status": kane["status"],
            "kane_summary": kane["summary"],
            "kane_final_state": kane["final_state"],
            "kane_duration": kane["duration"],
            "kane_links": [kane["link"]] if kane["link"] else [],
            "last_analyzed": today,
        }
        analyzed.append(item)
        kane_results.append(
            {
                "requirement_id": item["id"],
                "title": item["title"],
                "status": item["kane_status"],
                "summary": item["kane_summary"],
                "final_state": item["kane_final_state"],
                "duration": item["kane_duration"],
                "link": kane["link"],
                "url": item["url"],
            }
        )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(analyzed, indent=2) + "\n", encoding="utf-8")

    kane_path = Path(args.kane_results)
    kane_path.parent.mkdir(parents=True, exist_ok=True)
    kane_path.write_text(json.dumps(kane_results, indent=2) + "\n", encoding="utf-8")

    print("ID       Kane      Title")
    for item in analyzed:
        print(f"{item['id']:8} {item['kane_status']:<9} {item['title']}")


if __name__ == "__main__":
    main()
