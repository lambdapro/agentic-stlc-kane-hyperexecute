"""
AgentRouter — routes tasks to the right AI agent with fallback support.

Routing priority (highest to lowest):
  1. Explicit config preference (ai_agents.<task>: claude)
  2. Capability match from registered agents
  3. Primary agent from config (ai_agents.primary)
  4. Fallback chain from config (ai_agents.fallback_chain)
"""
from __future__ import annotations

from typing import Callable

from .base import AIAgentBase, AgentContext, AgentResult


UpdateFn = Callable[[str], None]


class AgentRoutingError(RuntimeError):
    pass


# Prompt templates per task type
_PROMPT_TEMPLATES: dict[str, str] = {
    "requirement_analysis": (
        "Analyze the following software requirements and identify gaps, ambiguities, "
        "and acceptance criteria coverage.\n\nContext:\n{context}\n\nRequirements:\n{requirements}"
    ),
    "edge_case_generation": (
        "Generate edge cases and boundary conditions for the following requirements. "
        "Focus on negative tests, race conditions, and unusual user paths.\n\n"
        "Context:\n{context}\n\nScenarios:\n{scenarios}"
    ),
    "playwright_generation": (
        "Generate Playwright test functions in Python (pytest-playwright) for the following "
        "test scenarios. Use async/await. Each test must have a @pytest.mark.scenario marker.\n\n"
        "Context:\n{context}\n\nScenarios:\n{scenarios}"
    ),
    "code_review": (
        "Review the following generated test code for correctness, Playwright best practices, "
        "and potential flakiness.\n\nContext:\n{context}\n\nCode:\n{code}"
    ),
    "rca": (
        "Perform root cause analysis on the following test failures. Categorize each failure, "
        "suggest fixes, and identify patterns.\n\nContext:\n{context}\n\nFailures:\n{failures}"
    ),
    "ci_insights": (
        "Analyze the following CI pipeline results and suggest improvements to reliability, "
        "speed, and coverage.\n\nContext:\n{context}\n\nResults:\n{results}"
    ),
    "confidence_analysis": (
        "Assess the confidence level (HIGH/MEDIUM/LOW) of each test scenario based on "
        "requirement clarity, test coverage, and known risk areas.\n\nContext:\n{context}\n\n"
        "Scenarios:\n{scenarios}"
    ),
}


class AgentRouter:
    """
    Routes tasks to the appropriate AI agent with automatic fallback.

    Args:
        agents:   dict of provider_name → AIAgentBase instance
        config:   dict from ai_agents config section
        on_update: optional callback for status messages
    """

    def __init__(
        self,
        agents: dict[str, AIAgentBase],
        config: dict | None = None,
        on_update: UpdateFn | None = None,
    ) -> None:
        self._agents  = agents
        self._config  = config or {}
        self._emit    = on_update or (lambda _: None)

    # ── Public ────────────────────────────────────────────────────────────────

    def route(self, task: str, context: AgentContext, extra: dict | None = None) -> AgentResult:
        """Route `task` to the best available agent, with fallback."""
        prompt   = self._build_prompt(task, context, extra or {})
        sequence = self._fallback_sequence(task)

        if not sequence:
            raise AgentRoutingError(
                f"No agent available for task '{task}'. "
                "Check ai_agents config and ensure at least one agent has credentials."
            )

        last_error = ""
        for agent in sequence:
            self._emit(f"> {agent.PROVIDER.capitalize()} handling '{task}'...")
            result = agent.execute(task, context, prompt)
            if result.success:
                return result
            last_error = result.error
            self._emit(
                f"> {agent.PROVIDER.capitalize()} failed for '{task}': {last_error[:120]}. "
                "Trying fallback..."
            )

        raise AgentRoutingError(
            f"All agents failed for task '{task}'. Last error: {last_error}"
        )

    def available_agents(self) -> list[str]:
        """Return list of provider names whose agents are currently available."""
        return [name for name, agent in self._agents.items() if agent.is_available()]

    def agent_for_task(self, task: str) -> str | None:
        """Return the provider name that would handle `task`, or None."""
        seq = self._fallback_sequence(task)
        return seq[0].PROVIDER if seq else None

    # ── Routing logic ─────────────────────────────────────────────────────────

    def _fallback_sequence(self, task: str) -> list[AIAgentBase]:
        """Build ordered list of agents to try for this task."""
        ordered: list[AIAgentBase] = []
        seen: set[str] = set()

        def _add(name: str) -> None:
            if name in seen or name not in self._agents:
                return
            agent = self._agents[name]
            if agent.is_available() and agent.supports(task):
                ordered.append(agent)
                seen.add(name)

        # 1. Explicit task → provider mapping from config
        task_provider = self._config.get(task, "")
        if task_provider:
            _add(task_provider)

        # 2. Capability-matched agents from fallback_chain
        fallback_chain: list[str] = self._config.get("fallback_chain", [])
        for name in fallback_chain:
            _add(name)

        # 3. Primary agent if it supports the task
        primary = self._config.get("primary", "claude")
        _add(primary)

        # 4. Any remaining registered agent that supports the task
        for name in self._agents:
            _add(name)

        return ordered

    # ── Prompt building ───────────────────────────────────────────────────────

    # Maximum items sent per list to any agent prompt.
    # Pre-slicing before json.dumps() avoids serialising 1000-item lists
    # and then discarding 99% of the output — the primary token hotspot in
    # multi-agent mode.
    _MAX_REQS     = 10
    _MAX_SCENARIOS = 10
    _MAX_FAILURES  = 5

    def _build_prompt(self, task: str, context: AgentContext, extra: dict) -> str:
        import json
        template = _PROMPT_TEMPLATES.get(task, "Perform task: {task}\n\nContext:\n{context}")

        # Pre-slice BEFORE json.dumps — never serialise a 1000-item list only
        # to discard it after slicing the string.
        reqs     = context.requirements[:self._MAX_REQS]
        scenarios = context.scenarios[:self._MAX_SCENARIOS]
        failures  = context.rca.get("failures", [])[:self._MAX_FAILURES]

        placeholders = {
            "task":         task,
            "context":      context.summary(),
            "requirements": json.dumps(reqs,      indent=2),
            "scenarios":    json.dumps(scenarios,  indent=2),
            "failures":     json.dumps(failures,   indent=2),
            "results":      json.dumps(
                                {k: context.test_results[k] for k in list(context.test_results)[:8]},
                                indent=2,
                            ),
            "code":         extra.get("code", ""),
        }

        try:
            return template.format(**placeholders)
        except KeyError:
            return f"Perform task '{task}'.\n\nContext:\n{context.summary()}"
