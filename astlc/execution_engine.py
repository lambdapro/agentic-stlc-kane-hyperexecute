"""
ProgrammaticExecutionEngine — deterministic pipeline runner.

Owns stages 3–9 of the QA pipeline.  The LLM is NOT in this execution
path at all: every stage is deterministic Python code.

Claude's role after this refactor:
  ┌──────────────────────────────────────────────────────┐
  │  User uploads file                                   │
  │  → ConversationalOrchestrator.ingest()   (LLM: 0)   │
  │    → FileIngestor + RequirementParsingSkill          │
  │    → Returns preview markdown  (Claude summarises)   │
  │                                                      │
  │  User: "proceed"                                     │
  │  → ConversationalOrchestrator.execute()  (LLM: 0)   │
  │    → ProgrammaticExecutionEngine.run()               │
  │      Stage 3  generate_tests      deterministic      │
  │      Stage 3b validate_syntax     deterministic      │
  │      Stage 4b validate_creds      deterministic      │
  │      Stage 4a git_commit          deterministic      │
  │      Stage 4c trigger_ci          deterministic      │
  │      Stage 5  monitor             deterministic      │
  │      Stage 7  collect_artifacts   deterministic      │
  │      Stage 8  coverage            deterministic      │
  │      Stage 9  rca                 deterministic      │
  │    → CompactExecutionResult (~1 K tokens)            │
  │    → ChatReporter.execution_summary()  (LLM: 0)     │
  │      → Claude receives 1-page markdown               │
  └──────────────────────────────────────────────────────┘

Token comparison:
  Before: ~100 K tokens passed through LLM reasoning per run
  After:  <2 K tokens total (preview + final summary)
"""
from __future__ import annotations

import json
import os
import py_compile
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .artifact_cache  import ArtifactCache
from .state_engine    import PipelineStateEngine

UpdateFn = Callable[[str], None]


# ── Compact result object (~1 K tokens vs ~100 K for the old state dict) ─────

@dataclass
class CompactExecutionResult:
    """
    Minimal result returned to the conversational layer.

    Contains counts and summaries only — never full lists.
    The LLM receives ~1 K tokens instead of the full state dict.
    """
    status:  str = "complete"   # complete | error | partial
    verdict: str = ""
    stage:   str = ""           # set on error to indicate where failure occurred
    error:   str = ""

    run_id:  str = ""
    run_url: str = ""

    # Coverage — counts, not lists
    requirements_total:   int   = 0
    requirements_covered: int   = 0
    coverage_pct:         float = 0.0

    # Test execution — counts, not lists
    tests_total:  int   = 0
    tests_passed: int   = 0
    tests_failed: int   = 0
    tests_flaky:  int   = 0

    # HyperExecute
    he_shards:    int   = 0
    he_duration_s: float = 0.0
    he_dashboard: str   = ""
    he_passed:    int   = 0
    he_failed:    int   = 0
    he_flaky:     int   = 0

    # Quality gates — counts + up to 5 gate details
    gates_total:      int  = 0
    gates_passed_n:   int  = 0
    critical_failures: int = 0
    gate_details:     list = field(default_factory=list)   # max 5 items

    # RCA — top 5 failures only
    rca_failure_count: int  = 0
    rca_top_failures:  list = field(default_factory=list)  # max 5

    # Confidence breakdown
    confidence_by_level: dict = field(default_factory=dict)

    # Links
    links: dict = field(default_factory=dict)

    # Agent participation (multi-agent mode only)
    agent_participation: list = field(default_factory=list)

    # State engine compact summary (always < 200 tokens)
    stage_summary: str = ""

    # Rendered markdown for the chat layer
    markdown: str = ""

    def to_chat_dict(self) -> dict:
        """
        Return the minimal dict that ChatReporter.execution_summary() needs.
        Never includes full requirement or scenario lists.
        """
        return {
            "status":  self.status,
            "verdict": self.verdict,
            "coverage": {
                "coverage_pct":       self.coverage_pct,
                "total_requirements": self.requirements_total,
                "covered_full":       self.requirements_covered,
            },
            "confidence": {
                "summary": {"by_confidence_level": self.confidence_by_level},
            },
            "execution": {
                "total":  self.tests_total,
                "passed": self.tests_passed,
                "failed": self.tests_failed,
                "flaky":  self.tests_flaky,
            },
            "hyperexecute": {
                "shards":    self.he_shards,
                "duration_s": self.he_duration_s,
                "dashboard": self.he_dashboard,
                "passed":    self.he_passed,
                "failed":    self.he_failed,
                "flaky":     self.he_flaky,
            },
            "quality_gates": {
                "gates_passed":      self.critical_failures == 0,
                "gates":             self.gate_details,
                "critical_failures": self.critical_failures,
                "warnings":          max(0, self.gates_total - self.gates_passed_n - self.critical_failures),
            },
            "rca": {
                "failures": self.rca_top_failures,
            },
            "links": self.links,
            "agent_participation": self.agent_participation,
        }


