"""Agentic STLC Adapters — pluggable integrations for any CI/CD, Git, or execution provider."""

from .base import GitAdapter, CIAdapter, ExecutionAdapter, FunctionalTestAdapter, ReportingAdapter
from .github import GitHubAdapter, GitHubActionsAdapter
from .gitlab import GitLabAdapter
from .jenkins import JenkinsAdapter
from .azure_devops import AzureDevOpsAdapter
from .hyperexecute import HyperExecuteAdapter
from .kaneai import KaneAIAdapter
from .playwright import PlaywrightAdapter

# Auto-register adapters
from astlc.registry import AdapterRegistry

AdapterRegistry.register("git",               "github",          GitHubAdapter)
AdapterRegistry.register("git",               "gitlab",          GitLabAdapter)
AdapterRegistry.register("ci",                "github_actions",  GitHubActionsAdapter)
AdapterRegistry.register("ci",                "gitlab_ci",       GitLabAdapter)
AdapterRegistry.register("ci",                "jenkins",         JenkinsAdapter)
AdapterRegistry.register("ci",                "azure_devops",    AzureDevOpsAdapter)
AdapterRegistry.register("execution",         "hyperexecute",    HyperExecuteAdapter)
AdapterRegistry.register("functional_testing","kaneai",          KaneAIAdapter)
AdapterRegistry.register("test_framework",    "playwright",      PlaywrightAdapter)

__all__ = [
    "GitAdapter", "CIAdapter", "ExecutionAdapter", "FunctionalTestAdapter", "ReportingAdapter",
    "GitHubAdapter", "GitHubActionsAdapter",
    "GitLabAdapter",
    "JenkinsAdapter",
    "AzureDevOpsAdapter",
    "HyperExecuteAdapter",
    "KaneAIAdapter",
    "PlaywrightAdapter",
]
