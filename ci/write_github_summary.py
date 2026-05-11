"""
GitHub Actions step summary renderer.

Pure data renderer — reads only from real artifacts:
  - requirements/analyzed_requirements.json
  - scenarios/scenarios.json
  - reports/normalized_results.json
  - reports/traceability_matrix.json
  - reports/api_details.json
  - reports/release_recommendation.md
  - reports/validation_report.json
  - reports/test_execution_manifest.json
  - kane/objectives.json

Produces factual tables only. No first-person narration. No fabricated values.
"""
import json
import os
import re
from pathlib import Path


def load_json(path, default):
    p = Path(path)
    if not p.exists():
        return default
    content = p.read_text(encoding="utf-8").strip()
    if not content:
        return default
    try:
        return json.loads(content)
    except Exception:
        return default


def emit(text):
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    # Force UTF-8 on Windows consoles that default to cp1252
    import sys
    out = sys.stdout
    try:
        if hasattr(out, "reconfigure"):
            out.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    print(text)
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write(text + "\n")


def verdict_emoji(verdict):
    return {"GREEN": "🟢", "YELLOW": "🟡", "RED": "🔴"}.get(verdict, "⚪")


def status_icon(status):
    mapping = {
        "passed": "✅",
        "failed": "❌",
        "skipped": "⏭️",
        "data_unavailable": "⚠️",
        "new": "🆕",
        "updated": "🔄",
        "active": "✅",
        "deprecated": "🚫",
    }
    return mapping.get(status, "❓")


def _he_job_id_from_log():
    for path in ("reports/hyperexecute-cli.log", "reports/hyperexecute_failure_analysis.md"):
        p = Path(path)
        if not p.exists():
            continue
        m = re.search(r"jobId=([\w-]+)", p.read_text(encoding="utf-8"))
        if m:
            return m.group(1)
    return ""


