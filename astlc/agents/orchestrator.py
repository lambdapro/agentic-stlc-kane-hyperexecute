"""
MultiAgentOrchestrator — model-agnostic autonomous QA orchestration.

When ai_agents.enabled = true, this orchestrator wraps
ConversationalOrchestrator and delegates individual tasks (requirement
analysis, edge-case generation, code generation, code review, RCA) to the
configured AI agents via AgentRouter before handing control back to the
core pipeline for CI execution.

When ai_agents.enabled = false (default), it delegates directly to
ConversationalOrchestrator with zero overhead — existing behavior is
100% unchanged.
"""
from __future__ import annotations

from typing import Any, Callable

UpdateFn = Callable[[str], None]


class MultiAgentOrchestrator:
    """
    Model-agnostic orchestrator that routes tasks to the best available agent.

    Usage:
        orchestrator = MultiAgentOrchestrator(config=platform_config, on_update=emit)
        state = orchestrator.ingest(path="requirements.txt")
        result = orchestrator.execute(state, repo_url=..., branch=..., target_url=...)
    """

    def __init__(
        self,
        config: Any | None = None,
        on_update: UpdateFn | None = None,
    ) -> None:
        self._config    = config
        self._emit      = on_update or (lambda _: None)
        self._router    = None
        self._conv      = None

        self._init_core()
        self._init_agents()

    # ── Public interface ──────────────────────────────────────────────────────

    def ingest(self, path: str = "", content: str = "", filename: str = "") -> dict:
        """Delegate to ConversationalOrchestrator for requirement ingestion."""
        return self._conv.ingest(path=path, content=content, filename=filename)

    def execute(
        self,
        state: dict,
        repo_url: str = "",
        branch: str = "",
        target_url: str = "",
        auto_push: bool = True,
    ) -> dict:
        """
        Run the full pipeline. If multi-agent is enabled, enrich the state
        with AI agent outputs before the CI execution phase.
        """
        ai_cfg     = self._ai_config()
        ma_enabled = ai_cfg.get("enabled", False)

        if ma_enabled and self._router:
            return self._execute_multi_agent(
                state, repo_url, branch, target_url, auto_push, ai_cfg
            )

        return self._conv.execute(
            state=state,
            repo_url=repo_url,
            branch=branch,
            target_url=target_url,
            auto_push=auto_push,
        )

    def agent_status(self) -> list[dict]:
        """Return availability status for all registered agents."""
        if not self._router:
            return []
        agents = getattr(self._router, "_agents", {})
        return [
            {
                "provider":    name,
                "available":   agent.is_available(),
                "capabilities": agent.CAPABILITIES,
            }
            for name, agent in agents.items()
        ]

    def sync_context_files(self, project_state: dict | None = None) -> list[str]:
        """Regenerate AGENTS.md, GEMINI.md, .github/copilot-instructions.md."""
        from .context_sync import ContextFileManager
        mgr = ContextFileManager()
        return mgr.sync(project_state or self._build_project_state())

    # ── Multi-agent execution flow ────────────────────────────────────────────

    def _execute_multi_agent(
        self,
        state: dict,
        repo_url: str,
        branch: str,
        target_url: str,
        auto_push: bool,
        ai_cfg: dict,
    ) -> dict:
        from .base import AgentContext

        requirements = state.get("requirements", [])
        scenarios    = state.get("scenarios", [])

        ctx = AgentContext(
            requirements=requirements,
            scenarios=scenarios,
            repo_url=repo_url,
            branch=branch,
            target_url=target_url,
        )

        participation: list[dict] = []

        # ── Requirement analysis ──────────────────────────────────────────────
        if requirements:
            result = self._try_route("requirement_analysis", ctx, ai_cfg)
            if result:
                participation.append(result.to_dict())
                state["ai_requirement_analysis"] = result.output

        # ── Edge-case generation ──────────────────────────────────────────────
        if scenarios:
            result = self._try_route("edge_case_generation", ctx, ai_cfg)
            if result:
                participation.append(result.to_dict())
                state["ai_edge_cases"] = result.output

        # ── Core CI pipeline (push → trigger → monitor → collect) ─────────────
        self._emit("> Running core CI pipeline...")
        core_result = self._conv.execute(
            state=state,
            repo_url=repo_url,
            branch=branch,
            target_url=target_url,
            auto_push=auto_push,
        )

        # ── RCA (after CI completes) ──────────────────────────────────────────
        failures = core_result.get("rca", {}).get("failures", [])
        if failures:
            ctx.rca          = core_result.get("rca", {})
            ctx.test_results = core_result.get("execution", {})
            ctx.hyperexecute = core_result.get("hyperexecute", {})
            result = self._try_route("rca", ctx, ai_cfg)
            if result:
                participation.append(result.to_dict())
                core_result.setdefault("rca", {})["ai_analysis"] = result.output

        # ── Context file sync ─────────────────────────────────────────────────
        try:
            written = self.sync_context_files(self._build_project_state())
            self._emit(f"> Context files updated: {', '.join(written)}")
        except Exception as exc:
            self._emit(f"> Context file sync skipped: {exc}")

        core_result["agent_participation"] = participation
        return core_result

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _try_route(self, task: str, ctx, ai_cfg: dict):
        """Route a task, emit status, swallow errors (non-blocking)."""
        if not self._router:
            return None
        try:
            return self._router.route(task, ctx)
        except Exception as exc:
            self._emit(f"> Agent task '{task}' skipped: {exc}")
            return None

    def _init_core(self) -> None:
        from ..conversation import ConversationalOrchestrator
        self._conv = ConversationalOrchestrator(
            config=self._config,
            on_update=self._emit,
        )

    def _init_agents(self) -> None:
        """Build agent registry and router from available adapters."""
        ai_cfg = self._ai_config()
        if not ai_cfg.get("enabled", False):
            return

        from .claude  import ClaudeAgent
        from .copilot import CopilotAgent
        from .gemini  import GeminiAgent
        from .codex   import CodexAgent
        from .router  import AgentRouter

        agents = {
            "claude":  ClaudeAgent(config=ai_cfg.get("claude_config", {})),
            "copilot": CopilotAgent(config=ai_cfg.get("copilot_config", {})),
            "gemini":  GeminiAgent(config=ai_cfg.get("gemini_config", {})),
            "codex":   CodexAgent(config=ai_cfg.get("codex_config", {})),
        }

        self._router = AgentRouter(
            agents=agents,
            config=ai_cfg,
            on_update=self._emit,
        )

    def _ai_config(self) -> dict:
        """Extract ai_agents section from platform config."""
        if not self._config:
            return {}
        ai = getattr(self._config, "ai_agents", None)
        if ai is None:
            return {}
        if hasattr(ai, "_data"):
            return dict(ai._data)
        if isinstance(ai, dict):
            return ai
        return {}

    def _build_project_state(self) -> dict:
        state: dict = {}
        if self._config:
            proj = getattr(self._config, "project", None)
            if proj:
                state["project_name"] = getattr(proj, "name", "")
                state["repo_url"]     = getattr(proj, "repository", "")
            exec_cfg = getattr(self._config, "execution", None)
            if exec_cfg:
                state["execution_provider"] = getattr(exec_cfg, "provider", "hyperexecute")
            fw = getattr(self._config, "framework", None)
            if fw:
                state["test_framework"] = getattr(fw, "type", "playwright")
        return state
