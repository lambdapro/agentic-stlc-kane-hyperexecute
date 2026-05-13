"""Agentic STLC Agent Skills — reusable, framework-agnostic test automation skills."""

from .base import AgentSkill
from .requirement_parsing import RequirementParsingSkill
from .scenario_generation import ScenarioGenerationSkill
from .playwright_generation import PlaywrightGenerationSkill
from .workflow_trigger import WorkflowTriggerSkill
from .hyperexecute_monitoring import HyperExecuteMonitoringSkill
from .artifact_collection import ArtifactCollectionSkill
from .coverage_analysis import CoverageAnalysisSkill
from .confidence_analysis import ConfidenceAnalysisSkill
from .rca import RCASkill
from .claude_feedback import ClaudeFeedbackSkill

# Auto-register all skills
from astlc.registry import SkillRegistry

SkillRegistry.register("requirement_parsing",      RequirementParsingSkill)
SkillRegistry.register("scenario_generation",      ScenarioGenerationSkill)
SkillRegistry.register("playwright_generation",    PlaywrightGenerationSkill)
SkillRegistry.register("workflow_trigger",         WorkflowTriggerSkill)
SkillRegistry.register("hyperexecute_monitoring",  HyperExecuteMonitoringSkill)
SkillRegistry.register("artifact_collection",      ArtifactCollectionSkill)
SkillRegistry.register("coverage_analysis",        CoverageAnalysisSkill)
SkillRegistry.register("confidence_analysis",      ConfidenceAnalysisSkill)
SkillRegistry.register("rca",                      RCASkill)
SkillRegistry.register("claude_feedback",          ClaudeFeedbackSkill)

__all__ = [
    "AgentSkill",
    "RequirementParsingSkill",
    "ScenarioGenerationSkill",
    "PlaywrightGenerationSkill",
    "WorkflowTriggerSkill",
    "HyperExecuteMonitoringSkill",
    "ArtifactCollectionSkill",
    "CoverageAnalysisSkill",
    "ConfidenceAnalysisSkill",
    "RCASkill",
    "ClaudeFeedbackSkill",
]
