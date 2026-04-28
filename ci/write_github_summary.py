import argparse
import json
import os
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", required=True)
    parser.add_argument("--run-url", default="")
    return parser.parse_args()


def load_json(path, default):
    file_path = Path(path)
    if not file_path.exists():
        return default
    return json.loads(file_path.read_text(encoding="utf-8"))


def append(text):
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        print(text)
        return
    with open(summary_path, "a", encoding="utf-8") as handle:
        handle.write(text)
        if not text.endswith("\n"):
            handle.write("\n")


def render_analyze(run_url):
    requirements = load_json("requirements/analyzed_requirements.json", [])
    passed = [item for item in requirements if item.get("kane_status") == "passed"]
    failed = [item for item in requirements if item.get("kane_status") == "failed"]
    
    # Calculate estimated token savings (Theoretical: 1 Kane Run = 50k tokens saved)
    token_savings = len(requirements) * 50000

    lines = [
        "## Analyze Requirements",
        "",
        f"Plain-English outcome: analyzed {len(requirements)} acceptance criteria and checked how many Kane AI could verify against the live LambdaTest eCommerce site.",
        f"- Kane passed: {len(passed)}",
        f"- Kane failed: {len(failed)}",
        f"- **Estimated Token Savings:** ~{token_savings:,} tokens (by offloading UI reasoning to Kane AI)",
        "",
    ]
    for item in requirements:
        kane_links = item.get("kane_links", [])
        link_str = f" ([View Session]({kane_links[0]}))" if kane_links and len(kane_links) > 0 and kane_links[0] else ""
        lines.append(f"- {item['id']} `{item['kane_status']}`: {item['title']}{link_str}")
    if run_url:
        lines.append(f"- GitHub Actions run: {run_url}")
    return "\n".join(lines) + "\n"


def render_manage(run_url):
    scenarios = load_json("scenarios/scenarios.json", [])
    counts = {}
    for scenario in scenarios:
        counts[scenario.get("status", "unknown")] = counts.get(scenario.get("status", "unknown"), 0) + 1
    lines = [
        "## Manage Scenarios",
        "",
        "Plain-English outcome: synchronized the scenario catalog with the analyzed requirements and updated lifecycle status for each scenario.",
    ]
    for key in sorted(counts):
        lines.append(f"- {key}: {counts[key]}")
    if run_url:
        lines.append(f"- GitHub Actions run: {run_url}")
    return "\n".join(lines) + "\n"


def render_generate(run_url):
    objectives = load_json("kane/objectives.json", [])
    lines = [
        "## Generate Tests",
        "",
        f"Plain-English outcome: generated or refreshed {len(objectives)} Selenium test mappings and Kane objectives from the current scenario set.",
    ]
    for item in objectives:
        lines.append(f"- {item['scenario_id']} -> {item['test_case_id']}")
    if run_url:
        lines.append(f"- GitHub Actions run: {run_url}")
    return "\n".join(lines) + "\n"


def render_select(run_url):
    manifest = load_json("reports/test_execution_manifest.json", {})
    selected = manifest.get("selected_scenarios", [])
    lines = [
        "## Select Tests",
        "",
        f"Plain-English outcome: prepared a `{manifest.get('run_type', 'unknown')}` execution manifest with {len(selected)} selected scenarios for HyperExecute.",
    ]
    for item in selected:
        lines.append(f"- Selected scenario: {item}")
    if run_url:
        lines.append(f"- GitHub Actions run: {run_url}")
    return "\n".join(lines) + "\n"


def render_execute(run_url):
    result = load_json("reports/hyperexecute-result.json", {})
    summary = result.get("summary", {})
    job_id = result.get("id", "unknown")
    job_link = summary.get("job_link", "")
    lines = [
        "## Execute Selenium On HyperExecute",
        "",
        "Plain-English outcome: sent the selected Selenium tests to HyperExecute so execution happened in ephemeral cloud workers rather than inside the GitHub runner.",
        f"- HyperExecute job id: {job_id}",
        f"- HyperExecute status: {summary.get('status', 'unknown')}",
        f"- HyperExecute tasks: {summary.get('total_tasks', 'unknown')}",
        f"- HyperExecute failed tasks: {summary.get('failed_tasks', 0)}",
    ]
    if job_link:
        lines.append(f"- HyperExecute job: {job_link}")
        lines.append(f"- Selenium reports artifact: https://hyperexecute.lambdatest.com/artifact/view/{job_id}?artifactName=selenium-test-reports")
        lines.append(f"- Runtime logs artifact: https://hyperexecute.lambdatest.com/artifact/view/{job_id}?artifactName=hyperexecute-runtime")
    if run_url:
        lines.append(f"- GitHub Actions run: {run_url}")
    return "\n".join(lines) + "\n"


def render_failures(run_url):
    content = Path("reports/hyperexecute_failure_analysis.md").read_text(encoding="utf-8") if Path("reports/hyperexecute_failure_analysis.md").exists() else "Failure analysis was not generated."
    lines = [
        "## Analyze HyperExecute Failures",
        "",
        "Plain-English outcome: consolidated HyperExecute signals, downloaded test artifacts, and RCA details into a single markdown report.",
        "",
        content,
    ]
    if run_url:
        lines.append(f"\n- GitHub Actions run: {run_url}\n")
    return "\n".join(lines)


def render_report(run_url):
    release = Path("reports/release_recommendation.md").read_text(encoding="utf-8") if Path("reports/release_recommendation.md").exists() else "Release recommendation was not generated."
    trace = Path("reports/traceability_matrix.md").read_text(encoding="utf-8") if Path("reports/traceability_matrix.md").exists() else "Traceability matrix was not generated."
    lines = [
        "## Final Report",
        "",
        "Plain-English outcome: assembled the final traceability view, release recommendation, and HyperExecute/Kane evidence into a single delivery package for this workflow run.",
        "",
        trace,
        "",
        release,
    ]
    if run_url:
        lines.append(f"\n- GitHub Actions run: {run_url}\n")
    return "\n".join(lines)


def main():
    args = parse_args()
    renderers = {
        "analyze": render_analyze,
        "manage": render_manage,
        "generate": render_generate,
        "select": render_select,
        "execute": render_execute,
        "analyze-failures": render_failures,
        "report": render_report,
    }
    append(renderers[args.stage](args.run_url))


if __name__ == "__main__":
    main()