# ── Engine ────────────────────────────────────────────────────────────────────

class ProgrammaticExecutionEngine:
    """
    Deterministic pipeline executor.

    All nine execution stages run as pure Python with no LLM involvement.
    The engine emits compact one-line status messages via on_update so the
    chat layer stays informed without receiving large payloads.
    """

    def __init__(
        self,
        config:       Any              = None,
        on_update:    UpdateFn | None  = None,
        state_engine: PipelineStateEngine | None = None,
        cache:        ArtifactCache | None       = None,
    ) -> None:
        self._config  = config
        self._emit    = on_update or (lambda _: None)
        self._state   = state_engine or PipelineStateEngine()
        self._cache   = cache        or ArtifactCache()
        self._reports = Path(
            getattr(config, "reports_dir", None) or "reports"
        )

    # ── Entry point ───────────────────────────────────────────────────────────

    def run(
        self,
        requirements: list[dict],
        scenarios:    list[dict],
        confidence:   dict,
        repo_url:     str,
        branch:       str,
        target_url:   str,
        auto_push:    bool = True,
    ) -> CompactExecutionResult:
        """Execute all pipeline stages; return a compact result."""

        self._state.begin(branch=branch, repo_url=repo_url, target_url=target_url)
        self._cache.clear()

        # Stage 3 — generate tests
        test_file = self._stage_generate_tests(scenarios, target_url)
        if isinstance(test_file, CompactExecutionResult):
            return test_file

        # Stage 3b — syntax validation
        err = self._stage_validate_syntax(test_file)
        if err:
            return self._error_result("validate", err)

        # Stage 4b — credential check (before any git writes)
        cred_report = self._stage_validate_credentials(repo_url, auto_push)
        if isinstance(cred_report, CompactExecutionResult):
            return cred_report

        # Stage 4a — git commit + push
        git_result = self._stage_git_commit(branch, test_file, repo_url, auto_push)

        # Stage 4c — trigger CI
        run_id, run_url = self._stage_trigger_ci(
            repo_url, branch, target_url, auto_push, cred_report
        )
        self._state.update_metrics(run_id=run_id, run_url=run_url)

        # Stage 5 — monitor workflow
        monitor_result = self._stage_monitor(run_id)

        # Stage 7 — collect + parse artifacts (uses ArtifactCache)
        collected = self._stage_collect(run_id, repo_url)

        # Stage 8 — coverage
        coverage = self._stage_coverage(requirements, scenarios)

        # Stage 9 — RCA
        rca = self._stage_rca()

        # Assemble compact result
        result = self._assemble(
            requirements, scenarios, confidence,
            run_id, run_url, monitor_result, collected, coverage, rca
        )
        self._state.complete(verdict=result.verdict)
        result.stage_summary = self._state.compact_summary()
        return result

    # ── Stage 3: Generate Playwright tests ────────────────────────────────────

    def _stage_generate_tests(self, scenarios: list[dict], target_url: str) -> str | CompactExecutionResult:
        self._state.begin_stage("generate_tests")
        self._emit("> Generating Playwright specs...")
        try:
            from skills.playwright_generation import PlaywrightGenerationSkill
            skill  = PlaywrightGenerationSkill(config=self._config, context={})
            result = skill.run(target_url=target_url)
            count  = result.get("tests_generated", 0)
            tf     = result.get("test_file", "tests/playwright/test_powerapps.py")
            self._emit(f"> Generated {count} test function(s).")
            self._state.complete_stage("generate_tests", summary=f"{count} tests", metrics={"count": count})
            self._cache.put(tf, None)   # invalidate; file just written
            return tf
        except Exception as exc:
            self._state.complete_stage("generate_tests", error=str(exc))
            return self._error_result("generate_tests", str(exc))

    # ── Stage 3b: Syntax validation ───────────────────────────────────────────

    def _stage_validate_syntax(self, test_file: str) -> str:
        """Returns empty string on success, error message on failure."""
        self._state.begin_stage("validate_syntax")
        self._emit("> Validating generated tests...")
        try:
            py_compile.compile(test_file, doraise=True)
            self._state.complete_stage("validate_syntax", summary="OK")
            self._emit("> Test syntax validation passed.")
            return ""
        except py_compile.PyCompileError as exc:
            msg = str(exc)
            self._state.complete_stage("validate_syntax", error=msg)
            return msg
        except FileNotFoundError:
            self._state.complete_stage("validate_syntax", summary="no file")
            return ""

    # ── Stage 4b: Credential validation ──────────────────────────────────────

    def _stage_validate_credentials(
        self, repo_url: str, auto_push: bool
    ) -> Any | CompactExecutionResult:
        """Returns cred_report on success, CompactExecutionResult on hard error."""
        if not (auto_push and repo_url):
            parts = []
            if not repo_url:
                parts.append("repository URL")
            if not os.environ.get("GITHUB_TOKEN"):
                parts.append("GITHUB_TOKEN")
            self._emit(
                f"> Skipping CI trigger — missing: {', '.join(parts)}. "
                "Running local validation only."
            )
            self._state.skip_stage("validate_credentials", reason="no repo_url or GITHUB_TOKEN")
            return None

        self._state.begin_stage("validate_credentials")
        self._emit("> Validating pipeline credentials...")
        try:
            from .credential_validator import CredentialValidator
            report = CredentialValidator().validate(repo_url=repo_url)
            if report.errors:
                self._state.complete_stage("validate_credentials", error="; ".join(report.errors))
                r = CompactExecutionResult(status="error", stage="credentials", error=report.errors[0])
                r.markdown = report.onboarding_message()
                return r
            for w in report.warnings:
                self._emit(f"> Credential warning: {w}")
            self._state.complete_stage("validate_credentials", summary="OK")
            return report
        except Exception as exc:
            self._state.complete_stage("validate_credentials", error=str(exc))
            return None    # non-fatal; proceed without guarantee

    # ── Stage 4a: Git commit + push ───────────────────────────────────────────

    def _stage_git_commit(
        self, branch: str, test_file: str, repo_url: str, auto_push: bool
    ) -> dict:
        self._state.begin_stage("git_commit")
        self._emit("> Creating branch and committing generated files...")

        files = [
            test_file,
            str(self._config.scenarios_path if self._config else "scenarios/scenarios.json"),
            str(self._config.requirements_output if self._config else
                "requirements/analyzed_requirements.json"),
        ]

        try:
            from skills.git_operations import GitOperationsSkill
            skill  = GitOperationsSkill(config=self._config, context={})
            result = skill.run(
                branch=branch,
                files=files,
                commit_message="feat: auto-generated tests from agentic-stlc chat-first workflow",
                push=auto_push and bool(os.environ.get("GITHUB_TOKEN")),
            )
            sha    = result.get("sha", "")[:8] if result.get("sha") else ""
            pushed = "pushed" if result.get("pushed") else "local only"
            self._emit(f"> Committed to branch '{branch}'" + (f" (SHA: {sha}), {pushed}." if sha else "."))
            self._state.complete_stage("git_commit", summary=f"sha={sha} {pushed}")
            return result
        except Exception as exc:
            self._state.complete_stage("git_commit", error=str(exc))
            self._emit(f"> Git commit failed: {exc}")
            return {"success": False, "error": str(exc)}

    # ── Stage 4c: Trigger CI ──────────────────────────────────────────────────

    def _stage_trigger_ci(
        self,
        repo_url:    str,
        branch:      str,
        target_url:  str,
        auto_push:   bool,
        cred_report: Any,
    ) -> tuple[str, str]:
        if not (auto_push and repo_url and cred_report):
            self._state.skip_stage("trigger_ci", reason="auto_push disabled or credentials missing")
            return "", ""

        self._state.begin_stage("trigger_ci")
        self._emit("> Triggering GitHub Actions workflow...")
        try:
            from adapters.github import GitHubActionsAdapter
            token = os.environ.get("GITHUB_TOKEN", "")
            gh    = GitHubActionsAdapter(token=token, repo=repo_url)
            run_id = gh.trigger_workflow(
                workflow_id="agentic-stlc.yml",
                ref=branch,
                inputs={"full_run": "false"},
            )
            if run_id:
                status  = gh.get_workflow_status(run_id)
                run_url = status.get("html_url", "")
                self._emit(f"> Workflow triggered (run #{run_id}).")
                self._state.complete_stage("trigger_ci", summary=f"run_id={run_id}")
                return str(run_id), run_url
            self._emit("> Workflow trigger returned no run ID.")
            self._state.complete_stage("trigger_ci", error="no run_id returned")
        except Exception as exc:
            self._emit(f"> Workflow trigger failed: {exc}")
            self._state.complete_stage("trigger_ci", error=str(exc))
        return "", ""

    # ── Stage 5: Monitor ──────────────────────────────────────────────────────

    def _stage_monitor(self, run_id: str) -> dict:
        if not run_id:
            self._state.skip_stage("monitor", reason="no run_id")
            return {}

        self._state.begin_stage("monitor")
        self._emit("> Monitoring pipeline...")
        try:
            from .pipeline_monitor import PipelineMonitor
            token = os.environ.get("GITHUB_TOKEN", "")
            cfg   = self._config
            repo  = (cfg.project.repository if cfg and cfg.project else "") if cfg else ""

            monitor = PipelineMonitor(
                github_token=token,
                repo_slug=repo,
                on_update=self._emit,
            )
            result = monitor.wait_for_completion(run_id=run_id)
            self._state.complete_stage("monitor", summary=result.get("conclusion", ""))
            return result
        except Exception as exc:
            self._state.complete_stage("monitor", error=str(exc))
            return {}

    # ── Stage 7: Collect + parse artifacts ───────────────────────────────────

    def _stage_collect(self, run_id: str, repo_url: str = "") -> dict:
        self._state.begin_stage("collect_artifacts")
        self._emit("> Collecting reports and artifacts...")
        try:
            from .report_collector import ReportCollector
            token = os.environ.get("GITHUB_TOKEN", "")
            # Extract owner/repo slug from URL
            slug  = "/".join(repo_url.rstrip("/").split("/")[-2:]) if repo_url else ""
            coll  = ReportCollector(
                github_token=token,
                repo_slug=slug,
                reports_dir=self._reports,
                on_update=self._emit,
                cache=self._cache,     # share the cache — no double reads
            )
            result = coll.collect(run_id)
            self._state.complete_stage(
                "collect_artifacts",
                summary=f"{result.get('artifacts_downloaded', 0)} artifacts",
            )
            return result
        except Exception as exc:
            self._state.complete_stage("collect_artifacts", error=str(exc))
            return {}

    # ── Stage 8: Coverage analysis ────────────────────────────────────────────

    def _stage_coverage(self, requirements: list[dict], scenarios: list[dict]) -> dict:
        self._state.begin_stage("coverage")
        self._emit("> Running coverage analysis...")
        try:
            from skills.coverage_analysis import CoverageAnalysisSkill
            skill  = CoverageAnalysisSkill(config=self._config, context={})
            result = skill.run()
            pct    = result.get("coverage", {}).get("summary", {}).get("coverage_pct", 0)
            self._state.complete_stage("coverage", summary=f"{pct}%", metrics={"coverage_pct": pct})
            self._state.update_metrics(coverage_pct=pct)
            return result
        except Exception as exc:
            self._state.complete_stage("coverage", error=str(exc))
            return {}

    # ── Stage 9: RCA ──────────────────────────────────────────────────────────

    def _stage_rca(self) -> dict:
        self._state.begin_stage("rca")
        self._emit("> Performing root cause analysis...")
        try:
            from skills.rca import RCASkill
            skill  = RCASkill(config=self._config, context={})
            result = skill.run()
            rca_path = self._reports / "rca_report.json"
            if rca_path.exists():
                rca_data = self._cache.get_json(rca_path)
                if rca_data:
                    result["failures"] = rca_data.get("failures", [])
            n = len(result.get("failures", []))
            self._state.complete_stage("rca", summary=f"{n} failure(s)")
            return result
        except Exception as exc:
            self._state.complete_stage("rca", error=str(exc))
            return {}

    # ── Result assembly ───────────────────────────────────────────────────────

    def _assemble(
        self,
        requirements:   list[dict],
        scenarios:      list[dict],
        confidence:     dict,
        run_id:         str,
        run_url:        str,
        monitor_result: dict,
        collected:      dict,
        coverage:       dict,
        rca:            dict,
    ) -> CompactExecutionResult:
        self._emit("> Generating final summary...")

        # Coverage
        cov_raw   = (
            collected.get("coverage")
            or coverage.get("coverage", {}).get("summary", {})
            or {}
        )
        cov_pct   = float(cov_raw.get("coverage_pct", 0))
        cov_total = int(cov_raw.get("total_requirements", len(requirements)))
        cov_done  = int(cov_raw.get("covered_full", cov_raw.get("fully_covered", 0)))

        verdict = self._compute_verdict(cov_pct)

        # Execution
        ex    = collected.get("execution", {})
        ep    = int(ex.get("passed", 0))
        ef    = int(ex.get("failed", 0))
        efl   = int(ex.get("flaky", 0))
        etot  = int(ex.get("total", ep + ef + efl))

        # HyperExecute
        he     = collected.get("hyperexecute", {})
        he_p   = int(he.get("passed", 0))
        he_f   = int(he.get("failed", 0))
        he_fl  = int(he.get("flaky", 0))
        he_sh  = int(he.get("shards", 0))
        he_dur = float(he.get("duration_s", 0))
        he_db  = he.get("dashboard", "")

        # Quality gates — truncate to 5 for the LLM
        qg_raw        = collected.get("quality_gates", {})
        all_gates     = qg_raw.get("gates", [])
        crit_failures = int(qg_raw.get("critical_failures", 0))
        gates_passed  = int(qg_raw.get("gates_passed", len(all_gates) - crit_failures))

        # RCA — only top 5 failures, stripped to essential fields
        all_failures = rca.get("failures", [])
        top_failures = [
            {
                "scenario_id":   f.get("scenario_id") or f.get("test") or f.get("id", ""),
                "requirement_id": f.get("requirement_id", ""),
                "category":      f.get("category", "UNKNOWN"),
                "message":       (f.get("message", ""))[:120],
                "advice":        f.get("advice") or f.get("suggested_fix", ""),
            }
            for f in all_failures[:5]
        ]

        # Confidence
        conf_by_level = (
            confidence.get("summary", {}).get("by_confidence_level", {})
            if confidence else {}
        )

        # Links
        links: dict[str, str] = {}
        if run_url:
            links["github_actions"] = run_url
        if he_db:
            links["hyperexecute"] = he_db
        report_html = self._reports / "report.html"
        if report_html.exists():
            links["playwright_report"] = str(report_html)
        links.update(collected.get("links", {}))

        return CompactExecutionResult(
            status="complete",
            verdict=verdict,
            run_id=run_id,
            run_url=run_url,
            requirements_total=cov_total,
            requirements_covered=cov_done,
            coverage_pct=cov_pct,
            tests_total=etot,
            tests_passed=ep,
            tests_failed=ef,
            tests_flaky=efl,
            he_shards=he_sh,
            he_duration_s=he_dur,
            he_dashboard=he_db,
            he_passed=he_p,
            he_failed=he_f,
            he_flaky=he_fl,
            gates_total=len(all_gates),
            gates_passed_n=gates_passed,
            critical_failures=crit_failures,
            gate_details=all_gates[:5],
            rca_failure_count=len(all_failures),
            rca_top_failures=top_failures,
            confidence_by_level=conf_by_level,
            links=links,
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _compute_verdict(coverage_pct: float) -> str:
        if coverage_pct >= 90:
            return "GREEN"
        if coverage_pct >= 75:
            return "YELLOW"
        return "RED"

    @staticmethod
    def _error_result(stage: str, error: str) -> CompactExecutionResult:
        return CompactExecutionResult(status="error", stage=stage, error=error)
