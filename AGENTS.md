# AGENTS — Agentic STLC

This file instructs AI coding agents (OpenAI Codex, GPT-4, Codex CLI) on how to work within this repository.

## Project Overview

**Agentic STLC** is an autonomous Software Testing Lifecycle platform that transforms plain-English
requirements into executed, traced test results — with no human writing a single test.

- **Repository:** https://github.com/lambdapro/agentic-stlc-kane-hyperexecute
- **Test framework:** Playwright (Python / pytest-playwright)
- **Cloud execution:** HyperExecute (LambdaTest, 5 parallel VMs)
- **Functional verification:** Kane AI per acceptance criterion

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

- Python 3.11+, asyncio for concurrent operations
- All Playwright tests live in `tests/playwright/test_powerapps.py` (**auto-generated — do NOT edit**)
- Scenario IDs (SC-001…) are immutable — never renumber or delete
- No LLM for test generation — the pipeline is intentionally deterministic
- Use `httpx` for HTTP calls (not `requests`)
- Use `@pytest.mark.scenario("SC-XXX")` and `@pytest.mark.requirement("AC-XXX")` markers

## Key Files

| File | Purpose |
|------|---------|
| `requirements/search.txt` | Human-editable plain-English requirements |
| `scenarios/scenarios.json` | Managed scenario pool |
| `ci/agent.py` | Main orchestrator (Stages 2–7) |
| `astlc/conversation.py` | Chat-first orchestrator |
| `astlc/agents/` | Multi-agent adapter layer |
| `hyperexecute.yaml` | HyperExecute concurrency config |
| `.github/workflows/agentic-stlc.yml` | CI/CD workflow |

## What NOT to Do

- Do NOT edit `tests/playwright/test_powerapps.py` directly
- Do NOT delete entries from `scenarios/scenarios.json` (mark deprecated instead)
- Do NOT add LLM steps to test generation (pipeline is deterministic)
- Do NOT hardcode SC or AC IDs — they must flow from `scenarios.json`
- Do NOT skip the Kane verification stage

## Multi-Agent Role

When this platform runs in multi-agent mode, Codex typically handles:
- **Playwright test generation** — given scenario specs, produce pytest-playwright functions
- **Code review** — assess generated tests for correctness and flakiness risk
- **Refactoring** — improve test helper utilities without changing test semantics

Output format for code generation tasks: valid Python with no prose, ready to be appended to `test_powerapps.py`.
