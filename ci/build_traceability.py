import argparse
import json
import xml.etree.ElementTree as ET
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--requirements", default="requirements/analyzed_requirements.json")
    parser.add_argument("--scenarios", default="scenarios/scenarios.json")
    parser.add_argument("--manifest", default="reports/test_execution_manifest.json")
    parser.add_argument("--pytest-junit", default="reports/junit.xml")
    parser.add_argument("--kane-results", default="reports/kane_results.json")
    parser.add_argument("--out", default="reports/traceability_matrix.md")
    parser.add_argument("--json-out", default="reports/traceability_matrix.json")
    return parser.parse_args()


FUNCTION_NAMES = {
    "SC-001": "test_sc_001_navigate_to_products_and_view_list",
    "SC-002": "test_sc_002_filter_products_by_category",
    "SC-003": "test_sc_003_click_product_view_details",
    "SC-004": "test_sc_004_product_highlights_visible_without_login",
    "SC-005": "test_sc_005_relevant_results_for_selected_filter",
}


def load_json(path, default):
    file_path = Path(path)
    if not file_path.exists():
        return default
    return json.loads(file_path.read_text(encoding="utf-8"))


def load_kane_execution_results(reports_dir):
    """Read per-test Selenium result files written by the conftest fixture."""
    results = {}
    for f in sorted(Path(reports_dir).glob("kane_result_SC-*.json")):
        try:
            item = json.loads(f.read_text(encoding="utf-8"))
            results[item["scenario_id"]] = item
        except Exception:
            continue
    return results


def load_he_task_results(api_details_path="reports/api_details.json"):
    """
    Build a function-name → {status, session_link} map from HyperExecute API data.
    This is the most reliable source for CI runs where conftest files may not reach
    the Actions runner.
    """
    p = Path(api_details_path)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    results = {}
    for task in data.get("he_tasks", []):
        name = task.get("name", "")
        if name:
            results[name] = {
                "status": task.get("status", "unknown"),
                "session_link": task.get("session_link", ""),
            }
    return results


