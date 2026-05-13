"""
ConversationalOrchestrator — chat-first autonomous QA workflow engine.

PRIMARY INTERFACE for the chat-driven experience:

    orch  = ConversationalOrchestrator(config, on_update=print)
    state = orch.ingest("requirements.txt")
    # → returns preview dict with rendered markdown; show to user

    result = orch.execute(state, repo_url="...", branch="main")
    # → runs full pipeline, streams progress via on_update
    # → returns chat-ready markdown summary

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

        # Attach confidence levels back to scenarios for preview
        conf_map = {
            s.get("id"): s
            for s in confidence.get("scenarios", [])
        } if confidence else {}
        for sc in scenarios:
            if sc.get("id") in conf_map:
                sc["confidence_level"]  = conf_map[sc["id"]].get("confidence_level", "MEDIUM")
                sc["confidence_reason"] = conf_map[sc["id"]].get("confidence_reason", "")

        markdown = ChatReporter.preview(requirements, scenarios, confidence)

        return {
            "status":       "preview",
            "requirements": requirements,
            "scenarios":    scenarios,
            "confidence":   confidence,
            "markdown":     markdown,
            "_tmp_req_path": str(tmp_path),
        }

    def execute(
        self,
        state: dict,
        repo_url: str | None = None,
        branch: str | None   = None,
        framework: str | None = None,
        auto_push: bool       = True,
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
        cfg_proj = self.config.project if self.config else None
        repo_url  = repo_url  or (cfg_proj.repository if cfg_proj else "")
        branch    = branch    or f"agentic-stlc/{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}"
        target_url = target_url or (
            self.config.target.url if self.config and self.config.target else ""
        )

        # ── Stage 3: Generate Playwright tests ───────────────────────────────
        self._emit("Generating Playwright specs...")
        test_result = self._generate_tests(scenarios, target_url)
        test_file   = test_result.get("test_file", "tests/playwright/test_powerapps.py")

        # ── Stage 3b: Validate generated test syntax ─────────────────────────
        self._emit("Validating generated tests...")
        valid = self._validate_syntax(test_file)
        if not valid["ok"]:
            return {"status": "error", "stage": "validate", "error": valid["error"]}

        # ── Stage 4a: Git operations ──────────────────────────────────────────
        self._emit("Creating branch and committing generated files...")
        files_to_commit = [
            test_file,
            "scenarios/scenarios.json",
            "kane/objectives.json",
        ]
        git_result = self._git_commit(branch, files_to_commit, repo_url, auto_push)

        # ── Stage 4b: Trigger GitHub Actions ─────────────────────────────────
        run_id  = ""
        run_url = ""
        if repo_url and os.environ.get("GITHUB_TOKEN"):
            self._emit("Triggering GitHub Actions workflow...")
            trigger = self._trigger_workflow(repo_url, branch, target_url)
            run_id  = trigger.get("run_id", "")
            run_url = trigger.get("html_url", "")
            if run_id:
                self._emit(f"Workflow triggered: run #{run_id}")
        else:
            self._emit("Skipping GitHub Actions trigger (no GITHUB_TOKEN or repo_url).")

        # ── Stage 5: Monitor workflow ─────────────────────────────────────────
        monitor_result: dict = {}
        if run_id:
            self._emit("Monitoring GitHub Actions workflow...")
            monitor_result = self._monitor_workflow(run_id, repo_url)

        # ── Stage 6: Collect artifacts ────────────────────────────────────────
        self._emit("Collecting reports and artifacts...")
        self._collect_artifacts(run_id, repo_url)

        # ── Stage 7: Coverage analysis ────────────────────────────────────────
        self._emit("Running coverage analysis...")
        coverage = self._coverage_analysis(requirements, scenarios)

        # ── Stage 8: RCA ──────────────────────────────────────────────────────
        self._emit("Performing root cause analysis...")
        rca = self._run_rca()

        # ── Stage 9: Build verdict ────────────────────────────────────────────
        self._emit("Generating final summary...")
        verdict = self._compute_verdict(coverage)

        # ── Assemble result ───────────────────────────────────────────────────
        result = {
            "status":       "complete",
            "verdict":      verdict,
            "coverage":     coverage.get("summary", {}),
            "confidence":   confidence,
            "execution":    self._parse_junit(),
            "hyperexecute": self._parse_he_summary(),
            "rca":          rca,
            "links": {
                "github_actions":  run_url,
                "hyperexecute":    self._he_dashboard_url(),
                "playwright_report": str(self._reports_dir / "report.html"),
            },
            "git": git_result,
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
        try:
            from skills.scenario_generation import ScenarioGenerationSkill
            skill = ScenarioGenerationSkill(config=self.config, context={})
            res = skill.run(requirements=requirements)
            return res.get("scenarios", [])
        except Exception as exc:
            print(f"[conv] scenario_generation failed: {exc}", file=sys.stderr)
            return []

    def _analyze_confidence(self, scenarios: list[dict]) -> dict:
        try:
            from skills.confidence_analysis import ConfidenceAnalysisSkill
            skill = ConfidenceAnalysisSkill(config=self.config, context={})
            return skill.run(scenarios=scenarios)
        except Exception as exc:
            print(f"[conv] confidence_analysis failed: {exc}", file=sys.stderr)
            return {}

    def _generate_tests(self, scenarios: list[dict], target_url: str) -> dict:
        try:
            from skills.playwright_generation import PlaywrightGenerationSkill
            skill = PlaywrightGenerationSkill(config=self.config, context={})
            return skill.run(scenarios=scenarios, target_url=target_url)
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
            return {"ok": True}  # File not generated → nothing to validate

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
            token = os.environ.get("GITHUB_TOKEN", "")
            gh    = GitHubActionsAdapter(token=token, repo=repo_url)
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

    def _monitor_workflow(self, run_id: str, repo_url: str) -> dict:
        try:
            from skills.workflow_monitor import WorkflowMonitorSkill
            slug = repo_url
            if slug.startswith("https://github.com/"):
                slug = slug.removeprefix("https://github.com/").rstrip("/")
            skill = WorkflowMonitorSkill(config=self.config, context={})
            return skill.run(run_id=run_id, repo=slug, on_update=self.on_update)
        except Exception as exc:
            print(f"[conv] workflow_monitor failed: {exc}", file=sys.stderr)
            return {}

    def _collect_artifacts(self, run_id: str, repo_url: str) -> None:
        if not run_id or not repo_url:
            return
        try:
            from adapters.github import GitHubActionsAdapter
            token = os.environ.get("GITHUB_TOKEN", "")
            gh    = GitHubActionsAdapter(token=token, repo=repo_url)
            gh.download_artifacts(run_id, str(self._reports_dir))
        except Exception as exc:
            print(f"[conv] collect_artifacts failed: {exc}", file=sys.stderr)

    def _coverage_analysis(self, requirements: list[dict], scenarios: list[dict]) -> dict:
        try:
            from skills.coverage_analysis import CoverageAnalysisSkill
            skill = CoverageAnalysisSkill(config=self.config, context={})
            return skill.run(requirements=requirements, scenarios=scenarios)
        except Exception as exc:
            print(f"[conv] coverage_analysis failed: {exc}", file=sys.stderr)
            return {}

    def _run_rca(self) -> dict:
        try:
            from skills.rca import RCASkill
            skill = RCASkill(config=self.config, context={})
            return skill.run()
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
            return {
                "total":  int(ts.get("tests", 0)),
                "failed": int(ts.get("failures", 0)) + int(ts.get("errors", 0)),
                "passed": int(ts.get("tests", 0)) - int(ts.get("failures", 0)) - int(ts.get("errors", 0)),
                "flaky":  0,
            }
        except Exception:
            return {}

    def _parse_he_summary(self) -> dict:
        api = self._reports_dir / "api_details.json"
        if not api.exists():
            return {}
        try:
            data = json.loads(api.read_text(encoding="utf-8"))
            he   = data.get("he_summary", {})
            tasks = data.get("he_tasks", [])
            return {
                "shards":     len(tasks),
                "duration_s": he.get("duration_s", 0),
            }
        except Exception:
            return {}

    def _compute_verdict(self, coverage: dict) -> str:
        pct = coverage.get("summary", {}).get("coverage_pct", 0)
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
