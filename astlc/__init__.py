"""Agentic STLC Platform — enterprise-grade autonomous QA orchestration."""

__version__ = "1.1.0"
__author__ = "Agentic STLC Platform"

from .config import PlatformConfig
from .telemetry import Telemetry
from .registry import SkillRegistry, AdapterRegistry
from .conversation import ConversationalOrchestrator
from .chat_reporter import ChatReporter
from .file_ingestor import FileIngestor
from .credential_validator import CredentialValidator
from .pipeline_monitor import PipelineMonitor
from .report_collector import ReportCollector
from .artifact_cache import ArtifactCache
from .state_engine import PipelineStateEngine, PipelineState, StageRecord
from .execution_engine import ProgrammaticExecutionEngine, CompactExecutionResult
from .agents import MultiAgentOrchestrator, AgentRouter, ContextFileManager

__all__ = [
    "PlatformConfig",
    "Telemetry",
    "SkillRegistry",
    "AdapterRegistry",
    "ConversationalOrchestrator",
    "ChatReporter",
    "FileIngestor",
    "CredentialValidator",
    "PipelineMonitor",
    "ReportCollector",
    "ArtifactCache",
    "PipelineStateEngine",
    "PipelineState",
    "StageRecord",
    "ProgrammaticExecutionEngine",
    "CompactExecutionResult",
    "MultiAgentOrchestrator",
    "AgentRouter",
    "ContextFileManager",
]
