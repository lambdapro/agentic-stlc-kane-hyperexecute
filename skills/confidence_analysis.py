"""
Skill 9: Confidence Analysis

Scores each scenario's test coverage sufficiency and produces a structured
confidence report. Wraps ci/scenario_confidence.py as a reusable skill.

Reads:
  - requirements/analyzed_requirements.json
  - scenarios/scenarios.json

Writes:
  - reports/scenario-confidence-report.json
  - reports/requirement-confidence-summary.md
  - reports/high-risk-requirements.json
  - reports/coverage-gap-analysis.json

Returns:
  success, confidence_gate_passed, scenarios (per-scenario confidence data),
  summary (by_confidence_level breakdown), and report paths.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .base import AgentSkill


class ConfidenceAnalysisSkill(AgentSkill):
    name = "confidence_analysis"
    description = "Score scenario sufficiency and produce coverage-gap analysis"
    version = "1.0.0"

    def run(self, **inputs: Any) -> dict:
        """
        Run confidence analysis.

        Accepts optional in-memory ``requirements`` and ``scenarios`` lists so
        callers that already have the data avoid a redundant disk read.  Falls
        back to disk paths when the lists are not supplied.
        """
        sys.path.insert(0, "ci")
        reports_dir = Path(self.reports_dir)
        reports_dir.mkdir(parents=True, exist_ok=True)

        playwright_bodies: dict[str, str] = inputs.get("playwright_bodies", {})

        # Prefer in-memory data; only read disk when not provided.
        requirements: list[dict] | None = inputs.get("requirements")
        scenarios:    list[dict] | None = inputs.get("scenarios")

        if requirements is None or scenarios is None:
            req_path = Path(
                inputs.get("requirements_path")
                or (self.config.requirements_output if self.config else
                    "requirements/analyzed_requirements.json")
            )
            sc_path = Path(
                inputs.get("scenarios_path")
                or (self.config.scenarios_path if self.config else "scenarios/scenarios.json")
            )
            if not req_path.exists() or not sc_path.exists():
                return {"success": False, "error": "requirements or scenarios file not found"}
            if requirements is None:
                requirements = json.loads(req_path.read_text(encoding="utf-8"))
            if scenarios is None:
                scenarios = json.loads(sc_path.read_text(encoding="utf-8"))

        try:
            from scenario_confidence import run_confidence_analysis
            report = run_confidence_analysis(
                requirements=requirements,
                scenarios=scenarios,
                playwright_bodies=playwright_bodies,
                output_dir=str(reports_dir),
            )
        except Exception as exc:
            return {"success": False, "error": str(exc)}

        summary = report.get("summary", {})
        records = report.get("records", [])
        signals = summary.get("quality_signals", {})

        # Build a "scenarios" list so ConversationalOrchestrator can attach
        # confidence levels to scenario dicts during the ingest() preview.
        scenario_confidence: list[dict] = [
            {
                "id":               r.get("scenario_id", ""),
                "requirement_id":   r.get("requirement_id", ""),
                "confidence_level": r.get("confidence_level", "MEDIUM"),
                "confidence_reason": r.get("confidence_reason", ""),
                "coverage_gaps":    r.get("coverage_gaps", []),
                "recommendations":  r.get("recommendations", []),
            }
            for r in records
        ]

        return {
            "success":  True,
            "scenarios": scenario_confidence,
            "summary":  summary,
            "confidence_gate_passed":              signals.get("confidence_gate_passed", True),
            "high_criticality_low_confidence":     signals.get("high_criticality_low_confidence", []),
            "missing_negative_coverage_count":     signals.get("missing_negative_coverage_count", 0),
            "total_requirements":                  summary.get("total_requirements", 0),
            "report_path":                         str(reports_dir / "scenario-confidence-report.json"),
        }
