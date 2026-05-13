"""Agentic STLC Platform — enterprise-grade autonomous QA orchestration."""

__version__ = "1.0.0"
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
]
