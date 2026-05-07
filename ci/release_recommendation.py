import argparse
import json
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace-json", default="reports/traceability_matrix.json")
    parser.add_argument("--out", default="reports/release_recommendation.md")
    return parser.parse_args()


def verdict_for(summary, result_analysis=None):
    has_untested = bool(summary.get("untested_requirements"))
    has_failures = bool(summary.get("failing_scenarios"))
    pass_rate = summary.get("pass_rate", 0)
    risk_level = (result_analysis or {}).get("risk_level", "")
    if pass_rate >= 90 and not has_failures and not has_untested and risk_level != "high":
        return "GREEN", "Approve release because coverage is complete and executed tests passed."
    if pass_rate >= 75 and not has_untested and risk_level != "high":
        return "YELLOW", "Conditional approval because coverage exists but there are remaining execution issues."
    return "RED", "Block release because pass rate or coverage is below the acceptance threshold."


def main():
    args = parse_args()
    payload = json.loads(Path(args.trace_json).read_text(encoding="utf-8"))
    summary = payload["summary"]
    result_analysis = payload.get("result_analysis", {})
    verdict, recommendation = verdict_for(summary, result_analysis)

    failing = summary.get("failing_scenarios", [])
    untested = summary.get("untested_requirements", [])

    lines = [
        "# QA Release Recommendation",
        "",
        f"**Verdict:** {verdict}",
        "",
        "## Summary",
        f"- Requirements covered: {summary['requirements_covered']}/{summary['requirements_total']}",
        f"- Scenarios executed: {summary['executed']}",
        f"- Pass rate: {summary['pass_rate']}% ({summary['passed']} passed, {summary['executed'] - summary['passed']} failed or skipped)",
    ]
    if result_analysis:
        lines.extend([
            f"- Overall health: {result_analysis.get('overall_health', 'unknown')}",
            f"- Risk level: {result_analysis.get('risk_level', 'unknown')}",
            f"- Kane AI pass rate: {result_analysis.get('kane_pass_rate', 0)}%",
        ])

    lines.extend(["", "## Failing Scenarios"])
    lines.extend([f"- {item}" for item in failing] if failing else ["- None"])
    lines.extend(["", "## Untested Requirements"])
    lines.extend([f"- {item}" for item in untested] if untested else ["- None"])

    key_findings = result_analysis.get("key_findings", [])
    if key_findings:
        lines.extend(["", "## Key Findings"])
        lines.extend([f"- {f}" for f in key_findings])

    lines.extend(["", "## Recommendation", recommendation])
    recommendation_hint = result_analysis.get("recommendation_hint", "")
    if recommendation_hint:
        lines.extend(["", f"_{recommendation_hint}_"])

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{verdict}: {recommendation}")


if __name__ == "__main__":
    main()
