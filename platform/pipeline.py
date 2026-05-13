"""
Platform Pipeline Orchestrator.

Framework-agnostic, configuration-driven pipeline engine.
Executes registered stages sequentially; each stage is a callable
that receives (config, context) and returns a result dict.

Stages are discovered from the `pipeline.stages` config key or from
the built-in stage registry populated by skills/__init__.py.

Usage::

    from platform.pipeline import Pipeline
    from platform.config import PlatformConfig

    cfg = PlatformConfig.load()
    result = Pipeline(cfg).run()
"""
from __future__ import annotations

import importlib
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .config import PlatformConfig
from .telemetry import Telemetry


StageCallable = Callable[[PlatformConfig, dict], dict]

_BUILTIN_STAGES: dict[str, str] = {
    "1":   "skills.requirement_parsing:RequirementParsingSkill",
    "2":   "skills.scenario_generation:ScenarioGenerationSkill",
    "2b":  "skills.confidence_analysis:ConfidenceAnalysisSkill",
    "3":   "skills.playwright_generation:PlaywrightGenerationSkill",
    "4":   "skills.artifact_collection:ArtifactCollectionSkill",
    "5":   "skills.hyperexecute_monitoring:HyperExecuteMonitoringSkill",
    "6":   "skills.artifact_collection:ArtifactCollectionSkill",
    "7a":  "skills.coverage_analysis:CoverageAnalysisSkill",
    "7b":  "skills.rca:RCASkill",
    "7c":  "skills.claude_feedback:ClaudeFeedbackSkill",
}


def _load_class(dotted: str) -> Any:
    module_path, class_name = dotted.rsplit(":", 1)
    mod = importlib.import_module(module_path)
    return getattr(mod, class_name)


class StageResult:
    def __init__(self, stage_id: str, name: str, success: bool, data: dict, duration_s: float) -> None:
        self.stage_id = stage_id
        self.name = name
        self.success = success
        self.data = data
        self.duration_s = duration_s


class Pipeline:
    """
    Configuration-driven pipeline executor.

    Stages are executed sequentially. A failed CRITICAL stage halts the
    pipeline; WARNING stages continue. Each stage receives the shared
    context dict (mutable, stages can add keys for downstream stages).
    """

    def __init__(self, config: PlatformConfig) -> None:
        self.config = config
        self.telemetry = Telemetry.get()
        self._results: list[StageResult] = []
        self._context: dict[str, Any] = {
            "config": config,
            "reports_dir": str(config.reports_dir),
            "started_at": datetime.now(timezone.utc).isoformat(),
        }

    # ── Public API ────────────────────────────────────────────────────────────

    def run(self, stage_ids: list[str] | None = None) -> dict:
        """
        Execute pipeline stages.

        Args:
            stage_ids: Optional list of stage IDs to run (subset execution).
                       None = run all configured stages.

        Returns:
            Summary dict with success flag and per-stage results.
        """
        Path(self.config.reports_dir).mkdir(parents=True, exist_ok=True)
        stages = self._resolve_stages(stage_ids)

        self.telemetry.event("pipeline_start", total_stages=len(stages))
        pipeline_start = time.monotonic()

        for stage_id, stage_fn, severity in stages:
            result = self._run_stage(stage_id, stage_fn)
            if not result.success and severity == "CRITICAL":
                self.telemetry.event("pipeline_blocked", stage_id=stage_id)
                break

        elapsed = round(time.monotonic() - pipeline_start, 3)
        summary = self._build_summary(elapsed)
        self.telemetry.event("pipeline_end", **summary)
        return summary

    def add_stage(self, stage_id: str, fn: StageCallable, severity: str = "CRITICAL") -> None:
        """Dynamically add a stage (used by external orchestrators)."""
        self._dynamic_stages = getattr(self, "_dynamic_stages", [])
        self._dynamic_stages.append((stage_id, fn, severity))

    # ── Internal ──────────────────────────────────────────────────────────────

    def _resolve_stages(self, stage_ids: list[str] | None) -> list[tuple[str, StageCallable, str]]:
        """Return ordered list of (id, callable, severity) tuples."""
        cfg_stages = (self.config.pipeline.as_dict().get("stages", [])
                      if self.config.pipeline else [])

        if cfg_stages:
            resolved = []
            for s in cfg_stages:
                sid = str(s.get("id", ""))
                if stage_ids and sid not in stage_ids:
                    continue
                if not s.get("enabled", True):
                    continue
                fn = self._load_stage_fn(sid, s.get("script"))
                resolved.append((sid, fn, s.get("severity", "CRITICAL")))
            return resolved

        # Fall back to built-in stage map
        built_in = list(_BUILTIN_STAGES.items())
        resolved = []
        for sid, dotted in built_in:
            if stage_ids and sid not in stage_ids:
                continue
            try:
                cls = _load_class(dotted)
                inst = cls(config=self.config, context=self._context)
                resolved.append((sid, inst.run, "CRITICAL"))
            except Exception as exc:
                print(f"[pipeline] WARNING: could not load stage {sid} ({exc})")
        return resolved

    def _load_stage_fn(self, stage_id: str, script_path: str | None) -> StageCallable:
        if not script_path:
            dotted = _BUILTIN_STAGES.get(stage_id)
            if dotted:
                cls = _load_class(dotted)
                inst = cls(config=self.config, context=self._context)
                return inst.run
            return lambda cfg, ctx: {"skipped": True}

        p = Path(script_path)
        if p.suffix == ".py":
            spec = importlib.util.spec_from_file_location(f"stage_{stage_id}", p)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if hasattr(mod, "run"):
                return lambda cfg, ctx: mod.run(cfg, ctx)
            if hasattr(mod, "evaluate"):
                return lambda cfg, ctx: mod.evaluate()
        return lambda cfg, ctx: {"skipped": True, "reason": f"unknown script: {script_path}"}

    def _run_stage(self, stage_id: str, fn: StageCallable) -> StageResult:
        self.telemetry.stage_start(stage_id, stage_id)
        start = time.monotonic()
        success = True
        data: dict = {}
        try:
            result = fn(self.config, self._context)
            if isinstance(result, dict):
                data = result
                self._context.update({f"stage_{stage_id}": data})
        except Exception as exc:
            success = False
            data = {"error": str(exc)}
            print(f"[pipeline] Stage {stage_id} failed: {exc}", file=sys.stderr)

        elapsed = round(time.monotonic() - start, 3)
        self.telemetry.stage_end(stage_id, stage_id, success, duration_s=elapsed)
        sr = StageResult(stage_id, stage_id, success, data, elapsed)
        self._results.append(sr)
        return sr

    def _build_summary(self, total_elapsed: float) -> dict:
        passed = [r for r in self._results if r.success]
        failed = [r for r in self._results if not r.success]
        return {
            "success": len(failed) == 0,
            "total_stages": len(self._results),
            "passed_stages": len(passed),
            "failed_stages": len(failed),
            "total_duration_s": total_elapsed,
            "stages": [
                {
                    "id": r.stage_id,
                    "name": r.name,
                    "success": r.success,
                    "duration_s": r.duration_s,
                }
                for r in self._results
            ],
        }
