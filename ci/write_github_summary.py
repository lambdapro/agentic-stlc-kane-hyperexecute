import json
import os
import re
from pathlib import Path


def load_json(path, default):
    file_path = Path(path)
    if not file_path.exists():
        return default
    content = file_path.read_text(encoding="utf-8").strip()
    if not content:
        return default
    return json.loads(content)


def emit(text):
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    print(text)
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write(text + "\n")


def verdict_emoji(verdict):
    return {"GREEN": "🟢", "YELLOW": "🟡", "RED": "🔴"}.get(verdict, "⚪")


def status_emoji(status):
    if status in ("passed", "active"):
        return "✅"
    if status in ("failed", "deprecated"):
        return "❌"
    if status == "new":
        return "🆕"
    if status == "updated":
        return "🔄"
    return "⏭️"


def extract_he_job_link(failure_analysis_path="reports/hyperexecute_failure_analysis.md"):
    path = Path(failure_analysis_path)
    if not path.exists():
        return "", ""
    text = path.read_text(encoding="utf-8")
    match = re.search(r"https://hyperexecute\.lambdatest\.com/hyperexecute/task\?jobId=([\w-]+)", text)
    if not match:
        return "", ""
    job_id = match.group(1)
    job_link = match.group(0)
    return job_id, job_link


