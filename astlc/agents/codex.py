"""
CodexAgent — adapter for OpenAI Codex / GPT models.

Invocation priority:
  1. `codex` CLI (OpenAI Codex CLI if installed)
  2. OpenAI Python SDK (openai.OpenAI().chat.completions.create)
"""
from __future__ import annotations

import json
import os

from .base import AIAgentBase, AgentContext, AgentResult


class CodexAgent(AIAgentBase):
    PROVIDER = "codex"
    CAPABILITIES = [
        "code_generation",
        "playwright_generation",
        "refactoring",
        "code_review",
    ]

    # ── Availability ──────────────────────────────────────────────────────────

    def _check_cli_available(self) -> bool:
        return self._cli_exists("codex")

    def _check_api_key_available(self) -> bool:
        return bool(os.environ.get("OPENAI_API_KEY", "").strip())

    # ── Execution ─────────────────────────────────────────────────────────────

    def _run(self, task: str, context: AgentContext, prompt: str) -> AgentResult:
        if self._check_cli_available():
            return self._run_cli(task, prompt)
        if self._check_api_key_available():
            return self._run_api(task, prompt)
        raise RuntimeError(
            "CodexAgent: neither 'codex' CLI nor OPENAI_API_KEY is available."
        )

    def _run_cli(self, task: str, prompt: str) -> AgentResult:
        raw = self._run_subprocess(
            ["codex", "--full-auto", "-q", prompt],
            timeout=180,
        )
        return AgentResult(
            provider=self.PROVIDER,
            task=task,
            output=raw,
            structured={},
            success=True,
        )

    def _run_api(self, task: str, prompt: str) -> AgentResult:
        import openai  # type: ignore[import]
        client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        model = self._config.get("model", "gpt-4o")
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4096,
        )
        text = response.choices[0].message.content or ""
        return AgentResult(
            provider=self.PROVIDER,
            task=task,
            output=text,
            structured={},
            success=True,
        )
