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
        Run the full pipeline from an ingest() state dict.

        Stages:
          1. Generate Playwright tests
          2. Validate syntax
          3. Git: create branch, commit, push
          4. Trigger GitHub Actions
          5. Monitor workflow
          6. Collect artifacts
          7. Coverage analysis
          8. RCA
          9. Format chat summary
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

        # ── Stage 3: Generate Playwright tests ───────────────────────────────
        self._emit("Generating Playwright specs...")
        test_result = self._generate_tests(scenarios, target_url)
        test_file   = test_result.get("test_file", "tests/playwright/test_powerapps.py")
        self._emit(f"Generated {test_result.get('tests_generated', 0)} test function(s).")

        # ── Stage 3b: Validate generated test syntax ─────────────────────────
        self._emit("Validating generated tests...")
        valid = self._validate_syntax(test_file)
        if not valid["ok"]:
            return {"status": "error", "stage": "validate", "error": valid["error"]}
        self._emit("Test syntax validation passed.")

        # ── Stage 4a: Git operations ──────────────────────────────────────────
        self._emit("Creating branch and committing generated files...")
        files_to_commit = [
            test_file,
            "scenarios/scenarios.json",
            "kane/objectives.json",
        ]
        git_result = self._git_commit(branch, files_to_commit, repo_url, auto_push)
        if git_result.get("success"):
            self._emit(f"Committed to branch '{branch}' (SHA: {git_result.get('commit_sha', '')[:8]}).")
        else:
            self._emit(f"Git commit skipped: {git_result.get('error', 'unknown')}")

        # ── Stage 4b: Credential validation + GitHub Actions trigger ─────────
        run_id  = ""
        run_url = ""
        he_job_id = ""
        cred_report = None

        if auto_push and repo_url:
            self._emit("Validating pipeline credentials...")
            validator   = CredentialValidator()
            cred_report = validator.validate(repo_url=repo_url)

            if cred_report.errors:
                # Hard stop — surface actionable onboarding message
                onboard_md = cred_report.onboarding_message()
                return {
                    "status":   "error",
                    "stage":    "credentials",
                    "error":    "Missing or invalid credentials. See markdown for setup instructions.",
                    "markdown": onboard_md,
                }

            if cred_report.warnings:
                for w in cred_report.warnings:
                    self._emit(f"Credential warning: {w}")

            self._emit("Triggering GitHub Actions workflow...")
            trigger = self._trigger_workflow(repo_url, branch, target_url)
            run_id  = trigger.get("run_id", "")
            run_url = trigger.get("html_url", "")
            if run_id:
                self._emit(f"Workflow triggered: run #{run_id}  {run_url}")
            else:
                self._emit("Workflow trigger failed or returned no run ID.")
        else:
            missing = []
            if not repo_url:
                missing.append("repository URL (--repo)")
            if not os.environ.get("GITHUB_TOKEN"):
                missing.append("GITHUB_TOKEN")
            self._emit(
                f"Skipping CI pipeline trigger — missing: {', '.join(missing)}. "
                "Running local validation only."
            )

        # ── Stage 5: Monitor workflow + HyperExecute concurrently ────────────
        monitor_result: dict = {}
        if run_id:
            self._emit("Monitoring GitHub Actions workflow and HyperExecute in real time...")
            repo_slug = repo_url
            if repo_slug.startswith("https://github.com/"):
                repo_slug = repo_slug.removeprefix("https://github.com/").rstrip("/")
            pm = PipelineMonitor(
                repo_slug=repo_slug,
                on_update=self.on_update,
            )
            monitor_result = pm.run(run_id=run_id, he_job_id=he_job_id)
            he_info = monitor_result.get("hyperexecute", {})
            if he_info:
                self._emit(
                    f"HyperExecute: {he_info.get('shards', 0)} shards | "
                    f"Passed: {he_info.get('passed', 0)}, "
                    f"Failed: {he_info.get('failed', 0)}, "
                    f"Flaky: {he_info.get('flaky', 0)}"
                )

        # ── Stage 6: Collect and parse artifacts ──────────────────────────────
        self._emit("Collecting reports and artifacts...")
        repo_slug_for_collect = ""
        if repo_url and repo_url.startswith("https://github.com/"):
            repo_slug_for_collect = repo_url.removeprefix("https://github.com/").rstrip("/")
        collector = ReportCollector(
            repo_slug=repo_slug_for_collect,
            reports_dir=self._reports_dir,
            on_update=self.on_update,
        )
        collected = collector.collect(run_id=run_id)

        # ── Stage 7: Coverage analysis ────────────────────────────────────────
        self._emit("Running coverage analysis...")
        coverage_result = self._coverage_analysis(requirements, scenarios)
        # Merge collected coverage if local CoverageSkill has no data
        coverage_summary = coverage_result.get("coverage", {}).get("summary", {})
        if not coverage_summary and collected.get("coverage"):
            coverage_summary = collected["coverage"]

        # ── Stage 8: RCA ──────────────────────────────────────────────────────
        self._emit("Performing root cause analysis...")
        rca = self._run_rca()
        # Merge downloaded RCA failures if local skill produced none
        if not rca.get("failures") and collected.get("rca", {}).get("failures"):
            rca["failures"] = collected["rca"]["failures"]

        # ── Stage 9: Build verdict ────────────────────────────────────────────
        self._emit("Generating final summary...")
        verdict = self._compute_verdict(coverage_result)

        # Build HyperExecute summary from monitor or collected data
        he_monitor = monitor_result.get("hyperexecute", {})
        he_summary = {
            "shards":     he_monitor.get("shards", 0) or self._parse_he_summary().get("shards", 0),
            "duration_s": he_monitor.get("duration_s", 0) or self._parse_he_summary().get("duration_s", 0),
            "passed":     he_monitor.get("passed", 0),
            "failed":     he_monitor.get("failed", 0),
            "flaky":      he_monitor.get("flaky", 0),
            "dashboard":  he_monitor.get("dashboard", self._he_dashboard_url()),
        }

        # Execution: prefer collected (from CI artifact) over local junit
        execution = collected.get("execution") or self._parse_junit()

        # ── Assemble result ───────────────────────────────────────────────────
        result = {
            "status":       "complete",
            "verdict":      verdict,
            "coverage":     coverage_summary,
            "confidence":   collected.get("confidence", confidence),
            "execution":    execution,
            "hyperexecute": he_summary,
            "quality_gates": collected.get("quality_gates", {}),
            "rca":          rca,
            "links": {
                "github_actions":    run_url,
                "hyperexecute":      he_summary.get("dashboard", ""),
                "playwright_report": str(self._reports_dir / "report.html"),
            },
            "git":     git_result,
            "monitor": monitor_result,
        }

        markdown = ChatReporter.execution_summary(result)
        result["markdown"] = markdown

        self._emit("Done.")
        return result

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