def main():
    run_url = os.environ.get("RUN_URL", "")

    requirements = load_json("requirements/analyzed_requirements.json", [])
    scenarios = load_json("scenarios/scenarios.json", [])
    manifest = load_json("reports/test_execution_manifest.json", {})
    objectives = load_json("kane/objectives.json", [])
    trace_json = load_json("reports/traceability_matrix.json", {})
    api_details = load_json("reports/api_details.json", {})

    he_api = api_details.get("he_summary", {})
    he_tasks_api = api_details.get("he_tasks", [])
    kane_sessions_api = {s["requirement_id"]: s for s in api_details.get("kane_sessions", [])}

    # ── Classify requirements ──────────────────────────────────────────────
    kane_failed = [r for r in requirements if r.get("kane_status") == "failed"]

    # ── Classify scenarios ─────────────────────────────────────────────────
    new_scenarios = [s for s in scenarios if s.get("status") == "new"]
    updated_scenarios = [s for s in scenarios if s.get("status") == "updated"]
    active_scenarios = [s for s in scenarios if s.get("status") == "active"]
    deprecated_scenarios = [s for s in scenarios if s.get("status") == "deprecated"]

    existing_covered_ids = {s["requirement_id"] for s in active_scenarios}
    new_needed_ids = {s["requirement_id"] for s in new_scenarios + updated_scenarios}

    # ── Execution stats ────────────────────────────────────────────────────
    selected = manifest.get("selected_scenarios", [])
    run_type = manifest.get("run_type", "full")
    he_job_id = he_api.get("job_id", "") or extract_he_job_link()[0]
    he_job_link = he_api.get("job_link", "")
    he_selenium_link = he_api.get("selenium_reports_link", "")
    he_runtime_link = he_api.get("runtime_logs_link", "")

    trace_summary = trace_json.get("summary", {})
    trace_rows = trace_json.get("rows", [])
    executed = trace_summary.get("executed", 0)
    passed = trace_summary.get("passed", 0)
    failed_count = executed - passed
    pass_rate = trace_summary.get("pass_rate", 0.0)
    failing_scenarios = trace_summary.get("failing_scenarios", [])
    untested = trace_summary.get("untested_requirements", [])

    # ── Verdict ────────────────────────────────────────────────────────────
    release_md = Path("reports/release_recommendation.md")
    verdict_line = "unknown"
    recommendation_line = ""
    if release_md.exists():
        for line in release_md.read_text(encoding="utf-8").splitlines():
            if line.startswith("**Verdict:**"):
                verdict_line = line.replace("**Verdict:**", "").strip()
            if line.startswith("Approve") or line.startswith("Block") or line.startswith("Conditional"):
                recommendation_line = line.strip()

    emit("# 🤖 Agentic SDLC — Pipeline Run Report")
    emit("")
    if run_url:
        emit(f"> **Run:** {run_url}")
    emit("")

    # ── Stage 1: Requirement Analysis ─────────────────────────────────────
    emit("## Stage 1 · Requirement Analysis")
    emit("")
    if not requirements:
        emit("_No requirements found._")
    else:
        new_req_titles = [
            r["title"] for r in requirements if r["id"] in new_needed_ids
        ]
        existing_req_titles = [
            r["title"] for r in requirements if r["id"] in existing_covered_ids
        ]

        emit(
            f"I analyzed **{len(requirements)} acceptance criteria** from the requirements files "
            f"and ran Kane AI against the live ecommerce site to verify each one."
        )
        emit("")

        if existing_req_titles:
            emit(
                f"**{len(existing_req_titles)} requirement(s) already covered** by existing test cases — no new tests needed:"
            )
            for title in existing_req_titles:
                emit(f"- ✅ {title}")
            emit("")

        if new_req_titles:
            emit(
                f"**{len(new_req_titles)} requirement(s) introduced new coverage needs** — test cases will be generated:"
            )
            for r in requirements:
                if r["id"] in new_needed_ids:
                    icon = status_emoji(r.get("kane_status", "unknown"))
                    kane_links = r.get("kane_links", [])
                    session = kane_sessions_api.get(r["id"], {})
                    session_link = session.get("link") or (kane_links[0] if kane_links else "")
                    link = f" — [session]({session_link})" if session_link else ""
                    # one_liner from run_end: what Kane AI actually observed on the site
                    one_liner = r.get("kane_one_liner", "")
                    observed = f" · _{one_liner}_" if one_liner else ""
                    emit(f"- {icon} `{r['id']}` {r['title']}{observed}{link}")
            emit("")

        if kane_failed:
            emit(f"⚠️ **{len(kane_failed)} criterion/criteria could not be verified by Kane AI:**")
            for r in kane_failed:
                kane_links = r.get("kane_links", [])
                session = kane_sessions_api.get(r["id"], {})
                session_link = session.get("link") or (kane_links[0] if kane_links else "")
                link = f" — [session]({session_link})" if session_link else ""
                one_liner = r.get("kane_one_liner", "")
                observed = f" · _{one_liner}_" if one_liner else ""
                emit(f"- ❌ `{r['id']}` {r['title']}{observed}{link}")
            emit("")

    # ── Stage 2: Scenario Management ──────────────────────────────────────
    emit("## Stage 2 · Scenario Management")
    emit("")
    emit(
        f"I synchronized the scenario catalog with the analyzed requirements. "
        f"Out of **{len(scenarios)} total scenarios**: "
        f"**{len(active_scenarios)} unchanged**, "
        f"**{len(new_scenarios)} new**, "
        f"**{len(updated_scenarios)} updated**, "
        f"**{len(deprecated_scenarios)} deprecated**."
    )
    if new_scenarios or updated_scenarios:
        emit("")
        emit("New and updated scenarios that will be tested this run:")
        for s in new_scenarios + updated_scenarios:
            emit(f"- {status_emoji(s['status'])} `{s['id']}` {s['title']}")
    emit("")

    # ── Stage 3: Test Generation ───────────────────────────────────────────
    emit("## Stage 3 · Test Generation with Kane AI")
    emit("")
    generated_count = len(new_scenarios) + len(updated_scenarios)
    if generated_count:
        emit(
            f"I generated **{generated_count} Selenium test case(s)** using Kane AI objectives — "
            f"one per new or updated scenario. Each test is fully mapped back to its acceptance criterion."
        )
        emit("")
        for obj in objectives:
            sc_id = obj.get("scenario_id", "")
            tc_id = obj.get("test_case_id", "")
            scenario = next((s for s in scenarios if s["id"] == sc_id), {})
            if scenario.get("status") in ("new", "updated"):
                emit(f"- 🆕 `{sc_id}` → `{tc_id}` — {scenario.get('title', obj.get('objective', ''))}")
    else:
        emit("No new test cases were generated — all requirements were already covered.")
    emit("")

    # ── Stage 4a: Test Selection ───────────────────────────────────────────
    emit("## Stage 4a · Test Selection")
    emit("")
    emit(
        f"Running a **{run_type} run** — selected **{len(selected)} scenario(s)** for execution on HyperExecute."
    )
    if selected:
        for sc_id in selected:
            emit(f"- `{sc_id}`")
    emit("")

    # ── Stage 4b: Execution ────────────────────────────────────────────────
    emit("## Stage 4b · Regression Execution at Scale (HyperExecute)")
    emit("")
    emit(
        f"I submitted the selected tests to **LambdaTest HyperExecute** for parallel cloud execution. "
        f"Tests ran across multiple workers simultaneously — no sequential bottleneck."
    )
    emit("")

    he_total = he_api.get("total_tasks") or len(selected)
    he_failed_api = he_api.get("failed_tasks") # Initialize he_failed_api
    he_passed_api = he_api.get("passed_tasks") # Initialize he_passed_api here to prevent UnboundLocalError

    # Ensure summary metrics are consistent with actual execution data for he_failed_api
    if he_failed_api is None:
        if executed > 0:
            he_failed_api = failed_count
        else:
            he_failed_api = he_total if he_total > 0 else 0 # Default to 0 if no tasks

    # Ensure summary metrics are consistent with actual execution data for he_passed_api
    if he_passed_api is None:
        he_passed_api = passed if executed > 0 else 0 # Default to 0 if no tasks

    he_status = he_api.get("status", "unknown")

    emit("| Metric | Value |")
    emit("|---|---|")
    if he_job_link:
        emit(f"| HyperExecute Job | [Open in LambdaTest ↗]({he_job_link}) |")
    else:
        emit(f"| HyperExecute Job ID | `{he_job_id or 'n/a'}` |")
    emit(f"| Status | {he_status} |")
    emit(f"| Total tasks | {he_total} |")
    emit(f"| ✅ Passed | {he_passed_api} |")
    emit(f"| ❌ Failed | {he_failed_api} |")
    if he_selenium_link:
        emit(f"| Selenium reports | [Download artifacts ↗]({he_selenium_link}) |")
    if he_runtime_link:
        emit(f"| Runtime logs | [View logs ↗]({he_runtime_link}) |")
    emit("")

    if he_tasks_api:
        emit("**Per-test results from HyperExecute API:**")
        emit("")
        emit("| Test | Status | Session |")
        emit("|---|---|---|")
        for task in he_tasks_api:
            status_icon = "✅" if task["status"] in ("passed", "completed") else "❌"
            session = f"[View session]({task['session_link']})" if task.get("session_link") else "—"
            emit(f"| `{task['name'] or task['task_id']}` | {status_icon} {task['status']} | {session} |")
        emit("")

    # ── Stage 5: Traceability ──────────────────────────────────────────────
    emit("## Stage 5 · Results with Full Traceability")
    emit("")
    emit(
        f"Every test result is traced back to its requirement. "
        f"**{passed}/{executed}** Selenium tests passed ({pass_rate}% pass rate)."
    )
    emit("")

    if trace_rows:
        emit("| Req | Acceptance Criterion | Scenario | Test Case | Kane AI | What Kane Saw | Result |")
        emit("|---|---|---|---|---|---|---|")
        for row in trace_rows:
            kane = row.get("kane_ai_result", "unknown")
            req_id = row.get("requirement_id", "")
            one_liner = row.get("kane_one_liner", "") or "—"
            overall = row.get("overall", "unknown")
            icon = "✅" if overall == "passed" else "❌"
            criterion = row["acceptance_criterion"][:55] + "…" if len(row["acceptance_criterion"]) > 55 else row["acceptance_criterion"]
            emit(
                f"| `{req_id}` | {criterion} | `{row['scenario_id']}` | `{row['test_case_id']}` "
                f"| {kane} | {one_liner} | {icon} {overall} |"
            )
        emit("")

        # Collapsible Kane AI detail — steps and full summary per requirement
        emit("<details>")
        emit("<summary>Kane AI verification detail (expand)</summary>")
        emit("")
        for row in trace_rows:
            if not row.get("kane_steps") and not row.get("kane_summary"):
                continue
            emit(f"**`{row['requirement_id']}` — {row['acceptance_criterion']}**")
            emit("")
            if row.get("kane_steps"):
                for step in row["kane_steps"]:
                    emit(f"- {step}")
                emit("")
            if row.get("kane_summary"):
                emit(f"_{row['kane_summary']}_")
                emit("")
        emit("</details>")
        emit("")

    if failing_scenarios:
        emit("**Failing scenarios:**")
        for sc in failing_scenarios:
            emit(f"- ❌ `{sc}`")
        emit("")

    if untested and executed > 0:
        emit("**Requirements not yet covered by Selenium:**")
        for req in untested:
            emit(f"- ⚠️ `{req}`")
        emit("")

    # ── Release Recommendation ─────────────────────────────────────────────
    emit("## Release Recommendation")
    emit("")
    icon = verdict_emoji(verdict_line)
    emit(f"### {icon} Verdict: {verdict_line}")
    emit("")
    if recommendation_line:
        emit(recommendation_line)
    emit("")
    emit(
        f"- Requirements covered: **{trace_summary.get('requirements_covered', '?')}/{trace_summary.get('requirements_total', '?')}**"
    )
    emit(f"- Pass rate: **{pass_rate}%** ({passed} passed, {failed_count} failed)")
    if run_url:
        emit(f"- Full run details: {run_url}")
    emit("")


if __name__ == "__main__":
    main()
