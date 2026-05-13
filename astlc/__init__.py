"""Agentic STLC Platform — enterprise-grade autonomous QA orchestration."""

__version__ = "1.0.0"
__author__ = "Agentic STLC Platform"

from .config import PlatformConfig
from .telemetry import Telemetry
from .registry import SkillRegistry, AdapterRegistry

__all__ = ["PlatformConfig", "Telemetry", "SkillRegistry", "AdapterRegistry"]
