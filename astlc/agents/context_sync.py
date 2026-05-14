"""
ContextFileManager — generates and synchronises AI context files.

Writes/updates:
  CLAUDE.md                          → Claude Code
  AGENTS.md                          → OpenAI Codex CLI, Codex
  GEMINI.md                          → Gemini CLI
  .github/copilot-instructions.md    → GitHub Copilot
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


class ContextFileManager:
    """
    Generates standard AI context files from current project state.

    Args:
        repo_root: absolute path to the repository root (default: cwd)
    """

    def __init__(self, repo_root: str | Path | None = None) -> None:
        self._root = Path(repo_root) if repo_root else Path.cwd()

    # ── Public ────────────────────────────────────────────────────────────────

    def sync(self, project_state: dict | None = None) -> list[str]:
        """
        Regenerate all context files from `project_state`.

        project_state keys (all optional):
          project_name, repo_url, branch, target_url,
          stages, requirements_count, scenarios_count,
          test_framework, execution_provider

        Returns list of file paths written.
        """
        state = project_state or {}
        written: list[str] = []

        files = [
            (self._root / "AGENTS.md",                        self._agents_md(state)),
            (self._root / "GEMINI.md",                        self._gemini_md(state)),
            (self._root / ".github" / "copilot-instructions.md", self._copilot_md(state)),
        ]

        for path, content in files:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            written.append(str(path))

        return written

    # ── Content generators ────────────────────────────────────────────────────

    def _agents_md(self, s: dict) -> str:
        project   = s.get("project_name", "Agentic STLC")
        repo_url  = s.get("repo_url", "")
        target    = s.get("target_url", "")
        req_count = s.get("requirements_count", 0)
        sc_count  = s.get("scenarios_count", 0)
        framework = s.get("test_framework", "playwright")
        provider  = s.get("execution_provider", "hyperexecute")

        return f"""\
# AGENTS — {project}

This file instructs AI coding agents (OpenAI Codex, GPT-4, Codex CLI) on how to work within this repository.

## Project Overview

**{project}** is an autonomous Software Testing Lifecycle (STLC) platform.
It transforms plain-English requirements into executed, traced test results
with no human writing a single test.

{f"- **Repository:** {repo_url}" if repo_url else ""}
{f"- **Target application:** {target}" if target else ""}
- **Test framework:** {framework} (Python)
- **Cloud execution:** {provider} (LambdaTest)
- **Requirements:** {req_count}
- **Scenarios:** {sc_count}

## Pipeline Stages

| Stage | Script | Purpose |
|-------|--------|---------|
| 1 | `ci/analyze_requirements.py` | Kane AI functional verification per AC |
| 2 | `ci/manage_scenarios.py` | Diff + sync scenario pool (SC-001…) |
| 3 | `ci/generate_tests_from_scenarios.py` | Generate Playwright test functions |
| 4 | `ci/select_tests.py` | Build test manifest (incremental vs full) |
| 5 | HyperExecute CLI | Parallel VM execution |
| 6 | `ci/fetch_api_details.py` | Collect LambdaTest session data |
| 7 | `ci/build_traceability.py` + `ci/release_recommendation.py` | Traceability matrix + verdict |

## Coding Conventions

- Python 3.11+, async where possible
- All Playwright tests go in `tests/playwright/test_powerapps.py` (auto-generated — do NOT edit)
- Scenario IDs (SC-001…) are immutable — never renumber or delete
- No LLM for test generation — pipeline is deterministic

## Key Files

- `requirements/search.txt` — plain-English requirements (human editable)
- `scenarios/scenarios.json` — scenario catalog
- `ci/agent.py` — main orchestrator (Stages 2–7)
- `astlc/` — Python platform package
- `hyperexecute.yaml` — HyperExecute config

## What NOT to Do

- Do NOT edit `tests/playwright/test_powerapps.py` directly
- Do NOT delete entries from `scenarios/scenarios.json`
- Do NOT add LLM steps to test generation
- Do NOT hardcode SC or AC IDs
"""

    def _gemini_md(self, s: dict) -> str:
        project  = s.get("project_name", "Agentic STLC")
        repo_url = s.get("repo_url", "")
        target   = s.get("target_url", "")

        return f"""\
# GEMINI — {project}

Instructions for Google Gemini CLI when working with this repository.

## Project Summary

**{project}** — autonomous QA pipeline: requirements → Kane AI verification → Playwright tests → HyperExecute parallel execution → traceability matrix.

{f"Repository: {repo_url}" if repo_url else ""}
{f"Target: {target}" if target else ""}

## Your Role in This Pipeline

When invoked by the multi-agent orchestrator, Gemini typically handles:
- **Edge case generation:** boundary conditions, negative tests, race conditions
- **Exploratory scenarios:** unusual user paths beyond the happy path
- **Confidence analysis:** assessing scenario clarity and test coverage gaps

## Repository Structure

```
requirements/search.txt   ← plain-English input (edit this to add tests)
scenarios/scenarios.json  ← managed scenario pool (SC-001…, never delete)
ci/                       ← all pipeline stage scripts
astlc/                    ← Python platform package
tests/playwright/         ← auto-generated test file (do not edit)
```

## Coding Style

- Python 3.11+
- Pytest with `@pytest.mark.scenario("SC-XXX")` markers
- Playwright async API
- No mocks for the database or external APIs in integration tests

## Gemini-Specific Notes

- When generating scenarios, output JSON array with fields: id, description, feature, acceptance_criteria
- When analyzing confidence, output JSON array with: id, confidence_level (HIGH/MEDIUM/LOW), confidence_reason
- Truncate individual output items to 200 characters to keep reports readable
"""

    def _copilot_md(self, s: dict) -> str:
        project  = s.get("project_name", "Agentic STLC")
        repo_url = s.get("repo_url", "")

        return f"""\
# Copilot Instructions — {project}

{f"Repository: {repo_url}" if repo_url else ""}

## Context

This is an autonomous QA platform. Playwright tests are **auto-generated** from `scenarios/scenarios.json`.
Do not suggest manual edits to `tests/playwright/test_powerapps.py`.

## PR Review Guidelines

When reviewing pull requests in this repository:

1. **Scenario IDs are immutable.** Never suggest renumbering SC-001, SC-002, etc.
2. **Generated test file is read-only.** Flag any direct edits as incorrect.
3. **Pipeline stages are sequential.** Stages 1–7 in `ci/` must run in order.
4. **Both Kane AND Playwright must pass** for a requirement to be GREEN.
5. **HyperExecute config** (`hyperexecute.yaml`) must specify `concurrency: 5` and `runtime: python 3.11`.

## CI Patterns

- GitHub Actions workflow: `.github/workflows/agentic-stlc.yml`
- Two jobs: `analyze` (Stage 1) → `orchestrate` (Stages 2–7)
- Artifacts: `junit.xml`, `traceability_matrix.json`, `quality_gates.json`, `api_details.json`

## Code Quality

- Use `httpx` for HTTP calls (not `requests`)
- Use `asyncio` for concurrent operations
- Avoid hardcoded test IDs — always read from `scenarios.json`
- Follow `pytest-playwright` patterns for browser fixtures
"""

