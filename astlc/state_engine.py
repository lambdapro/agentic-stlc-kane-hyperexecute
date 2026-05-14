"""
PipelineStateEngine — persistent, lightweight execution state store.

Stores stage progress, artifact paths, and key metrics in a structured
JSON file at reports/.pipeline_state.json.

The LLM never needs to re-derive what stage is running, what artifacts
exist, or what metrics were produced — it reads a compact (<200-token)
summary from this store instead of reasoning over large file trees.

Design:
  - One JSON file per pipeline run (overwritten on begin())
  - StageRecord tracks timing, status, summary, metrics per stage
  - compact_summary() returns a <200-token string for LLM consumption
  - All writes are atomic (write to tmp, rename)
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

_STATE_FILE = "reports/.pipeline_state.json"


@dataclass
class StageRecord:
    name:         str   = ""
    status:       str   = "pending"   # pending | running | complete | failed | skipped
    started_at:   float = 0.0
    completed_at: float = 0.0
    duration_s:   float = 0.0
    summary:      str   = ""
    metrics:      dict  = field(default_factory=dict)
    error:        str   = ""


@dataclass
class PipelineState:
    run_id:        str   = ""
    branch:        str   = ""
    repo_url:      str   = ""
    target_url:    str   = ""
    started_at:    float = 0.0
    completed_at:  float = 0.0
    current_stage: str   = ""
    verdict:       str   = ""
    stages:        dict  = field(default_factory=dict)   # name -> StageRecord dict
    artifacts:     dict  = field(default_factory=dict)   # label -> path
    metrics:       dict  = field(default_factory=dict)   # key -> value

    def compact_summary(self) -> str:
        """Return a <200-token state summary for LLM injection."""
        stage_recs = [StageRecord(**v) for v in self.stages.values()]
        done   = sum(1 for s in stage_recs if s.status == "complete")
        failed = [s.name for s in stage_recs if s.status == "failed"]
        total  = len(stage_recs)

        lines: list[str] = []
        if self.verdict:
            lines.append(f"Verdict: {self.verdict}")
        lines.append(f"Stage: {self.current_stage or 'idle'} ({done}/{total} complete)")
        if failed:
            lines.append(f"Failed: {', '.join(failed)}")
        for k, v in list(self.metrics.items())[:6]:
            lines.append(f"{k}: {v}")
        if self.run_id:
            lines.append(f"run_id: {self.run_id}")
        return "\n".join(lines)


class PipelineStateEngine:
    """
    Persistent execution state manager.

    Usage::

        state = PipelineStateEngine()
        state.begin(run_id="", branch="product", repo_url=..., target_url=...)

        state.begin_stage("generate_tests")
        # ... work ...
        state.complete_stage("generate_tests", summary="15 tests", metrics={"count": 15})

        state.update_metrics(coverage_pct=72.0, pass_rate=80.0)
        print(state.compact_summary())   # < 200 tokens
    """

    def __init__(self, state_file: str | Path = _STATE_FILE) -> None:
        self._path  = Path(state_file)
        self._state = self._load()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def begin(
        self,
        run_id:     str = "",
        branch:     str = "",
        repo_url:   str = "",
        target_url: str = "",
    ) -> None:
        self._state = PipelineState(
            run_id=run_id,
            branch=branch,
            repo_url=repo_url,
            target_url=target_url,
            started_at=time.time(),
        )
        self._save()

    def complete(self, verdict: str = "") -> None:
        self._state.completed_at = time.time()
        self._state.verdict       = verdict
        self._save()

    # ── Stage tracking ────────────────────────────────────────────────────────

    def begin_stage(self, name: str) -> None:
        self._state.current_stage = name
        self._state.stages[name]  = asdict(StageRecord(
            name=name, status="running", started_at=time.time()
        ))
        self._save()

    def complete_stage(
        self,
        name:    str,
        summary: str  = "",
        metrics: dict | None = None,
        error:   str  = "",
    ) -> None:
        now = time.time()
        rec = self._state.stages.get(name) or asdict(StageRecord(name=name, started_at=now))
        rec["status"]       = "failed" if error else "complete"
        rec["completed_at"] = now
        rec["duration_s"]   = round(now - rec.get("started_at", now), 2)
        rec["summary"]      = summary
        rec["metrics"]      = metrics or {}
        rec["error"]        = error
        self._state.stages[name] = rec
        self._save()

    def skip_stage(self, name: str, reason: str = "") -> None:
        self._state.stages[name] = asdict(StageRecord(
            name=name, status="skipped", summary=reason
        ))
        self._save()

    # ── Artifact & metric tracking ────────────────────────────────────────────

    def record_artifact(self, label: str, path: str) -> None:
        self._state.artifacts[label] = path
        self._save()

    def update_metrics(self, **kv: Any) -> None:
        self._state.metrics.update(kv)
        self._save()

    # ── Read interface ────────────────────────────────────────────────────────

    @property
    def state(self) -> PipelineState:
        return self._state

    def compact_summary(self) -> str:
        return self._state.compact_summary()

    def get_metric(self, key: str, default: Any = None) -> Any:
        return self._state.metrics.get(key, default)

    def artifact_path(self, label: str) -> str:
        return self._state.artifacts.get(label, "")

    # ── Persistence ───────────────────────────────────────────────────────────

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self._state), indent=2), encoding="utf-8")
        tmp.replace(self._path)

    def _load(self) -> PipelineState:
        if not self._path.exists():
            return PipelineState()
        try:
            data   = json.loads(self._path.read_text(encoding="utf-8"))
            stages = data.pop("stages", {})
            state  = PipelineState(**data)
            state.stages = stages          # keep as raw dicts; deserialized on demand
            return state
        except Exception:
            return PipelineState()
