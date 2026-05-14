"""
ConversationalOrchestrator — chat-first autonomous QA workflow engine.

PRIMARY INTERFACE for the chat-driven experience:

    orch  = ConversationalOrchestrator(config, on_update=print)
    state = orch.ingest("requirements.txt")
    # -> returns preview dict with rendered markdown; show to user

    result = orch.execute(state, repo_url="...", branch="main")
    # -> runs full pipeline, streams progress via on_update
    # -> returns chat-ready markdown summary

The on_update callback receives plain-text progress lines so callers
can print them, stream them via SSE, or forward them to a chat UI.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .config import PlatformConfig
from .file_ingestor import FileIngestor
from .chat_reporter import ChatReporter
from .credential_validator import CredentialValidator
from .pipeline_monitor import PipelineMonitor
from .report_collector import ReportCollector


UpdateFn = Callable[[str], None]


class ConversationalOrchestrator:
    """
    Chat-first pipeline driver.

    Responsibilities:
    - Ingest uploaded requirements files in any format
    - Run every pipeline stage with live progress callbacks
    - Auto-commit generated files and push to remote
    - Trigger and monitor GitHub Actions / HyperExecute
    - Return structured results + rendered markdown summary
    """

    def __init__(self, config: PlatformConfig | None = None, on_update: UpdateFn | None = None) -> None:
        self.config    = config or PlatformConfig.load()
        self.on_update = on_update or (lambda msg: None)
        self._reports_dir = Path(self.config.reports_dir if self.config else "reports")

    # ── Public API ────────────────────────────────────────────────────────────

    def ingest(
        self,
        path: str | Path | None = None,
        content: str | bytes | None = None,
        filename: str | None = None,
    ) -> dict:
        """
        Parse a requirements file and return a preview for user confirmation.

        Returns:
          {
            "status": "preview",
            "requirements": [...],
            "scenarios": [...],
            "confidence": {...},
            "markdown": "<preview markdown>",
          }
        """
        self._emit("Analyzing uploaded requirements...")

        try:
            text, fmt = FileIngestor.ingest(path=path, content=content, filename=filename)
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

        # Guard: reject empty or whitespace-only files before writing to disk
        if not text.strip():
            return {
                "status": "error",
                "error": "The uploaded file is empty. Please upload a file containing requirements.",
            }

        # Write normalized text to a temp file so skills can read it
        tmp_path = self._reports_dir / "_ingested_requirements.txt"
        tmp_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path.write_text(text, encoding="utf-8")

        requirements = self._parse_requirements(str(tmp_path), fmt)
        if not requirements:
            return {
                "status": "error",
                "error": "No requirements could be parsed from the uploaded file.",
                "formats_tried": [fmt],
            }

        self._emit(f"Parsed {len(requirements)} requirement(s). Generating scenarios...")
        scenarios = self._generate_scenarios(requirements)

        self._emit("Running confidence analysis...")
        confidence = self._analyze_confidence(scenarios)

        # Attach confidence levels back to scenarios for preview.
        # ConfidenceAnalysisSkill returns "scenarios" with per-scenario confidence data.
        conf_map = {
            s.get("id"): s
            for s in confidence.get("scenarios", [])
            if s.get("id")
        }
        for sc in scenarios:
            sc_id = sc.get("id")
            if sc_id and sc_id in conf_map:
                sc["confidence_level"]  = conf_map[sc_id].get("confidence_level", "MEDIUM")
                sc["confidence_reason"] = conf_map[sc_id].get("confidence_reason", "")

        self._emit(f"Confidence analysis complete. {len(scenarios)} scenarios ready.")
        markdown = ChatReporter.preview(requirements, scenarios, confidence)

        return {
            "status":        "preview",
            "requirements":  requirements,
            "scenarios":     scenarios,
            "confidence":    confidence,
            "markdown":      markdown,
            "_tmp_req_path": str(tmp_path),
        }

    def execute(
        self,
        state: dict,
        repo_url: str | None   = None,
        branch: str | None     = None,
        framework: str | None  = None,
        auto_push: bool        = True,
        target_url: str | None = None,
    ) -> dict:
        """
        Thin delegate: resolves config, hands off to ProgrammaticExecutionEngine,
        renders markdown, returns chat-ready dict.

        The engine owns all 9 execution stages deterministically.
        Claude is not in the execution path — it only sees the final summary.
        """
        if state.get("status") != "preview":
            return {"status": "error", "error": "Call ingest() first to build a preview state."}

        requirements = state["requirements"]
        scenarios    = state["scenarios"]
        confidence   = state.get("confidence", {})

        # Resolve overrides from config
        cfg_proj   = self.config.project if self.config else None
        repo_url   = repo_url   or (cfg_proj.repository if cfg_proj else "")
        branch     = branch     or f"agentic-stlc/{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}"
        target_url = target_url or (
            self.config.target.url if self.config and self.config.target else ""
        )

        # ── Resolve config overrides ──────────────────────────────────────────
        from .execution_engine import ProgrammaticExecutionEngine
        cfg_proj   = self.config.project if self.config else None
        repo_url   = repo_url   or (cfg_proj.repository if cfg_proj else "")
        branch     = branch     or f"agentic-stlc/{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}"
        target_url = target_url or (
            self.config.target.url if self.config and self.config.target else ""
        )

        # ── Delegate all 9 stages to the deterministic engine ─────────────────
        engine = ProgrammaticExecutionEngine(
            config=self.config,
            on_update=self.on_update,
        )
        compact = engine.run(
            requirements=requirements,
            scenarios=scenarios,
            confidence=confidence,
            repo_url=repo_url,
            branch=branch,
            target_url=target_url,
            auto_push=auto_push,
        )

        # ── Error path: surface credential onboarding markdown ────────────────
        if compact.status == "error":
            return {
                "status":   "error",
                "stage":    compact.stage,
                "error":    compact.error,
                "markdown": compact.markdown or compact.error,
            }

        # ── Render final summary — only thing Claude sees ─────────────────────
        self._emit("Done.")
        chat_dict = compact.to_chat_dict()
        chat_dict["markdown"] = ChatReporter.execution_summary(chat_dict)
        return chat_dict

    # ── Stage helpers ─────────────────────────────────────────────────────────

    def _parse_requirements(self, path: str, fmt: str) -> list[dict]:
        try:
            from skills.requirement_parsing import RequirementParsingSkill
            skill = RequirementParsingSkill(config=self.config, context={})
            res = skill.run(paths=[path], format=fmt)
            return res.get("requirements", [])
        except Exception as exc:
            print(f"[conv] requirement_parsing failed: {exc}", file=sys.stderr)
            return []

    def _generate_scenarios(self, requirements: list[dict]) -> list[dict]:
        """Generate/sync scenarios then return the active list from disk."""
        try:
            from skills.scenario_generation import ScenarioGenerationSkill
            skill = ScenarioGenerationSkill(config=self.config, context={})
            res = skill.run()  # reads analyzed_requirements.json, writes scenarios.json
            if res.get("success"):
                # ScenarioGenerationSkill writes to disk; read back active scenarios.
                sc_path = Path(
                    res.get("scenarios_path")
                    or (self.config.scenarios_path if self.config else "scenarios/scenarios.json")
                )
                if sc_path.exists():
                    all_scenarios = json.loads(sc_path.read_text(encoding="utf-8"))
                    return [s for s in all_scenarios if s.get("status") != "deprecated"]
        except Exception as exc:
            print(f"[conv] scenario_generation failed: {exc}", file=sys.stderr)
        return []

    def _analyze_confidence(self, scenarios: list[dict]) -> dict:
        """Run confidence analysis; returns dict with 'scenarios' key for conf_map building."""
        try:
            from skills.confidence_analysis import ConfidenceAnalysisSkill
            skill = ConfidenceAnalysisSkill(config=self.config, context={})
            return skill.run()  # reads from disk; returns {"scenarios": [...], "summary": {...}, ...}
        except Exception as exc:
            print(f"[conv] confidence_analysis failed: {exc}", file=sys.stderr)
            return {}

    def _generate_tests(self, scenarios: list[dict], target_url: str) -> dict:
        try:
            from skills.playwright_generation import PlaywrightGenerationSkill
            skill = PlaywrightGenerationSkill(config=self.config, context={})
            return skill.run(target_url=target_url)  # reads scenarios.json from disk
        except Exception as exc:
            print(f"[conv] playwright_generation failed: {exc}", file=sys.stderr)
            return {"success": False, "error": str(exc)}

    def _validate_syntax(self, test_file: str) -> dict:
        """Syntax-check generated Python with py_compile."""
        import py_compile
        try:
            py_compile.compile(test_file, doraise=True)
            return {"ok": True}
        except py_compile.PyCompileError as exc:
            return {"ok": False, "error": str(exc)}
        except FileNotFoundError:
            return {"ok": True}  # File not generated -> nothing to validate

    def _git_commit(self, branch: str, files: list[str], repo_url: str, push: bool) -> dict:
        try:
            from skills.git_operations import GitOperationsSkill
            skill = GitOperationsSkill(config=self.config, context={})
            return skill.run(
                branch=branch,
                files=files,
                commit_message="feat: auto-generated tests from agentic-stlc chat-first workflow",
                push=push and bool(os.environ.get("GITHUB_TOKEN")),
            )
        except Exception as exc:
            print(f"[conv] git_operations failed: {exc}", file=sys.stderr)
            return {"success": False, "error": str(exc)}

    def _trigger_workflow(self, repo_url: str, branch: str, target_url: str) -> dict:
        try:
            from adapters.github import GitHubActionsAdapter
            token  = os.environ.get("GITHUB_TOKEN", "")
            gh     = GitHubActionsAdapter(token=token, repo=repo_url)
            run_id = gh.trigger_workflow(
                workflow_id="agentic-stlc.yml",
                ref=branch,
                inputs={"full_run": "false"},
            )
            if run_id:
                status = gh.get_workflow_status(run_id)
                return {"run_id": run_id, "html_url": status.get("html_url", "")}
        except Exception as exc:
            print(f"[conv] trigger_workflow failed: {exc}", file=sys.stderr)
        return {}

    def _coverage_analysis(self, requirements: list[dict], scenarios: list[dict]) -> dict:
        """Returns CoverageAnalysisSkill result: {"coverage": {"summary": {...}}, ...}"""
        try:
            from skills.coverage_analysis import CoverageAnalysisSkill
            skill = CoverageAnalysisSkill(config=self.config, context={})
            return skill.run()
        except Exception as exc:
            print(f"[conv] coverage_analysis failed: {exc}", file=sys.stderr)
            return {}

    def _run_rca(self) -> dict:
        """Run RCA and return result including the failures list from the written report."""
        try:
            from skills.rca import RCASkill
            skill   = RCASkill(config=self.config, context={})
            result  = skill.run()
            # RCASkill writes rca_report.json; read it back to expose failures to ChatReporter.
            rca_path = self._reports_dir / "rca_report.json"
            if rca_path.exists():
                report_data = json.loads(rca_path.read_text(encoding="utf-8"))
                result["failures"] = report_data.get("failures", [])
            return result
        except Exception as exc:
            print(f"[conv] rca failed: {exc}", file=sys.stderr)
            return {}

    def _parse_junit(self) -> dict:
        junit = self._reports_dir / "junit.xml"
        if not junit.exists():
            return {}
        try:
            import xml.etree.ElementTree as ET
            tree = ET.parse(str(junit))
            root = tree.getroot()
            ts   = root if root.tag == "testsuite" else root.find("testsuite")
            if ts is None:
                return {}
            total  = int(ts.get("tests", 0))
            failed = int(ts.get("failures", 0)) + int(ts.get("errors", 0))
            return {
                "total":  total,
                "failed": failed,
                "passed": total - failed,
                "flaky":  0,
            }
        except Exception:
            return {}

    def _parse_he_summary(self) -> dict:
        api = self._reports_dir / "api_details.json"
        if not api.exists():
            return {}
        try:
            data  = json.loads(api.read_text(encoding="utf-8"))
            he    = data.get("he_summary", {})
            tasks = data.get("he_tasks", [])
            return {
                "shards":     len(tasks),
                "duration_s": he.get("duration_s", 0),
            }
        except Exception:
            return {}

    def _compute_verdict(self, coverage_result: dict) -> str:
        # CoverageAnalysisSkill result shape: {"coverage": {"summary": {"coverage_pct": N}}, ...}
        pct = coverage_result.get("coverage", {}).get("summary", {}).get("coverage_pct", 0)
        if pct >= 90:
            return "GREEN"
        if pct >= 75:
            return "YELLOW"
        return "RED"

    def _he_dashboard_url(self) -> str:
        api = self._reports_dir / "api_details.json"
        if not api.exists():
            return ""
        try:
            data   = json.loads(api.read_text(encoding="utf-8"))
            job_id = data.get("job_id", "")
            if job_id:
                return f"https://hyperexecute.lambdatest.com/task-queue/{job_id}"
        except Exception:
            pass
        return ""

    # ── Utility ───────────────────────────────────────────────────────────────

    def _emit(self, msg: str) -> None:
        self.on_update(ChatReporter.update(msg))
