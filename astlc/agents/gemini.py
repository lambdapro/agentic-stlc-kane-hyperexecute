"""
GeminiAgent — adapter for Google Gemini.

Invocation priority:
  1. Gemini CLI (`gemini -p "..."`)
  2. Google GenAI Python SDK (google.generativeai)
"""
from __future__ import annotations

import json
import os

from .base import AIAgentBase, AgentContext, AgentResult


class GeminiAgent(AIAgentBase):
    PROVIDER = "gemini"
    CAPABILITIES = [
        "requirement_analysis",
        "edge_case_generation",
        "exploratory_scenarios",
        "confidence_analysis",
    ]

    # ── Availability ──────────────────────────────────────────────────────────

    def _check_cli_available(self) -> bool:
        return self._cli_exists("gemini")

    def _check_api_key_available(self) -> bool:
        return bool(
            os.environ.get("GEMINI_API_KEY", "").strip()
            or os.environ.get("GOOGLE_API_KEY", "").strip()
        )

    # ── Execution ─────────────────────────────────────────────────────────────

    def _run(self, task: str, context: AgentContext, prompt: str) -> AgentResult:
        if self._check_cli_available():
            return self._run_cli(task, prompt)
        if self._check_api_key_available():
            return self._run_api(task, prompt)
        raise RuntimeError(
            "GeminiAgent: neither 'gemini' CLI nor GEMINI_API_KEY / GOOGLE_API_KEY is available."
        )

    def _run_cli(self, task: str, prompt: str) -> AgentResult:
        raw = self._run_subprocess(["gemini", "-p", prompt], timeout=120)
        return AgentResult(
            provider=self.PROVIDER,
            task=task,
            output=raw,
            structured={},
            success=True,
        )

    def _run_api(self, task: str, prompt: str) -> AgentResult:
        import google.generativeai as genai  # type: ignore[import]
        api_key = (
            os.environ.get("GEMINI_API_KEY")
            or os.environ.get("GOOGLE_API_KEY", "")
        )
        genai.configure(api_key=api_key)
        model_name = self._config.get("model", "gemini-2.0-flash")
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(prompt)
        text = response.text if hasattr(response, "text") else str(response)
        return AgentResult(
            provider=self.PROVIDER,
            task=task,
            output=text,
            structured={},
            success=True,
        )
