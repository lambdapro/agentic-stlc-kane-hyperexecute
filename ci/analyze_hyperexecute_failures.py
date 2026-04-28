import argparse
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--result-json", default="reports/hyperexecute-result.json")
    parser.add_argument("--junit-dir", default="reports")
    parser.add_argument("--cli-log", default="hyperexecute-cli.log")
    parser.add_argument("--out", default="reports/hyperexecute_failure_analysis.md")
    return parser.parse_args()


def load_result(path):
    file_path = Path(path)
    if not file_path.exists():
        return {}
    return json.loads(file_path.read_text(encoding="utf-8"))


def junit_failures(root_dir):
    root = Path(root_dir)
    failures = []
    for xml_file in root.rglob("*.xml"):
        try:
            tree = ET.fromstring(xml_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        for testcase in tree.iter("testcase"):
            failure = testcase.find("failure") or testcase.find("error")
            if failure is None:
                continue
            message = failure.attrib.get("message", "") or failure.text or ""
            lowered = message.lower()
            category = "assertion"
            reason = "Assertion or validation failure"
            if "elementclickinterceptedexception" in lowered:
                category = "ui-intercept"
                reason = "Clickable element was covered or not interactable in the current layout."
            elif "timeout" in lowered:
                category = "timeout"
                reason = "The page did not reach the expected state before the wait timed out."
            elif "auth gate" in lowered or "log in" in lowered:
                category = "auth-or-layout"
                reason = "Guest-visible content assumptions did not match the live page state."
            failures.append(
                {
                    "test": testcase.attrib.get("name", "unknown"),
                    "category": category,
                    "reason": reason,
                    "message": message.strip(),
                    "source": str(xml_file),
                }
            )
    return failures


def cli_highlights(path):
    file_path = Path(path)
    if not file_path.exists():
        return []
    lines = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    highlights = []
    patterns = [
        r"Job Link:\s+(https://\S+)",
        r"remark:\s*(.+)$",
        r"Exiting with error:\s*(.+)$",
    ]
    for line in lines:
        for pattern in patterns:
            match = re.search(pattern, line)
            if match:
                highlights.append(match.group(1).strip())
    deduped = []
    for item in highlights:
        if item not in deduped:
            deduped.append(item)
    return deduped


def main():
    args = parse_args()
    result = load_result(args.result_json)
    failures = junit_failures(args.junit_dir)
    cli_notes = cli_highlights(args.cli_log)

    lines = [
        "# HyperExecute Failure Analysis",
        "",
        f"- Job ID: {result.get('id', 'unknown')}",
        f"- Job Status: {result.get('summary', {}).get('status', 'unknown')}",
        f"- Job Remark: {result.get('remark', 'n/a')}",
    ]

    job_link = result.get("summary", {}).get("job_link")
    if job_link:
        lines.append(f"- Job Link: {job_link}")

    if cli_notes:
        lines.extend(["", "## HyperExecute Signals", ""])
        lines.extend([f"- {note}" for note in cli_notes])

    lines.extend(["", "## Test Failure Breakdown", ""])
    if failures:
        for failure in failures:
            lines.append(f"- {failure['test']}: {failure['category']} - {failure['reason']}")
    else:
        lines.append("- No JUnit failures were found in the downloaded HyperExecute artifacts.")

    lines.extend(["", "## Detailed Messages", ""])
    if failures:
        for failure in failures:
            lines.append(f"- {failure['test']}: {failure['message']}")
    else:
        lines.append("- None")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"failure_entries={len(failures)}")


if __name__ == "__main__":
    main()
