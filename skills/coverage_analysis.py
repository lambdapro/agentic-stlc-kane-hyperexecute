"""
Skill 8: Requirement Coverage Analysis

Maps test execution results back to requirements, computes coverage
percentages, identifies uncovered requirements, and writes:
  - reports/coverage_report.json
  - reports/traceability_matrix.json (delegated to build_traceability)
  - reports/release_recommendation.json

This skill wraps the existing ci/build_traceability.py + ci/release_recommendation.py
while exposing a clean, config-driven interface for external callers.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .base import AgentSkill


class CoverageAnalysisSkill(AgentSkill):
    name = "coverage_analysis"
    description = "Map execution results to requirements and compute coverage metrics"
    version = "1.0.0"

    def run(self, **inputs: Any) -> dict:
        sys.path.insert(0, "ci")
        reports_dir = Path(self.reports_dir)
        reports_dir.mkdir(parents=True, exist_ok=True)

        results: dict[str, Any] = {}

        # Traceability
        try:
            import build_traceability
            matrix = build_traceability.build()
            results["traceability"] = {
                "success": True,
                "requirements": matrix.get("summary", {}).get("total_requirements", 0),
                "covered":      matrix.get("summary", {}).get("fully_covered", 0),
            }
        except Exception as exc:
            results["traceability"] = {"success": False, "error": str(exc)}

        # Release recommendation
        try:
            import release_recommendation
            verdict = release_recommendation.recommend()
            results["verdict"] = {
                "success": True,
                "status": verdict.get("verdict", "UNKNOWN"),
                "pass_rate": verdict.get("pass_rate", 0),
            }
        except Exception as exc:
            results["verdict"] = {"success": False, "error": str(exc)}

        # Coverage report
        coverage_report = self._build_coverage_report(reports_dir)
        results["coverage"] = coverage_report

        return {"success": True, **results}

    def _build_coverage_report(self, reports_dir: Path) -> dict:
        """Build coverage_report.json from traceability matrix."""
        matrix_path = reports_dir / "traceability_matrix.json"
        if not matrix_path.exists():
            return {"error": "traceability_matrix.json not found"}

        matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
        requirements = matrix.get("requirements", [])
        total = len(requirements)
        covered = sum(1 for r in requirements if r.get("coverage_status") != "NONE")
        coverage_pct = round((covered / total * 100) if total else 0, 1)

        report = {
            "summary": {
                "total_requirements": total,
                "covered_full": covered,
                "coverage_pct": coverage_pct,
                "he_coverage_pct": self._he_coverage_pct(requirements),
            },
            "requirements": [
                {
                    "requirement_id": r.get("requirement_id", r.get("id", "")),
                    "criticality": r.get("criticality", "MEDIUM"),
                    "coverage_status": r.get("coverage_status", "NONE"),
                    "risk_level": r.get("risk_level", "LOW"),
                    "execution_status": r.get("execution_status", {}),
                }
                for r in requirements
            ],
        }

        out_path = reports_dir / "coverage_report.json"
        out_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        return report

    def _he_coverage_pct(self, requirements: list[dict]) -> float:
        total = len(requirements)
        if not total:
            return 0.0
        he_covered = sum(
            1 for r in requirements
            if r.get("execution_status", {}).get("he_session_url")
        )
        return round(he_covered / total * 100, 1)
