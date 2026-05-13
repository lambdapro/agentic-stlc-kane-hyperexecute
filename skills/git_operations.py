"""
Skill: Git Operations

Provides automated git operations for the chat-first workflow:
- create feature branch
- stage and commit generated files
- push to remote
- optionally open a PR

Used by ConversationalOrchestrator to auto-commit generated test files
before triggering the CI pipeline.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from .base import AgentSkill


class GitOperationsSkill(AgentSkill):
    name = "git_operations"
    description = "Create branch, commit generated files, push to remote"
    version = "1.0.0"

    input_schema = {
        "branch":         {"type": str, "required": True,  "description": "Branch name to create/use"},
        "files":          {"type": list, "required": True,  "description": "List of file paths to commit"},
        "commit_message": {"type": str, "required": False, "description": "Commit message"},
        "base_branch":    {"type": str, "required": False, "description": "Base branch to branch from (default: main)"},
        "push":           {"type": bool,"required": False, "description": "Push after commit (default: True)"},
        "remote":         {"type": str, "required": False, "description": "Remote name (default: origin)"},
    }

    output_schema = {
        "success":      {"type": bool},
        "branch":       {"type": str},
        "commit_sha":   {"type": str},
        "pushed":       {"type": bool},
    }

    def run(self, **inputs: Any) -> dict:
        branch         = inputs.get("branch", "")
        files          = inputs.get("files", [])
        commit_message = inputs.get("commit_message", "chore: auto-generated tests from agentic-stlc")
        base_branch    = inputs.get("base_branch", "main")
        push           = inputs.get("push", True)
        remote         = inputs.get("remote", "origin")

        if not branch:
            return {"success": False, "error": "branch is required"}
        if not files:
            return {"success": False, "error": "files list is empty"}

        try:
            self._ensure_branch(branch, base_branch)
            self._stage(files)
            sha = self._commit(commit_message)
            pushed = False
            if push:
                pushed = self._push(remote, branch)
            return {
                "success": True,
                "branch": branch,
                "commit_sha": sha,
                "pushed": pushed,
            }
        except Exception as exc:
            print(f"[git_operations] error: {exc}", file=sys.stderr)
            return {"success": False, "error": str(exc), "branch": branch}

    # ── Internal ──────────────────────────────────────────────────────────────

    @staticmethod
    def _run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(cmd, capture_output=True, text=True, check=check, timeout=60)

    def _ensure_branch(self, branch: str, base: str) -> None:
        # Fetch to make sure we have the latest remote refs
        self._run(["git", "fetch", "--quiet"], check=False)

        # Check if branch already exists locally
        local_result = self._run(["git", "branch", "--list", branch], check=False)
        if branch in local_result.stdout:
            self._run(["git", "checkout", branch], check=False)
            return

        # Check if branch exists on remote
        remote_result = self._run(["git", "branch", "-r", "--list", f"origin/{branch}"], check=False)
        if f"origin/{branch}" in remote_result.stdout:
            self._run(["git", "checkout", "-b", branch, f"origin/{branch}"])
            return

        # Check for uncommitted changes: if the working tree is dirty, create the
        # branch at HEAD rather than attempting a full remote-base checkout, which
        # would fail when local changes conflict with the target base.
        dirty = self._run(["git", "status", "--porcelain"], check=False).stdout.strip()
        if dirty:
            # Create branch from current HEAD (pipeline-generated files are already on disk)
            self._run(["git", "checkout", "-b", branch])
            return

        # Clean working tree — create from resolved remote base
        resolved_base = self._resolve_base(base)
        self._run(["git", "checkout", "-b", branch, resolved_base])

    def _resolve_base(self, requested_base: str) -> str:
        """Return 'origin/BRANCH' for the best available base branch."""
        candidates = [requested_base, "main", "master", "develop", "trunk"]
        remote_branches = self._run(["git", "branch", "-r"], check=False).stdout

        for candidate in candidates:
            ref = f"origin/{candidate}"
            if ref in remote_branches:
                return ref

        # Last resort: current HEAD
        head = self._run(["git", "rev-parse", "HEAD"], check=False).stdout.strip()
        return head or "HEAD"

    def _stage(self, files: list[str]) -> None:
        existing = [f for f in files if Path(f).exists()]
        if not existing:
            raise RuntimeError("None of the specified files exist on disk")
        self._run(["git", "add"] + existing)

    def _commit(self, message: str) -> str:
        env = dict(os.environ)
        # Set a default author if git config is missing
        env.setdefault("GIT_AUTHOR_NAME", "Agentic STLC")
        env.setdefault("GIT_AUTHOR_EMAIL", "platform@lambdatest.com")
        env.setdefault("GIT_COMMITTER_NAME", "Agentic STLC")
        env.setdefault("GIT_COMMITTER_EMAIL", "platform@lambdatest.com")

        result = subprocess.run(
            ["git", "commit", "-m", message],
            capture_output=True, text=True, env=env, timeout=30
        )
        if result.returncode != 0:
            if "nothing to commit" in result.stdout or "nothing to commit" in result.stderr:
                # Idempotent — no new changes
                sha_result = subprocess.run(
                    ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10
                )
                return sha_result.stdout.strip()
            raise RuntimeError(result.stderr or result.stdout)

        # Extract SHA from commit output
        sha_result = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10
        )
        return sha_result.stdout.strip()

    def _push(self, remote: str, branch: str) -> bool:
        result = self._run(["git", "push", remote, branch, "--set-upstream"], check=False)
        return result.returncode == 0
