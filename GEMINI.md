# GEMINI — Agentic STLC

Instructions for Google Gemini CLI when working with this repository.

## Project Summary

**Agentic STLC** — autonomous QA pipeline:

```
requirements.txt → Kane AI verification → Playwright tests → HyperExecute parallel execution → traceability matrix
```

- **Repository:** https://github.com/lambdapro/agentic-stlc-kane-hyperexecute  
- **Target:** Microsoft Power Apps / web application under test
- **Stack:** Python 3.11, Playwright, pytest, HyperExecute, LambdaTest Grid

## Your Role in This Pipeline

When invoked by the multi-agent orchestrator (`astlc/agents/orchestrator.py`), Gemini typically handles:

1. **Edge case generation** — boundary conditions, negative tests, race conditions, unusual user paths
2. **Exploratory scenarios** — happy-path variations and non-obvious user journeys
3. **Confidence analysis** — assess scenario clarity and test coverage gaps

## Output Formats

### Edge case generation
Return a JSON array:
```json
[
  {
    "id": "EC-001",
    "parent_scenario": "SC-001",
    "description": "User submits empty search form",
    "type": "negative",
    "expected_behavior": "Error message displayed"
  }
]
```

### Confidence analysis
Return a JSON array:
```json
[
  {
    "scenario_id": "SC-001",
    "confidence_level": "HIGH",
    "confidence_reason": "Clear acceptance criteria with measurable outcomes"
  }
]
```

## Repository Structure

```
requirements/search.txt   ← plain-English input (edit to add tests)
scenarios/scenarios.json  ← managed scenario pool (SC-001…, never delete)
ci/                       ← all pipeline stage scripts
astlc/                    ← Python platform package
  agents/                 ← multi-agent adapters (this is where you're called from)
tests/playwright/         ← auto-generated test file (do not edit)
reports/                  ← runtime artifacts (gitignored)
```

## Coding Style (when generating code)

- Python 3.11+
- Pytest with `@pytest.mark.scenario("SC-XXX")` markers
- Playwright async API (`async def test_...(page: Page)`)
- No mocks for external services — use real browser automation

## Critical Rules

- Scenario IDs (SC-001…) are **immutable** — never suggest renaming or deleting
- `tests/playwright/test_powerapps.py` is **auto-generated** — flag any direct edits
- Both Kane AI (functional) AND Playwright (regression) must pass for a GREEN verdict
