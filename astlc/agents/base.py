"""
AIAgentBase — abstract base for all AI agent adapters.

AgentContext  — shared execution context propagated to every agent.
AgentResult   — structured result returned by every agent.execute() call.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentContext:
    """Shared context propagated to all agents during a pipeline run."""
    requirements: list[dict] = field(default_factory=list)
    scenarios: list[dict] = field(default_factory=list)
    test_results: dict = field(default_factory=dict)
    rca: dict = field(default_factory=dict)
    hyperexecute: dict = field(default_factory=dict)
    repo_url: str = ""
    branch: str = ""
    target_url: str = ""
    artifacts: dict = field(default_factory=dict)
    extra: dict = field(default_factory=dict)

    def summary(self) -> str:
        """Return a compact text summary for injection into agent prompts."""
        lines = []
        if self.requirements:
            lines.append(f"Requirements: {len(self.requirements)} total")
        if self.scenarios:
            lines.append(f"Scenarios: {len(self.scenarios)} total")
        if self.repo_url:
            lines.append(f"Repository: {self.repo_url}")
        if self.target_url:
            lines.append(f"Target URL: {self.target_url}")
        if self.rca.get("failures"):
            lines.append(f"Failures: {len(self.rca['failures'])} in RCA")
        return "\n".join(lines) if lines else "No context available."


@dataclass
class AgentResult:
    """Result returned by every agent.execute() call."""
    provider: str
    task: str
    output: str
    structured: dict = field(default_factory=dict)
    duration_s: float = 0.0
    retries: int = 0
    success: bool = True
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "provider":   self.provider,
            "task":       self.task,
            "output":     self.output,
            "structured": self.structured,
            "duration_s": round(self.duration_s, 2),
            "retries":    self.retries,
            "success":    self.success,
            "error":      self.error,
        }


class AIAgentBase(ABC):
    """
    Abstract base for all AI agent adapters.

    Subclasses declare CAPABILITIES and PROVIDER, then implement execute().
    The router uses supports() to select the right agent per task.
    """

    CAPABILITIES: list[str] = []
    PROVIDER: str = ""
    MAX_RETRIES: int = 2

    def __init__(self, config: dict | None = None) -> None:
        self._config = config or {}

    # ── Public interface ──────────────────────────────────────────────────────

    def supports(self, capability: str) -> bool:
        return capability in self.CAPABILITIES

    def is_available(self) -> bool:
        """Return True if the agent can be invoked (CLI present or API key set)."""
        return self._check_cli_available() or self._check_api_key_available()

    def execute(
        self,
        task: str,
        context: AgentContext,
        prompt: str,
        max_retries: int | None = None,
    ) -> AgentResult:
        """Run the task with automatic retry on failure."""
        attempts = max_retries if max_retries is not None else self.MAX_RETRIES
        last_error = ""
        t0 = time.monotonic()

        for attempt in range(attempts + 1):
            try:
                result = self._run(task, context, prompt)
                result.duration_s = time.monotonic() - t0
                result.retries = attempt
                return result
            except Exception as exc:
                last_error = str(exc)
                if attempt < attempts:
                    time.sleep(2 ** attempt)  # exponential back-off

        return AgentResult(
            provider=self.PROVIDER,
            task=task,
            output="",
            success=False,
            error=last_error,
            duration_s=time.monotonic() - t0,
            retries=attempts,
        )

    # ── Subclass hooks ────────────────────────────────────────────────────────

    @abstractmethod
    def _run(self, task: str, context: AgentContext, prompt: str) -> AgentResult:
        """Actual invocation — implemented by each adapter."""
        ...

    def _check_cli_available(self) -> bool:
        return False

    def _check_api_key_available(self) -> bool:
        return False

    # ── Shared utilities ──────────────────────────────────────────────────────

    @staticmethod
    def _run_subprocess(cmd: list[str], input_text: str = "", timeout: int = 120) -> str:
        """Run a CLI command and return stdout. Raises RuntimeError on failure."""
        import subprocess
        result = subprocess.run(
            cmd,
            input=input_text,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Command {cmd[0]} failed (exit {result.returncode}): {result.stderr[:500]}"
            )
        return result.stdout.strip()

    @staticmethod
    def _cli_exists(name: str) -> bool:
        """Return True if `name` is on PATH."""
        import shutil
        return shutil.which(name) is not None
