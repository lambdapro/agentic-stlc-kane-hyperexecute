"""
Skill 11: Claude Feedback Context

Assembles a structured debugging context package from all pipeline
artifacts and formats it for consumption by Claude (or any AI agent).

The feedback context includes:
  - Failed test names + error messages
  - Kane AI failure details + session links
  - Playwright body for each failing scenario
  - Confidence gaps from scenario-confidence-report.json
  - RCA categories and advice
  - Suggested next prompts for the engineer

This closes the human-in-the-loop: instead of an engineer manually
digging through logs, they paste the context report into Claude Code
and get targeted fix suggestions instantly.

Output:
  - reports/claude_feedback_context.md
  - reports/claude_feedback_context.json
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .base import AgentSkill


class ClaudeFeedbackSkill(AgentSkill):
    name = "claude_feedback"
    description = "Assemble structured AI debugging context from all pipeline artifacts"
    version = "1.0.0"

    def run(self, **inputs: Any) -> dict:
        reports_dir = Path(self.reports_dir)
        reports_dir.mkdir(parents=True, exist_ok=True)

        context = self._build_context(reports_dir)
        md_path  = reports_dir / "claude_feedback_context.md"
        json_path = reports_dir / "claude_feedback_context.json"

        md_path.write_text(self._render_markdown(context), encoding="utf-8")
        json_path.write_text(json.dumps(context, indent=2) + "\n", encoding="utf-8")

        return {
            "success": True,
            "context_path": str(md_path),
            "json_path":    str(json_path),
            "failure_count": context["summary"]["total_failures"],
            "suggested_prompts": len(context.get("suggested_prompts", [])),
        }

    # ── Context assembly ──────────────────────────────────────────────────────

    def _build_context(self, reports_dir: Path) -> dict:
        verdict      = self._load_json(reports_dir / "release_recommendation.json", {})
        rca          = self._load_json(reports_dir / "rca_report.json", {})
        confidence   = self._load_json(reports_dir / "scenario-confidence-report.json", {})
        traceability = self._load_json(reports_dir / "traceability_matrix.json", {})

        failures = rca.get("failures", [])
        low_conf = (
            confidence.get("summary", {})
                      .get("quality_signals", {})
                      .get("high_criticality_low_confidence", [])
        )
        gaps = [
            r for r in confidence.get("records", [])
            if r.get("confidence_level") in ("LOW", "CRITICAL_GAP")
        ]

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "project": {
                "name": self.config.project.name if self.config else "unknown",
                "repository": self.config.project.repository if self.config else "",
                "branch": self.config.project.branch if self.config else "",
            },
            "summary": {
                "verdict": verdict.get("verdict", "UNKNOWN"),
                "pass_rate": verdict.get("pass_rate", 0),
                "total_failures": len(failures),
                "low_confidence_requirements": len(low_conf),
                "coverage_gaps": len(gaps),
            },
            "failures": [
                {
                    "source":      f.get("source", ""),
                    "test":        f.get("test") or f.get("requirement_id", ""),
                    "category":    f.get("category", "UNKNOWN"),
                    "message":     f.get("message", "")[:400],
                    "advice":      f.get("advice", ""),
                    "session_url": f.get("session_url", ""),
                }
                for f in failures
            ],
            "low_confidence_requirements": low_conf,
            "coverage_gaps": [
                {
                    "requirement_id": r.get("requirement_id", ""),
                    "feature":        r.get("feature", ""),
                    "confidence":     r.get("confidence_level", ""),
                    "gaps":           r.get("coverage_gaps", [])[:3],
                    "recommendations": r.get("recommendations", [])[:2],
                }
                for r in gaps
            ],
            "suggested_prompts": self._generate_prompts(failures, gaps),
        }

    def _generate_prompts(self, failures: list[dict], gaps: list[dict]) -> list[str]:
        prompts = []
        categories = {f.get("category") for f in failures}

        if "TIMEOUT" in categories:
            prompts.append(
                "Several tests failed with TimeoutError. Review the Playwright selectors "
                "and add explicit `page.wait_for_selector()` calls before interactions. "
                "Check if the target site added new loading animations or lazy-loaded sections."
            )
        if "SELECTOR" in categories:
            prompts.append(
                "Selector failures detected. Run `playwright codegen <url>` to re-record "
                "up-to-date selectors. Check if the application renamed CSS classes or IDs."
            )
        if "AUTH" in categories:
            prompts.append(
                "Authentication failures detected in Kane AI sessions. "
                "Verify LT_USERNAME / LT_ACCESS_KEY secrets and Kane project/folder IDs in config."
            )
        if "NETWORK" in categories:
            prompts.append(
                "Network errors suggest the target URL is unreachable from the CI environment. "
                "Confirm TARGET_URL is correct and the environment has outbound internet access."
            )

        if gaps:
            prompts.append(
                f"{len(gaps)} requirement(s) have LOW/CRITICAL_GAP confidence. "
                "Add negative test scenarios (invalid inputs, empty states, boundary values) "
                "to the PLAYWRIGHT_BODIES dict in ci/agent.py for these requirements: "
                + ", ".join(g.get("requirement_id", "") for g in gaps[:5])
            )

        return prompts

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _render_markdown(self, ctx: dict) -> str:
        s = ctx["summary"]
        lines = [
            "# Claude Debugging Context — Agentic STLC Pipeline",
            "",
            f"**Project:** {ctx['project']['name']}  ",
            f"**Repository:** {ctx['project']['repository']}  ",
            f"**Branch:** {ctx['project']['branch']}  ",
            f"**Generated:** {ctx['generated_at']}",
            "",
            "## Pipeline Summary",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Verdict | **{s['verdict']}** |",
            f"| Pass Rate | {s['pass_rate']}% |",
            f"| Total Failures | {s['total_failures']} |",
            f"| Low-Confidence Requirements | {s['low_confidence_requirements']} |",
            f"| Coverage Gaps | {s['coverage_gaps']} |",
            "",
        ]

        if ctx["failures"]:
            lines += ["## Test Failures", ""]
            for f in ctx["failures"]:
                lines += [
                    f"### [{f['category']}] `{f['test']}`",
                    f"**Source:** {f['source']}  ",
                    f"**Advice:** {f['advice']}  ",
                    f"**Message:** `{f['message'][:300]}`  ",
                ]
                if f.get("session_url"):
                    lines.append(f"**Session recording:** [{f['session_url']}]({f['session_url']})  ")
                lines.append("")

        if ctx["coverage_gaps"]:
            lines += ["## Coverage Gaps (LOW/CRITICAL_GAP Confidence)", ""]
            for g in ctx["coverage_gaps"]:
                lines += [
                    f"### `{g['requirement_id']}` — {g['feature']} ({g['confidence']})",
                    "**Missing coverage:**",
                ]
                for gap in g["gaps"]:
                    lines.append(f"  - {gap}")
                lines += ["**Recommended actions:**"]
                for rec in g["recommendations"]:
                    lines.append(f"  - {rec}")
                lines.append("")

        if ctx["suggested_prompts"]:
            lines += ["## Suggested Next Actions for Claude", ""]
            for i, prompt in enumerate(ctx["suggested_prompts"], 1):
                lines.append(f"**{i}.** {prompt}")
                lines.append("")

        return "\n".join(lines) + "\n"

    def _load_json(self, path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default
