"""
Base AgentSkill interface.

All platform skills inherit from AgentSkill and implement run().
Skills are:
  - Stateless between invocations (context is passed per call)
  - Config-driven (PlatformConfig injected at construction)
  - Repository-agnostic (no hardcoded paths)
  - Independently testable

Skill lifecycle:
    skill = MySkill(config=cfg, context={})
    skill.validate_inputs(key=value)      # raises ValueError if invalid
    result = skill.run(key=value)          # returns structured dict
    assert skill.validate_output(result)   # optional post-run validation
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class AgentSkill(ABC):
    """Abstract base class for all Agentic STLC skills."""

    name: str = ""
    description: str = ""
    version: str = "1.0.0"

    # Input schema: {"param_name": {"type": str, "required": True, "description": "..."}}
    input_schema: dict[str, dict] = {}

    # Output schema: {"key": {"type": str, "description": "..."}}
    output_schema: dict[str, dict] = {}

    def __init__(self, config: Any, context: dict | None = None) -> None:
        self.config = config
        self.context = context or {}

    # ── Abstract interface ────────────────────────────────────────────────────

    @abstractmethod
    def run(self, **inputs: Any) -> dict:
        """
        Execute the skill.

        Returns:
            Structured dict with at minimum: {"success": bool, ...}
        """

    # ── Optional hooks ────────────────────────────────────────────────────────

    def validate_inputs(self, **inputs: Any) -> None:
        """Raise ValueError for missing required inputs."""
        for param, schema in self.input_schema.items():
            if schema.get("required") and param not in inputs:
                raise ValueError(f"[{self.name}] Required input '{param}' is missing")

    def validate_output(self, result: dict) -> bool:
        """Validate output keys are present. Returns True if valid."""
        for key in self.output_schema:
            if key not in result:
                return False
        return True

    def on_success(self, result: dict) -> None:
        """Hook called after successful run. Override for custom post-processing."""

    def on_failure(self, error: Exception) -> dict:
        """Hook called on run failure. Returns fallback result dict."""
        return {"success": False, "error": str(error), "skill": self.name}

    # ── Convenience helpers ───────────────────────────────────────────────────

    @property
    def reports_dir(self) -> str:
        if self.config and hasattr(self.config, "reports_dir"):
            return str(self.config.reports_dir)
        if self.config:
            try:
                return self.config.reporting.output_dir or "reports"
            except Exception:
                pass
        return "reports"

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r}, version={self.version!r})"
