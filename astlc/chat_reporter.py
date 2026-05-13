"""
ChatReporter — format pipeline results as chat-ready Markdown.

All methods return strings that can be streamed directly to a chat UI,
printed to a terminal, or written to a file.
"""
from __future__ import annotations

from typing import Any


class ChatReporter:
    """Static factory for chat-ready Markdown messages."""

    # ── Pre-execution preview ─────────────────────────────────────────────────

    @staticmethod
    def preview(
        requirements: list[dict],
        scenarios: list[dict],
        confidence: dict,
    ) -> str:
        total_reqs = len(requirements)
        total_sc   = len(scenarios)

        # Confidence summary
        by_level: dict[str, int] = {}
        if confidence:
            by_level = confidence.get("summary", {}).get("by_confidence_level", {})

        lines = [
            "## Requirements Analysis Preview",
            "",
            f"**{total_reqs} requirement(s) detected, {total_sc} test scenario(s) generated.**",
            "",
        ]

        # Feature breakdown
        features: dict[str, int] = {}
        for sc in scenarios:
            f = sc.get("feature", "GENERAL")
            features[f] = features.get(f, 0) + 1
        if features:
            lines.append("### Feature Breakdown")
            for feat, count in sorted(features.items()):
                lines.append(f"- **{feat}**: {count} scenario(s)")
            lines.append("")

        # Confidence breakdown
        if by_level:
            lines.append("### Confidence Analysis")
            icons = {"HIGH": "[HIGH]", "MEDIUM": "[MEDIUM]", "LOW": "[LOW]"}
            for level, count in by_level.items():
                if count:
                    lines.append(f"- {icons.get(level, level)}: {count} scenario(s)")
            lines.append("")

        # Low-confidence warnings
        low_sc = [sc for sc in scenarios if sc.get("confidence_level") == "LOW"]
        if low_sc:
            lines.append("### Warnings - Low Confidence")
            for sc in low_sc[:5]:
                reason = sc.get("confidence_reason", "insufficient detail")
                lines.append(f"- **{sc['id']}**: {sc.get('description', '')[:80]}  ")
                lines.append(f"  _Reason: {reason}_")
            lines.append("")

        lines += [
            "",
            "---",
            "",
            "Reply **proceed** to generate Playwright specs, commit, and trigger the pipeline.",
            "Reply **cancel** to abort.",
        ]
        return "\n".join(lines)

    # ── Streaming status messages ─────────────────────────────────────────────

    @staticmethod
    def update(message: str) -> str:
        return f"> {message}"

    # ── Execution summary ─────────────────────────────────────────────────────

    @staticmethod
    def execution_summary(result: dict) -> str:
        """Full post-pipeline markdown summary."""
        lines = ["# Execution Summary", ""]

        verdict = result.get("verdict", "UNKNOWN")
        verdict_icons = {"GREEN": "[GREEN]", "YELLOW": "[YELLOW]", "RED": "[RED]"}
        lines.append(f"**Verdict: {verdict_icons.get(verdict, verdict)} {verdict}**")
        lines.append("")

        # Coverage
        coverage = result.get("coverage", {})
        if coverage:
            pct = coverage.get("coverage_pct", 0)
            total  = coverage.get("total_requirements", 0)
            # CoverageAnalysisSkill uses "covered_full"; also accept "fully_covered" / "covered"
            covered = coverage.get("covered_full", coverage.get("fully_covered", coverage.get("covered", 0)))
            lines += [
                "## Requirement Coverage",
                "",
                f"- **{pct}%** complete ({covered}/{total} requirements)",
                "",
            ]

        # Confidence
        confidence = result.get("confidence", {})
        by_level   = confidence.get("summary", {}).get("by_confidence_level", {}) if confidence else {}
        if by_level:
            lines.append("## Confidence Analysis")
            lines.append("")
            for level, count in by_level.items():
                if count:
                    lines.append(f"- **{level}**: {count} scenario(s)")
            lines.append("")

        # Execution results
        exec_res = result.get("execution", {})
        if exec_res:
            passed  = exec_res.get("passed", 0)
            failed  = exec_res.get("failed", 0)
            flaky   = exec_res.get("flaky", 0)
            total_t = exec_res.get("total", passed + failed + flaky)
            lines += [
                "## Execution Results",
                "",
                f"- **{passed}** tests passed",
                f"- **{failed}** failed",
            ]
            if flaky:
                lines.append(f"- **{flaky}** flaky")
            lines.append("")

        # HyperExecute
        he = result.get("hyperexecute", {})
        if he:
            shards   = he.get("shards", 0)
            duration = he.get("duration_s", 0)
            he_passed = he.get("passed", 0)
            he_failed = he.get("failed", 0)
            he_flaky  = he.get("flaky", 0)
            he_dash   = he.get("dashboard", "")
            lines += ["## HyperExecute", ""]
            lines.append(f"- **{shards}** parallel shard(s)")
            lines.append(f"- **{round(duration / 60, 1)}m** total execution time")
            if he_passed or he_failed or he_flaky:
                lines.append(f"- Passed: **{he_passed}** | Failed: **{he_failed}** | Flaky: **{he_flaky}**")
            if he_dash:
                lines.append(f"- [HyperExecute Dashboard]({he_dash})")
            lines.append("")

        # Quality gates
        qg = result.get("quality_gates", {})
        if qg:
            gates        = qg.get("gates", [])
            crit_fail    = qg.get("critical_failures", 0)
            warns        = qg.get("warnings", 0)
            gates_passed = qg.get("gates_passed", False)
            icon = "[PASS]" if gates_passed else "[FAIL]"
            lines += ["## Quality Gates", ""]
            lines.append(f"**{icon}** {len(gates) - crit_fail - warns}/{len(gates)} gates passed")
            if crit_fail:
                lines.append(f"- **{crit_fail}** critical failure(s)")
            if warns:
                lines.append(f"- **{warns}** warning(s)")
            for g in gates[:5]:
                g_icon = "[PASS]" if g.get("passed") else "[FAIL]"
                lines.append(f"  {g_icon} {g.get('name', '')}: {g.get('message', '')}")
            lines.append("")

        # GitHub Actions job breakdown
        monitor = result.get("monitor", {})
        gh_jobs = monitor.get("github", {}).get("jobs", [])
        if gh_jobs:
            lines += ["## GitHub Actions Jobs", ""]
            for j in gh_jobs:
                icon = "[PASS]" if j.get("conclusion") == "success" else (
                    "[SKIP]" if j.get("conclusion") == "skipped" else "[FAIL]"
                )
                dur = j.get("duration_s", 0)
                dur_str = f" ({round(dur / 60, 1)}m)" if dur else ""
                lines.append(f"- {icon} **{j['name']}**{dur_str}: {j.get('conclusion', j.get('status', ''))}")
            lines.append("")

        # RCA
        rca = result.get("rca", {})
        failures_by_cat: dict[str, list[dict]] = {}
        for f in rca.get("failures", []):
            cat = f.get("category", "UNKNOWN")
            failures_by_cat.setdefault(cat, []).append(f)

        if failures_by_cat:
            lines += ["## Root Cause Analysis", ""]
            for cat, items in failures_by_cat.items():
                lines.append(f"### {cat} ({len(items)} failure(s))")
                for item in items[:3]:
                    label = item.get("scenario_id") or item.get("requirement_id") or item.get("test") or item.get("id", "")
                    lines.append(f"- **{label}**: {item.get('message', '')[:120]}")
                    # RCASkill uses "advice"; also accept "suggested_fix"
                    fix = item.get("suggested_fix") or item.get("advice", "")
                    if fix:
                        lines.append(f"  _Suggested fix: {fix}_")
            lines.append("")

        # Links
        links = result.get("links", {})
        if links:
            lines.append("## Reports")
            lines.append("")
            if links.get("github_actions"):
                lines.append(f"- [GitHub Actions]({links['github_actions']})")
            if links.get("hyperexecute"):
                lines.append(f"- [HyperExecute Dashboard]({links['hyperexecute']})")
            if links.get("playwright_report"):
                lines.append(f"- [Playwright Report]({links['playwright_report']})")
            lines.append("")

        return "\n".join(lines)

    # ── RCA detail ────────────────────────────────────────────────────────────

    @staticmethod
    def rca_detail(failures: list[dict]) -> str:
        if not failures:
            return "_No failures to report._"

        lines = ["## Failure Analysis", ""]
        for f in failures:
            sc_id    = f.get("scenario_id") or f.get("test") or f.get("id", "")
            req_id   = f.get("requirement_id", "")
            category = f.get("category", "UNKNOWN")
            message  = f.get("message", "")[:200]
            fix      = f.get("suggested_fix") or f.get("advice", "")
            session  = f.get("session_url", "")

            lines.append(f"### {sc_id} — {category}")
            if req_id:
                lines.append(f"**Requirement:** {req_id}")
            lines.append(f"**Error:** {message}")
            if fix:
                lines.append(f"**Suggested fix:** {fix}")
            if session:
                lines.append(f"**Session:** [{session}]({session})")
            lines.append("")

        return "\n".join(lines)

    # ── Confidence detail ─────────────────────────────────────────────────────

    @staticmethod
    def confidence_detail(scenarios: list[dict]) -> str:
        lines = ["## Confidence Analysis", ""]
        groups: dict[str, list[dict]] = {"HIGH": [], "MEDIUM": [], "LOW": []}
        for sc in scenarios:
            lvl = sc.get("confidence_level", "MEDIUM")
            groups.setdefault(lvl, []).append(sc)

        for level in ("HIGH", "MEDIUM", "LOW"):
            items = groups.get(level, [])
            if not items:
                continue
            lines.append(f"### {level} confidence — {len(items)} scenario(s)")
            for sc in items:
                reason = sc.get("confidence_reason", "")
                desc   = sc.get("description", "")[:80]
                entry  = f"- **{sc['id']}**: {desc}"
                if reason:
                    entry += f"  \n  _{reason}_"
                lines.append(entry)
            lines.append("")

        return "\n".join(lines)