def main():
    run_url = os.environ.get("RUN_URL", "")

    requirements = load_json("requirements/analyzed_requirements.json", [])
    scenarios = load_json("scenarios/scenarios.json", [])
    manifest = load_json("reports/test_execution_manifest.json", {})
    trace_json = load_json("reports/traceability_matrix.json", {})
    api_details = load_json("reports/api_details.json", {})
    normalized_raw = load_json("reports/normalized_results.json", {})
    normalized = normalized_raw.get("results", [])
    validation = load_json("reports/validation_report.json", {})

    he_api = api_details.get("he_summary", {})
    _seen_he: dict = {}
    for t in api_details.get("he_tasks", []):
        key = t.get("name") or t.get("task_id", "")
        _seen_he.setdefault(key, t)
    he_tasks_api = list(_seen_he.values())

    trace_summary = trace_json.get("summary", {})
    trace_rows = trace_json.get("rows", [])
    result_analysis = trace_json.get("result_analysis", {})

    executed = trace_summary.get("executed", 0)
    passed = trace_summary.get("passed", 0)
    pass_rate = trace_summary.get("pass_rate", 0.0)
    all_browsers = trace_summary.get("browsers_tested", [])
    failing_scenarios = trace_summary.get("failing_scenarios", [])
    untested = trace_summary.get("untested_requirements", [])

    he_job_id = he_api.get("job_id", "") or _he_job_id_from_log()
    he_job_link = he_api.get("job_link", "") or (
        f"https://hyperexecute.lambdatest.com/hyperexecute/task?jobId={he_job_id}"
        if he_job_id else ""
    )
    he_status = he_api.get("status", "unknown")

    release_md = Path("reports/release_recommendation.md")
    verdict_line = "UNKNOWN"
    recommendation_line = ""
    if release_md.exists():
        for line in release_md.read_text(encoding="utf-8").splitlines():
            if line.startswith("**Verdict:**"):
                verdict_line = line.replace("**Verdict:**", "").strip()
            if line.startswith("## Recommendation") is False and (
                line.startswith("Approve") or line.startswith("Block") or line.startswith("Conditional")
            ):
                recommendation_line = line.strip()

    # ── Header ────────────────────────────────────────────────────────────────
    emit("# Agentic STLC — Power Apps Pipeline Report")
    emit("")
    if run_url:
        emit(f"> **Run:** {run_url}")
    emit("")

    # ── Stage 1: Kane AI Requirement Analysis ─────────────────────────────────
    emit("## Stage 1 · Kane AI Functional Verification")
    emit("")
    if not requirements:
        emit("_No requirements data found in analyzed_requirements.json._")
    else:
        emit(f"| Req ID | Acceptance Criterion | Kane Status | What Kane Observed |")
        emit("|---|---|---|---|")
        for r in requirements:
            kane_status = r.get("kane_status", "unknown")
            icon = status_icon(kane_status)
            one_liner = r.get("kane_one_liner", "") or "—"
            kane_links = r.get("kane_links", [])
            link = f"[session]({kane_links[0]})" if kane_links else "—"
            criterion = r.get("description", "")[:60]
            emit(f"| `{r['id']}` | {criterion} | {icon} {kane_status} | {one_liner} |")
        emit("")

        kane_failed = [r for r in requirements if r.get("kane_status") == "failed"]
        if kane_failed:
            emit(f"**{len(kane_failed)} criterion/criteria failed Kane AI verification:**")
            for r in kane_failed:
                emit(f"- ❌ `{r['id']}` {r.get('title', '')} — {r.get('kane_one_liner', '')}")
            emit("")

    # ── Stage 2: Scenario Management ──────────────────────────────────────────
    emit("## Stage 2 · Scenario Catalog")
    emit("")
    if scenarios:
        new_sc = [s for s in scenarios if s.get("status") == "new"]
        updated_sc = [s for s in scenarios if s.get("status") == "updated"]
        active_sc = [s for s in scenarios if s.get("status") == "active"]
        deprecated_sc = [s for s in scenarios if s.get("status") == "deprecated"]
        emit(
            f"Total: **{len(scenarios)}** — "
            f"{len(active_sc)} active, {len(new_sc)} new, "
            f"{len(updated_sc)} updated, {len(deprecated_sc)} deprecated"
        )
        if new_sc or updated_sc:
            emit("")
            emit("| Scenario | Status | Requirement |")
            emit("|---|---|---|")
            for s in new_sc + updated_sc:
                emit(f"| `{s['id']}` {s.get('title', '')} | {status_icon(s['status'])} {s['status']} | `{s.get('requirement_id', '')}` |")
    emit("")

    # ── Stage 3: Test Generation ───────────────────────────────────────────────
    emit("## Stage 3 · Generated Playwright Tests")
    emit("")
    objectives = load_json("kane/objectives.json", [])
    active_scenarios_set = {s["id"] for s in scenarios if s.get("status") != "deprecated"}
    active_objectives = [o for o in objectives if o.get("scenario_id") in active_scenarios_set]
    if active_objectives:
        emit(f"**{len(active_objectives)}** test function(s) in `tests/playwright/test_powerapps.py`:")
        emit("")
        emit("| Scenario | Test Case | Function |")
        emit("|---|---|---|")
        for o in active_objectives:
            sc = next((s for s in scenarios if s["id"] == o["scenario_id"]), {})
            fn = sc.get("function_name", o.get("objective", ""))
            emit(f"| `{o['scenario_id']}` | `{o.get('test_case_id', '')}` | `{fn}` |")
    else:
        emit("_No test generation data available._")
    emit("")

    # ── Stage 4: Test Selection ────────────────────────────────────────────────
    emit("## Stage 4 · Test Selection")
    emit("")
    selected = manifest.get("selected_scenarios", [])
    run_type = manifest.get("run_type", "unknown")
    emit(f"Run type: **{run_type}** · **{len(selected)}** scenario(s) submitted to HyperExecute")
    emit("")

    # ── Stage 5: HyperExecute Execution (multi-browser) ───────────────────────
    emit("## Stage 5 · HyperExecute Regression (Multi-Browser)")
    emit("")

    he_passed_count = sum(1 for t in he_tasks_api if t.get("status") == "passed")
    he_total_count = len(he_tasks_api) or he_api.get("total_tasks", 0) or len(selected)

    emit("| Metric | Value |")
    emit("|---|---|")
    if he_job_link:
        emit(f"| HyperExecute Job | [Open in LambdaTest ↗]({he_job_link}) |")
    else:
        emit(f"| HyperExecute Job ID | `{he_job_id or 'n/a'}` |")
    emit(f"| Status | {he_status} |")
    emit(f"| Browsers | {', '.join(all_browsers) if all_browsers else 'chrome (default)'} |")
    emit(f"| Total tasks | {he_total_count} |")
    emit(f"| ✅ Passed | {he_passed_count} |")
    emit(f"| ❌ Failed | {he_total_count - he_passed_count} |")
    emit(f"| Pass rate | {pass_rate}% |")
    emit("")

    if he_tasks_api:
        emit("### Per-Test Results")
        emit("")
        emit("| Test | Status | Session |")
        emit("|---|---|---|")
        for task in he_tasks_api:
            icon = "✅" if task.get("status") == "passed" else "❌"
            session = f"[View session]({task['session_link']})" if task.get("session_link") else "—"
            emit(f"| `{task.get('name') or task.get('task_id', 'unknown')}` | {icon} {task.get('status', 'unknown')} | {session} |")
        emit("")

    # ── Multi-browser breakdown from normalized results ────────────────────────
    if normalized and all_browsers:
        emit("### Browser Breakdown")
        emit("")
        emit(f"| Scenario | " + " | ".join(b.capitalize() for b in all_browsers) + " |")
        emit("|---| " + " | ".join("---" for _ in all_browsers) + " |")
        by_sc: dict = {}
        for r in normalized:
            by_sc.setdefault(r["scenario_id"], {})[r["browser"]] = r.get("status", "data_unavailable")
        for sc_id in sorted(by_sc):
            cells = " | ".join(
                f"{status_icon(by_sc[sc_id].get(b, 'data_unavailable'))} {by_sc[sc_id].get(b, '—')}"
                for b in all_browsers
            )
            emit(f"| `{sc_id}` | {cells} |")
        emit("")

    # ── Stage 6: Traceability Matrix ───────────────────────────────────────────
    emit("## Stage 6 · Traceability Matrix")
    emit("")
    emit(
        f"**{passed}/{executed}** regression tests passed across "
        f"**{len(all_browsers) or 1}** browser(s) — {pass_rate}% pass rate"
    )
    emit("")

    if trace_rows:
        browser_header = " | ".join(b.capitalize() for b in all_browsers) if all_browsers else "Browser"
        browser_sep = " | ".join("---" for _ in (all_browsers or ["chrome"]))
        emit(
            f"| Req | Acceptance Criterion | Scenario | Test Case | Kane AI | Kane Session | What Kane Saw | "
            f"{browser_header} | Playwright | Session | Overall |"
        )
        emit(f"|---|---|---|---|---|---|---|{browser_sep}|---|---|---|")

        for row in trace_rows:
            req_id = row.get("requirement_id", "")
            criterion = (row.get("acceptance_criterion", ""))[:55]
            if len(row.get("acceptance_criterion", "")) > 55:
                criterion += "…"
            kane = row.get("kane_ai_result", "unknown")
            kane_link = row.get("kane_session_link", "")
            kane_cell = f"[session]({kane_link})" if kane_link else "—"
            one_liner = row.get("kane_one_liner", "") or "—"
            per_browser = row.get("playwright_per_browser", {})
            browser_cells = " | ".join(
                f"{status_icon(per_browser.get(b, 'data_unavailable'))} {per_browser.get(b, '—')}"
                for b in all_browsers
            ) if all_browsers else "—"
            pw = row.get("playwright_status", "data_unavailable")
            sel_link = row.get("session_link", "")
            sel_cell = f"[session]({sel_link})" if sel_link else "—"
            overall = row.get("overall", "unknown")
            overall_icon = status_icon(overall)
            emit(
                f"| `{req_id}` | {criterion} | `{row.get('scenario_id', 'n/a')}` "
                f"| `{row.get('test_case_id', 'n/a')}` | {kane} | {kane_cell} | {one_liner} "
                f"| {browser_cells} | {pw} | {sel_cell} | {overall_icon} {overall} |"
            )
        emit("")

        # Kane AI detail (collapsible)
        if any(row.get("kane_steps") or row.get("kane_summary") for row in trace_rows):
            emit("<details>")
            emit("<summary>Kane AI verification steps (expand)</summary>")
            emit("")
            for row in trace_rows:
                if not row.get("kane_steps") and not row.get("kane_summary"):
                    continue
                emit(f"**`{row['requirement_id']}` — {row.get('acceptance_criterion', '')}**")
                emit("")
                for step in row.get("kane_steps", []):
                    emit(f"- {step}")
                if row.get("kane_summary"):
                    emit("")
                    emit(f"_{row['kane_summary']}_")
                emit("")
            emit("</details>")
            emit("")

    if result_analysis:
        emit("### Result Analysis")
        emit("")
        emit(f"- **Overall health:** {result_analysis.get('overall_health', 'unknown')}")
        emit(f"- **Risk level:** {result_analysis.get('risk_level', 'unknown')}")
        emit(f"- **Kane AI pass rate:** {result_analysis.get('kane_pass_rate', 0)}%")
        emit(f"- **Playwright pass rate:** {result_analysis.get('playwright_pass_rate', result_analysis.get('selenium_pass_rate', 0))}%")
        emit("")
        for finding in result_analysis.get("key_findings", []):
            emit(f"- {finding}")
        hint = result_analysis.get("recommendation_hint", "")
        if hint:
            emit("")
            emit(f"> {hint}")
        emit("")

    if failing_scenarios:
        emit("**Failing scenarios:**")
        for sc in failing_scenarios:
            emit(f"- ❌ `{sc}`")
        emit("")

    if untested and executed > 0:
        emit("**No execution data for:**")
        for req in untested:
            emit(f"- ⚠️ `{req}` (data_unavailable)")
        emit("")

    # ── Validation Report ──────────────────────────────────────────────────────
    if validation:
        valid = validation.get("valid", True)
        v_errors = validation.get("errors", [])
        v_warnings = validation.get("warnings", [])
        emit("## Data Validation")
        emit("")
        label = "✅ VALID" if valid else "❌ INVALID"
        emit(f"Traceability integrity: **{label}**")
        if v_errors:
            emit("")
            for e in v_errors:
                emit(f"- ❌ {e}")
        if v_warnings:
            emit("")
            for w in v_warnings:
                emit(f"- ⚠️ {w}")
        emit("")

    # ── Release Recommendation ─────────────────────────────────────────────────
    emit("## Release Recommendation")
    emit("")
    icon = verdict_emoji(verdict_line)
    emit(f"### {icon} {verdict_line}")
    emit("")
    if recommendation_line:
        emit(recommendation_line)
    emit("")
    emit(f"- Requirements covered: **{trace_summary.get('requirements_covered', '?')}/{trace_summary.get('requirements_total', '?')}**")
    emit(f"- Browsers tested: **{', '.join(all_browsers) or 'none'}**")
    emit(f"- Playwright pass rate: **{pass_rate}%** ({passed} passed, {executed - passed} failed)")
    if run_url:
        emit(f"- Full run details: {run_url}")
    emit("")


if __name__ == "__main__":
    main()
