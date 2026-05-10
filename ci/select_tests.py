import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path


FUNCTION_NAMES = {
    "SC-001": "test_sc_001_navigate_to_app_and_see_issues_list",
    "SC-002": "test_sc_002_create_new_issue_report",
    "SC-003": "test_sc_003_view_issue_details",
    "SC-004": "test_sc_004_filter_issues_by_status",
    "SC-005": "test_sc_005_navigate_back_from_detail_view",
}


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenarios", default="scenarios/scenarios.json")
    parser.add_argument("--manifest", default="reports/test_execution_manifest.json")
    parser.add_argument("--selection", default="reports/pytest_selection.txt")
    return parser.parse_args()


def function_name_for(scenario_id):
    return FUNCTION_NAMES.get(scenario_id, f"test_{scenario_id.lower().replace('-', '_')}")


def main():
    args = parse_args()
    scenarios = json.loads(Path(args.scenarios).read_text(encoding="utf-8"))
    full_run = os.environ.get("FULL_RUN", "false").lower() == "true"

    selected = []
    excluded = []
    reasons = {}
    for scenario in scenarios:
        status = scenario.get("status", "active")
        if status == "deprecated":
            excluded.append(scenario["id"])
            reasons[scenario["id"]] = "deprecated"
            continue
        if full_run or status in {"new", "updated"}:
            selected.append(scenario)
        elif status == "active":
            excluded.append(scenario["id"])
            reasons[scenario["id"]] = "not part of incremental run"

    run_type = "full" if full_run else "incremental"
    manifest = {
        "run_type": run_type,
        "selected_scenarios": [scenario["id"] for scenario in selected],
        "selected_test_ids": [scenario["test_case_id"] for scenario in selected],
        "excluded_scenarios": excluded,
        "exclusion_reason": reasons,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    manifest_path = Path(args.manifest)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    selection_lines = [
        f"tests/playwright/test_powerapps.py::{function_name_for(scenario['id'])}"
        for scenario in selected
    ]
    selection_path = Path(args.selection)
    selection_path.parent.mkdir(parents=True, exist_ok=True)
    selection_path.write_text("\n".join(selection_lines) + ("\n" if selection_lines else ""), encoding="utf-8")

    print(f"run_type={run_type} selected={len(selected)} excluded={len(excluded)}")


if __name__ == "__main__":
    main()
