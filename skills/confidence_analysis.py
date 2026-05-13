"""
Skill 9: Confidence Analysis

Wraps the existing ci/scenario_confidence.py engine and exposes it
as a reusable platform skill. Can be called independently of the
pipeline to re-score confidence after adding new scenarios.

Reads:
  - requirements/analyzed_requirements.json
  - scenarios/scenarios.json
  - PLAYWRIGHT_BODIES dict (optional, passed via inputs for body-quality scoring)

Writes:
  - reports/scenario-confidence-report.json
  - reports/requirement-confidence-summary.md
  - reports/high-risk-requirements.json
  - reports/coverage-gap-analysis.json
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
        sys.path.insert(0, "ci")
        reports_dir = Path(self.reports_dir)
        reports_dir.mkdir(parents=True, exist_ok=True)

        req_path = Path(
            inputs.get("requirements_path")
            or (self.config.requirements_output if self.config else "requirements/analyzed_requirements.json")
        )
        sc_path = Path(
            inputs.get("scenarios_path")
            or (self.config.scenarios_path if self.config else "scenarios/scenarios.json")
        )
        playwright_bodies: dict[str, str] = inputs.get("playwright_bodies", {})

        if not req_path.exists() or not sc_path.exists():
            return {"success": False, "error": "requirements or scenarios file not found"}

        requirements = json.loads(req_path.read_text(encoding="utf-8"))
        scenarios    = json.loads(sc_path.read_text(encoding="utf-8"))

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

        signals = report.get("summary", {}).get("quality_signals", {})
        return {
            "success": True,
            "confidence_gate_passed": signals.get("confidence_gate_passed", True),
            "high_criticality_low_confidence": signals.get("high_criticality_low_confidence", []),
            "missing_negative_coverage_count": signals.get("missing_negative_coverage_count", 0),
            "total_requirements": report.get("summary", {}).get("total_requirements", 0),
            "report_path": str(reports_dir / "scenario-confidence-report.json"),
        }