def load_junit_results(path):
    file_path = Path(path)
    if not file_path.exists():
        return {}
    results = {}
    xml_files = [file_path] if file_path.is_file() else sorted(file_path.rglob("*.xml"))
    for xml_file in xml_files:
        try:
            root = ET.fromstring(xml_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        for testcase in root.iter("testcase"):
            name = testcase.attrib.get("name", "")
            result = "passed"
            if testcase.find("failure") is not None or testcase.find("error") is not None:
                result = "failed"
            elif testcase.find("skipped") is not None:
                result = "skipped"
            results[name] = result
    return results


def main():
    args = parse_args()
    requirements = load_json(args.requirements, [])
    scenarios = load_json(args.scenarios, [])
    manifest = load_json(args.manifest, {})
    kane_results = {
        item["requirement_id"]: item for item in load_json(args.kane_results, [])
    }
    kane_execution = load_kane_execution_results(Path(args.pytest_junit).parent)
    junit_results = load_junit_results(args.pytest_junit)
    he_task_results = load_he_task_results()
    scenarios_by_requirement = {scenario["requirement_id"]: scenario for scenario in scenarios}

    rows = []
    executed = 0
    passed = 0
    untested = []
    failing = []

    for requirement in requirements:
        scenario = scenarios_by_requirement.get(requirement["id"])
        test_case_id = scenario.get("test_case_id") if scenario else "n/a"
        scenario_id = scenario.get("id") if scenario else "n/a"
        function_name = FUNCTION_NAMES.get(scenario_id, f"test_{scenario_id.lower().replace('-', '_')}")

        # Selenium result priority:
        # 1. conftest-written kane_result_SC-*.json (local runs, most precise)
        # 2. HyperExecute API task data from api_details.json (CI runs on HE)
        # 3. junit.xml (last resort)
        kane_exec = kane_execution.get(scenario_id, {})
        selenium_session_link = kane_exec.get("link", "")
        if kane_exec:
            selenium_result = kane_exec.get("status", "not_run")
        else:
            he_task = he_task_results.get(function_name, {})
            if he_task:
                selenium_result = he_task.get("status", "not_run")
                selenium_session_link = he_task.get("session_link", "")
            else:
                selenium_result = junit_results.get(function_name, "not_run")

        # analyzed_requirements.json is the canonical Stage 1 source.
        # kane_results.json is supplemental; only use when kane_status is absent
        # (e.g. legacy runs that predated the field).
        kane_result = (
            requirement.get("kane_status")
            or kane_results.get(requirement["id"], {}).get("status")
            or "unknown"
        )
        # Kane AI session link: test_url from run_end stored in kane_links
        kane_links = requirement.get("kane_links", [])
        kane_session_link = kane_links[0] if kane_links else ""
        # one_liner and summary from run_end NDJSON for the report detail section
        kane_one_liner = requirement.get("kane_one_liner", "")
        kane_summary = requirement.get("kane_summary", "")
        kane_steps = requirement.get("kane_steps", [])

        if selenium_result != "not_run":
            overall = selenium_result
            executed += 1
            if selenium_result == "passed":
                passed += 1
            if overall != "passed":
                failing.append(scenario_id)
        else:
            untested.append(requirement["id"])
            overall = "not_run"

        rows.append(
            {
                "requirement_id": requirement["id"],
                "acceptance_criterion": requirement["description"],
                "scenario_id": scenario_id,
                "test_case_id": test_case_id,
                # Kane AI verification fields (Stage 1)
                "kane_ai_result": kane_result,
                "kane_session_link": kane_session_link,
                "kane_one_liner": kane_one_liner,
                "kane_summary": kane_summary,
                "kane_steps": kane_steps,
                # Selenium execution fields (Stage 4)
                "selenium_result": selenium_result,
                "session_link": selenium_session_link,
                "analysis_note": "" if selenium_result != "not_run" else "Test result not yet available.",
                "overall": overall,
            }
        )

    pass_rate = round((passed / executed) * 100, 1) if executed else 0.0
    # Only flag requirements as untested when selenium actually ran for at least some tests.
    # If executed == 0, no selenium results are available yet — omit the untested warning.
    untested_to_report = [
        req_id for req_id in untested
        if executed > 0
    ]
    summary = {
        "run_type": manifest.get("run_type", "unknown"),
        "requirements_covered": len([row for row in rows if row["scenario_id"] != "n/a"]),
        "requirements_total": len(requirements),
        "executed": executed,
        "passed": passed,
        "pass_rate": pass_rate,
        "untested_requirements": untested_to_report,
        "failing_scenarios": [scenario_id for scenario_id in failing if scenario_id != "n/a"],
    }

    lines = [
        "# Traceability Matrix",
        "",
        f"- Run type: {summary['run_type']}",
        f"- Requirements covered: {summary['requirements_covered']}/{summary['requirements_total']}",
        f"- Selenium pass rate: {summary['pass_rate']}% ({summary['passed']} passed, {summary['executed'] - summary['passed']} failed or skipped)",
        "",
        "| Req ID | Acceptance Criterion | Scenario | Test Case | Kane Verify | What Kane Saw | Overall |",
        "|---|---|---|---|---|---|---|",
    ]

    for row in rows:
        one_liner = row.get("kane_one_liner", "") or "-"
        lines.append(
            f"| {row['requirement_id']} "
            f"| {row['acceptance_criterion']} "
            f"| {row['scenario_id']} "
            f"| {row['test_case_id']} "
            f"| {row['kane_ai_result']} "
            f"| {one_liner} "
            f"| {row['overall']} |"
        )

    # Detail section: expand kane_steps and kane_summary for each requirement
    lines.extend(["", "## Kane AI Verification Detail", ""])
    for row in rows:
        lines.append(f"### {row['requirement_id']} - {row['acceptance_criterion']}")
        if row.get("kane_one_liner"):
            lines.append(f"> {row['kane_one_liner']}")
        lines.append("")
        if row.get("kane_steps"):
            lines.append("**Steps observed by Kane AI:**")
            lines.extend([f"- {step}" for step in row["kane_steps"]])
            lines.append("")
        if row.get("kane_summary"):
            lines.append(f"**Full summary:** {row['kane_summary']}")
            lines.append("")
        if row.get("kane_session_link"):
            lines.append(f"**TestMu AI session:** [{row['kane_session_link']}]({row['kane_session_link']})")
            lines.append("")

    # Only warn when Kane explicitly failed; not for pending/skipped/unknown
    kane_only_issues = [
        row for row in rows
        if row["selenium_result"] == "passed" and row["kane_ai_result"] == "failed"
    ]
    if kane_only_issues:
        lines.extend(["", "## Kane Analysis Warnings", ""])
        lines.extend([
            f"- {row['scenario_id']}: Kane analysis returned `failed` while Selenium passed."
            for row in kane_only_issues
        ])

    if summary["untested_requirements"]:
        lines.extend(["", "## Untested Requirements", ""])
        lines.extend([f"- {item}" for item in summary["untested_requirements"]])

    if summary["failing_scenarios"]:
        lines.extend(["", "## Failing Scenarios", ""])
        lines.extend([f"- {item}" for item in summary["failing_scenarios"]])

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    json_path = Path(args.json_out)
    json_path.write_text(json.dumps({"summary": summary, "rows": rows}, indent=2) + "\n", encoding="utf-8")

    print(f"traceability_rows={len(rows)} pass_rate={pass_rate}")


if __name__ == "__main__":
    main()
