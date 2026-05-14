"""
ClaudeAgent — adapter for Anthropic Claude.

Invocation priority:
  1. Claude Code CLI (`claude -p "..." --output-format json`)
  2. Anthropic Python SDK (anthropic.Anthropic().messages.create)
"""
from __future__ import annotations

import json
import os

from .base import AIAgentBase, AgentContext, AgentResult


class ClaudeAgent(AIAgentBase):
    PROVIDER = "claude"
    CAPABILITIES = [
        "requirement_analysis",
        "rca",
        "architecture",
        "planning",
        "code_review",
        "confidence_analysis",
    ]

    # ── Availability ──────────────────────────────────────────────────────────

    def _check_cli_available(self) -> bool:
        return self._cli_exists("claude")

    def _check_api_key_available(self) -> bool:
        return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())

    # ── Execution ─────────────────────────────────────────────────────────────

    def _run(self, task: str, context: AgentContext, prompt: str) -> AgentResult:
        if self._check_cli_available():
            return self._run_cli(task, prompt)
        if self._check_api_key_available():
            return self._run_api(task, prompt)
        raise RuntimeError(
            "ClaudeAgent: neither 'claude' CLI nor ANTHROPIC_API_KEY is available."
        )

    def _run_cli(self, task: str, prompt: str) -> AgentResult:
        raw = self._run_subprocess(
            ["claude", "-p", prompt, "--output-format", "json"],
            timeout=120,
        )
        try:
            data = json.loads(raw)
            text = data.get("result", data.get("content", raw))
        except json.JSONDecodeError:
            text = raw
        return AgentResult(
            provider=self.PROVIDER,
            task=task,
            output=text if isinstance(text, str) else json.dumps(text),
            structured=data if isinstance(data, dict) else {},
            success=True,
        )

    def _run_api(self, task: str, prompt: str) -> AgentResult:
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        msg = client.messages.create(
            model=self._config.get("model", "claude-sonnet-4-6"),
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        text = msg.content[0].text if msg.content else ""
        return AgentResult(
            provider=self.PROVIDER,
            task=task,
            output=text,
            structured={},
            success=True,
        )
