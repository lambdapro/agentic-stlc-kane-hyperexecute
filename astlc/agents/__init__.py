"""Multi-agent / multi-model support for the Agentic STLC platform."""

from .base        import AIAgentBase, AgentContext, AgentResult
from .claude      import ClaudeAgent
from .copilot     import CopilotAgent
from .gemini      import GeminiAgent
from .codex       import CodexAgent
from .router      import AgentRouter, AgentRoutingError
from .context_sync import ContextFileManager
from .orchestrator import MultiAgentOrchestrator

__all__ = [
    "AIAgentBase",
    "AgentContext",
    "AgentResult",
    "ClaudeAgent",
    "CopilotAgent",
    "GeminiAgent",
    "CodexAgent",
    "AgentRouter",
    "AgentRoutingError",
    "ContextFileManager",
    "MultiAgentOrchestrator",
]
