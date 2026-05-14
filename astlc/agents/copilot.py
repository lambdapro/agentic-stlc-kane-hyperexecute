"""
CopilotAgent — adapter for GitHub Copilot.

Invocation: `gh copilot suggest "<prompt>"` (GitHub Copilot CLI extension).
GitHub Copilot has no public programmatic chat API; only the CLI extension
(gh copilot) and IDE integrations are available.

Capabilities are limited to tasks where Copilot excels: code review, CI
insights, and PR-level commentary — not full requirement analysis or RCA.
"""
from __future__ import annotations

import os

from .base import AIAgentBase, AgentContext, AgentResult


class CopilotAgent(AIAgentBase):
    PROVIDER = "copilot"
    CAPABILITIES = [
        "code_review",
        "ci_insights",
        "inline_completion",
        "pr_review",
    ]

    # ── Availability ──────────────────────────────────────────────────────────

    def _check_cli_available(self) -> bool:
        # gh must be present AND have copilot extension installed
        if not self._cli_exists("gh"):
            return False
        try:
            self._run_subprocess(["gh", "copilot", "--version"], timeout=10)
            return True
        except Exception:
            return False

    def _check_api_key_available(self) -> bool:
        # GITHUB_TOKEN is the implicit credential; no separate API key
        return bool(os.environ.get("GITHUB_TOKEN", "").strip())

    # ── Execution ─────────────────────────────────────────────────────────────

    def _run(self, task: str, context: AgentContext, prompt: str) -> AgentResult:
        if not self._check_cli_available():
            raise RuntimeError(
                "CopilotAgent: 'gh copilot' CLI extension is not installed. "
                "Install with: gh extension install github/gh-copilot"
            )
        return self._run_cli(task, prompt)

    def _run_cli(self, task: str, prompt: str) -> AgentResult:
        # gh copilot suggest reads from stdin in non-interactive mode
        raw = self._run_subprocess(
            ["gh", "copilot", "suggest", "-t", "shell", prompt],
            timeout=60,
        )
        return AgentResult(
            provider=self.PROVIDER,
            task=task,
            output=raw,
            structured={},
            success=True,
        )
