# Copilot Instructions — Agentic STLC

Repository: https://github.com/lambdapro/agentic-stlc-kane-hyperexecute

## Context

This is an **autonomous QA platform**. Playwright tests are **auto-generated** from `scenarios/scenarios.json`.
Do not suggest manual edits to `tests/playwright/test_powerapps.py` — it is overwritten on every pipeline run.

## Architecture at a Glance

```
requirements/search.txt  →  Kane AI (ci/analyze_requirements.py)
                         →  Scenarios (scenarios/scenarios.json)
                         →  Playwright tests (tests/playwright/test_powerapps.py)  ← AUTO-GENERATED
                         →  HyperExecute (5 parallel VMs)
                         →  Traceability matrix + GREEN/YELLOW/RED verdict
```

## PR Review Guidelines

1. **Scenario IDs are immutable.** Never suggest renumbering SC-001, SC-002, etc.
2. **Generated test file is read-only.** Any direct edits to `test_powerapps.py` are wrong.
3. **Pipeline stages are sequential.** Stages 1–7 in `ci/` must run in order.
4. **Both Kane AND Playwright must pass** for a requirement to be GREEN in the traceability matrix.
5. **HyperExecute config** (`hyperexecute.yaml`) must keep `concurrency: 5` and `runtime: python 3.11`.
6. **Deprecated scenarios stay forever** — `scenarios/scenarios.json` entries are never deleted.

## CI Patterns

- Workflow: `.github/workflows/agentic-stlc.yml`
- Two jobs: `analyze` (Stage 1, Kane AI) → `orchestrate` (Stages 2–7)
- Artifacts uploaded: `junit.xml`, `traceability_matrix.json`, `quality_gates.json`, `api_details.json`
- HyperExecute reads test list from `reports/pytest_selection.txt`

## Code Style

- Python 3.11+
- Use `httpx` for HTTP (not `requests`)
- Use `asyncio` for concurrent work
- Pytest markers: `@pytest.mark.scenario("SC-XXX")`, `@pytest.mark.requirement("AC-XXX")`
- Never hardcode test IDs — read from `scenarios/scenarios.json`

## Multi-Agent Layer

`astlc/agents/` contains adapters for Claude, Copilot, Gemini, and Codex.
Copilot is primarily used for **code review** and **PR-level commentary** via `gh copilot suggest`.
The `AgentRouter` in `astlc/agents/router.py` handles capability-based routing and fallback.

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `GITHUB_TOKEN` | Push + CI trigger (repo + workflow scopes required) |
| `LT_USERNAME` | LambdaTest username for HyperExecute |
| `LT_ACCESS_KEY` | LambdaTest access key |
| `ANTHROPIC_API_KEY` | Claude API (optional if claude CLI is installed) |
| `OPENAI_API_KEY` | Codex/GPT-4 API |
| `GEMINI_API_KEY` | Gemini API (or GOOGLE_API_KEY) |
