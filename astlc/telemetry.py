"""
Platform telemetry and structured logging.

Provides a singleton Telemetry object that emits structured JSON events
to stdout (or a configurable sink). Each pipeline stage records its own
span so downstream analytics can reconstruct the full run timeline.

Usage::

    from platform.telemetry import Telemetry
    t = Telemetry.get()
    with t.span("stage_1_kane") as span:
        span.set("requirements", 7)
        span.set("passed", 4)
        # ... do work ...
    t.flush()
"""
from __future__ import annotations

import json
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator


class Span:
    """A single timed execution unit within the pipeline."""

    def __init__(self, name: str, telemetry: "Telemetry") -> None:
        self.name = name
        self._t = telemetry
        self._fields: dict[str, Any] = {}
        self._start = time.monotonic()
        self._start_ts = datetime.now(timezone.utc).isoformat()

    def set(self, key: str, value: Any) -> "Span":
        self._fields[key] = value
        return self

    def finish(self, success: bool = True) -> dict:
        elapsed = round(time.monotonic() - self._start, 3)
        record = {
            "event": "span",
            "name": self.name,
            "status": "ok" if success else "error",
            "started_at": self._start_ts,
            "duration_s": elapsed,
            **self._fields,
        }
        self._t._emit(record)
        return record


class Telemetry:
    """
    Singleton telemetry collector.

    Emits newline-delimited JSON to stdout by default.
    Set ASTLC_TELEMETRY_SINK=stderr or ASTLC_TELEMETRY_SINK=none to change.
    """

    _instance: "Telemetry | None" = None

    def __init__(self) -> None:
        import os
        sink = os.environ.get("ASTLC_TELEMETRY_SINK", "stdout").lower()
        self._sink = sink
        self._run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        self._events: list[dict] = []
        self._pipeline_start = time.monotonic()

    @classmethod
    def get(cls) -> "Telemetry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        cls._instance = None

    # ── Public API ────────────────────────────────────────────────────────────

    def event(self, name: str, **fields: Any) -> None:
        self._emit({"event": name, **fields})

    def stage_start(self, stage_id: str, stage_name: str) -> None:
        self._emit({"event": "stage_start", "stage_id": stage_id, "stage_name": stage_name})

    def stage_end(self, stage_id: str, stage_name: str, success: bool, **fields: Any) -> None:
        elapsed = round(time.monotonic() - self._pipeline_start, 3)
        self._emit({
            "event": "stage_end",
            "stage_id": stage_id,
            "stage_name": stage_name,
            "status": "ok" if success else "error",
            "pipeline_elapsed_s": elapsed,
            **fields,
        })

    @contextmanager
    def span(self, name: str) -> Iterator[Span]:
        s = Span(name, self)
        try:
            yield s
            s.finish(success=True)
        except Exception:
            s.finish(success=False)
            raise

    def flush(self) -> list[dict]:
        """Return all collected events."""
        return list(self._events)

    def summary(self) -> dict:
        total = round(time.monotonic() - self._pipeline_start, 3)
        errors = [e for e in self._events if e.get("status") == "error"]
        return {
            "run_id": self._run_id,
            "total_duration_s": total,
            "total_events": len(self._events),
            "error_count": len(errors),
        }

    # ── Internal ──────────────────────────────────────────────────────────────

    def _emit(self, record: dict) -> None:
        record.setdefault("ts", datetime.now(timezone.utc).isoformat())
        record.setdefault("run_id", self._run_id)
        self._events.append(record)
        if self._sink == "stdout":
            print(json.dumps(record, default=str), file=sys.stdout, flush=True)
        elif self._sink == "stderr":
            print(json.dumps(record, default=str), file=sys.stderr, flush=True)
        # sink == "none": collect only, no output
