"""
Skill 5: GitHub Workflow Trigger

Triggers a CI/CD workflow run and optionally waits for completion.
Adapter-backed: swaps GitHub / GitLab / Bitbucket via config.
"""
from __future__ import annotations

import os
import time
from typing import Any

from .base import AgentSkill


class WorkflowTriggerSkill(AgentSkill):
    name = "workflow_trigger"
    description = "Trigger CI/CD workflow and optionally poll for completion"
    version = "1.0.0"

    input_schema = {
        "workflow_id":  {"type": str, "required": True, "description": "Workflow file name or ID"},
        "ref":          {"type": str, "required": False, "description": "Branch/tag ref (default: config branch)"},
        "inputs":       {"type": dict, "required": False, "description": "Workflow dispatch inputs"},
        "wait":         {"type": bool, "required": False, "description": "Wait for completion (default False)"},
        "timeout_s":    {"type": int, "required": False, "description": "Max wait seconds (default 1800)"},
    }

    def run(self, **inputs: Any) -> dict:
        self.validate_inputs(**inputs)
        workflow_id = inputs["workflow_id"]
        ref = inputs.get("ref") or (self.config.project.branch if self.config else "main") or "main"
        wf_inputs = inputs.get("inputs", {})
        wait = inputs.get("wait", False)
        timeout_s = inputs.get("timeout_s", 1800)

        provider = (self.config.adapters.ci if self.config else None) or "github_actions"
        adapter = self._get_adapter(provider)

        run_id = adapter.trigger_workflow(workflow_id, ref, wf_inputs)
        result = {"success": bool(run_id), "run_id": run_id, "provider": provider, "ref": ref}

        if wait and run_id:
            status = self._poll(adapter, run_id, timeout_s)
            result["final_status"] = status.get("conclusion", "unknown")
            result["run_url"] = status.get("html_url", "")

        return result

    def _get_adapter(self, provider: str):
        if provider == "github_actions":
            from adapters.github import GitHubActionsAdapter
            return GitHubActionsAdapter(
                token=os.environ.get("GITHUB_TOKEN", ""),
                repo=self.config.project.repository if self.config else "",
            )
        raise ValueError(f"Unsupported CI provider: {provider}")

    def _poll(self, adapter, run_id: str, timeout_s: int) -> dict:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            status = adapter.get_workflow_status(run_id)
            if status.get("status") == "completed":
                return status
            time.sleep(30)
        return {"status": "timeout", "conclusion": "timed_out"}
