# Agentic STLC — Claude Context Reference

## Project Overview

**Agentic STLC** is a fully automated Software Testing Lifecycle pipeline that transforms plain-English requirements into executed, traced test results — with no human writing a single test. It chains **Kane AI** (functional browser verification per acceptance criterion) with **HyperExecute** (parallel Playwright regression at scale on LambdaTest Grid), and produces a traceability matrix and GREEN/YELLOW/RED release verdict automatically.

The pipeline is entirely deterministic. No LLM is used for test generation. Kane AI verifies live site behavior; Playwright tests are generated from hardcoded templates.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Functional Testing | Kane CLI (`@testmuai/kane-cli`) — AI-driven browser automation via LambdaTest Playwright |
| Regression Testing | Playwright (Python) + pytest 8.2.0 |
| Cloud Execution | HyperExecute CLI (LambdaTest parallel VMs) |
| Grid Provider | LambdaTest (Selenium Grid, Automate API) |
| Orchestration | Python 3.11+, asyncio, httpx, MCP client |
| CI/CD | GitHub Actions (2-job workflow) |
| Reporting | pytest-html, JUnit XML, custom JSON/Markdown traceability |
| Dependencies | See `requirements.txt` (playwright, pytest, pytest-playwright, mcp, httpx) |

---

## Directory Structure

```
d:/agentic-stlc/
├── .github/workflows/
│   └── agentic-stlc.yml        # GitHub Actions: 2 jobs (analyze + orchestrate)
│
├── ci/                          # All pipeline stage scripts
│   ├── agent.py                 # Main orchestrator: Stages 2–7
│   ├── analyze_requirements.py  # Stage 1: Run Kane CLI per acceptance criterion
│   ├── manage_scenarios.py      # Stage 2: Sync scenarios.json with requirements
│   ├── generate_tests_from_scenarios.py  # Stage 3: Generate Selenium tests
│   ├── select_tests.py          # Stage 4: Build test manifest (incremental vs full)
│   ├── build_traceability.py    # Stage 7a: Map Kane + HE results → requirements
│   ├── release_recommendation.py # Stage 7b: Compute GREEN/YELLOW/RED verdict
│   ├── write_github_summary.py  # Stage 7c: Format GitHub Actions summary
│   ├── analyze_hyperexecute_failures.py  # Parse HE failure logs
│   ├── fetch_api_details.py     # Query LambdaTest API via MCP
│   └── run_pytest_node.py       # Single test executor (used by HE per VM)
│
├── requirements/
│   ├── search.txt               # INPUT: Plain-English requirements (edit this to add/change tests)
│   ├── cart.txt                 # Additional requirements file
│   └── analyzed_requirements.json  # OUTPUT Stage 1: Kane results + metadata (auto-generated)
│
├── scenarios/
│   └── scenarios.json           # Managed scenario pool (SC-001…); never delete entries
│
├── kane/
│   └── objectives.json          # Kane objective per scenario (scenario_id → objective)
│
├── tests/playwright/
│   ├── conftest.py              # pytest fixtures: Playwright browser, LambdaTest CDP, markers
│   └── test_powerapps.py        # AUTO-GENERATED Playwright tests — do NOT edit manually
│
├── reports/                     # Runtime artifacts (gitignored, generated each run)
│   ├── traceability_matrix.md   # Requirement → Scenario → Test → Result mapping
│   ├── traceability_matrix.json # Machine-readable traceability
│   ├── release_recommendation.md # QA verdict with reasoning
│   ├── junit.xml                # pytest JUnit report
│   ├── report.html              # pytest HTML report
│   ├── test_execution_manifest.json  # Which tests ran this pipeline
│   ├── pytest_selection.txt     # Test node IDs for HyperExecute discovery
│   ├── kane_results.json        # Aggregated Kane AI results
│   └── api_details.json         # LambdaTest API responses (sessions, builds)
│
├── docker/                      # Docker build/deployment config
├── hyperexecute.yaml            # HyperExecute config: concurrency=5, Python 3.11
├── pytest.ini                   # pytest marker definitions (scenario, requirement)
├── requirements.txt             # Python dependencies
├── PIPELINE.md                  # Stage definitions in natural language (170 lines)
└── DEMO_SCRIPT.md               # Full pipeline walkthrough (406 lines)
```

---

## Pipeline Stages

### Stage 1 — Analyze Requirements
- **Script:** `ci/analyze_requirements.py`
- **Input:** `requirements/search.txt` (plain-English user stories + acceptance criteria)
- **Process:** Parses acceptance criteria, runs `kane-cli run` per criterion (5 parallel workers via ThreadPoolExecutor), captures NDJSON output (status, one_liner, steps, duration, session link)
- **Output:** `requirements/analyzed_requirements.json` (AC-001 through AC-N with Kane results)
- **CI Job:** `analyze` (Job 1)

### Stage 2 — Manage Scenarios
- **Script:** `ci/manage_scenarios.py` (called from `ci/agent.py`)
- **Input:** `requirements/analyzed_requirements.json` + `scenarios/scenarios.json`
- **Process:** Deterministic diff — new requirements → new SC-xxx (status: "new"), changed → status: "updated", removed → status: "deprecated" (never deleted), unchanged → status: "active"
- **Output:** Updated `scenarios/scenarios.json`

### Stage 3 — Generate Playwright Tests
- **Script:** `ci/generate_tests_from_scenarios.py` (called from `ci/agent.py`)
- **Input:** `scenarios/scenarios.json`
- **Process:** Reads active scenarios, maps each to a hardcoded Playwright body from `PLAYWRIGHT_BODIES` dict in `agent.py`. Builds pytest functions with `@pytest.mark.scenario("SC-001")` and `@pytest.mark.requirement("AC-001")` markers.
- **Output:** `tests/playwright/test_powerapps.py` (auto-generated), `kane/objectives.json`
- **IMPORTANT:** The generated test file must NEVER be edited manually — it is overwritten each run.

### Stage 4 — Test Selection
- **Script:** `ci/select_tests.py` (called from `ci/agent.py`)
- **Input:** `scenarios/scenarios.json` + `FULL_RUN` env var
- **Process:** If `FULL_RUN=true` → include all non-deprecated; else → incremental (only "new" + "updated")
- **Output:** `reports/pytest_selection.txt` (one test node per line), `reports/test_execution_manifest.json`

### Stage 5 — HyperExecute Regression
- **Script:** `ci/agent.py` (run_hyperexecute function)
- **Input:** `reports/pytest_selection.txt` + `hyperexecute.yaml`
- **Process:** Downloads HE CLI if absent, submits job with `--user LT_USERNAME --key LT_ACCESS_KEY --config hyperexecute.yaml`. HE fans tests out to 5 parallel VMs. Each VM runs: `PYTHONPATH=. pytest "$test" --html=... --junitxml=...` and connects to LambdaTest Grid via `conftest.py` fixture.
- **Output:** HyperExecute job ID, JUnit XML, HTML report, per-test LambdaTest session videos

### Stage 6 — Fetch Results
- **Script:** `ci/agent.py` (fetch_and_save_mcp_results + _fetch_he_sessions_api)
- **Input:** HyperExecute job ID
- **Process:** Polls HE `/v2.0/job/{id}/sessions` API (max 15 min, 30 attempts, 30s sleep). Falls back to LT Automation API if HE API returns 403. Uses MCP (Model Context Protocol) for additional LambdaTest state queries.
- **Output:** `reports/api_details.json` (he_summary, he_tasks list with session links)

### Stage 7 — Traceability + Verdict
- **Scripts:** `ci/build_traceability.py` → `ci/release_recommendation.py` → `ci/write_github_summary.py`
- **Input:** `requirements/analyzed_requirements.json`, `scenarios/scenarios.json`, `reports/api_details.json`, `reports/test_execution_manifest.json`, JUnit XML
- **Process:**
  - Maps every test result back to its requirement (Kane functional + Playwright regression combined)
  - A requirement is "PASSED" only if BOTH Kane AND Playwright pass
  - Computes pass rate, coverage, failing scenarios
  - Verdict thresholds: **GREEN** (≥90% pass, full coverage) / **YELLOW** (≥75%) / **RED** (<75%)
- **Output:** `reports/traceability_matrix.md`, `reports/traceability_matrix.json`, `reports/release_recommendation.md`, GitHub Actions step summary

---

## Key Architectural Rules

1. **Scenario IDs are immutable.** SC-001 always maps to the same requirement. Never renumber or delete. Only set status="deprecated".

2. **`tests/playwright/test_powerapps.py` is auto-generated.** Do not edit it. Changes are overwritten on the next pipeline run. Add new Playwright bodies to the `PLAYWRIGHT_BODIES` dict in `ci/agent.py`.

3. **No LLM for test generation.** All Playwright test bodies are hardcoded templates in `agent.py`. Kane AI is a specialized functional testing tool, not an LLM agent.

4. **Incremental by default.** Only new/updated scenarios run unless `FULL_RUN=true`. This is set via GitHub Actions workflow dispatch input or environment variable.

5. **Both verifications required.** For a requirement to be GREEN in the traceability matrix, both Kane (functional) and Playwright (regression) must pass.

6. **History is never lost.** Deprecated scenarios stay in `scenarios.json` forever. This enables trend analysis and rollback.

7. **MCP is used for LambdaTest queries.** `agent.py` uses httpx + Model Context Protocol to query LambdaTest services, not raw REST calls.

---

## Environment Variables

| Variable | Where Set | Purpose |
|---|---|---|
| `LT_USERNAME` | GitHub Secrets / local `.env` | LambdaTest account username |
| `LT_ACCESS_KEY` | GitHub Secrets / local `.env` | LambdaTest API access key |
| `GITHUB_TOKEN` | GitHub Actions (auto) | For writing step summaries, artifact uploads |
| `FULL_RUN` | Workflow dispatch input | `true` = run all tests; default = incremental |
| `RUN_NUMBER` | GitHub Actions (auto) | Used in HyperExecute build name |
| `GITHUB_STEP_SUMMARY` | GitHub Actions (auto) | Path for writing Actions summary |
| `KANE_CREDENTIALS` | Kane CLI config | Passed inline to kane-cli commands |
| `M365_USERNAME` | GitHub Secrets / local `.env` | Microsoft 365 account for Power Apps login |
| `M365_PASSWORD` | GitHub Secrets / local `.env` | Microsoft 365 password for Power Apps login |

---

## Critical Files Reference

| File | Purpose | Pipeline Stage |
|---|---|---|
| `requirements/search.txt` | Human-editable input requirements | Input |
| `ci/analyze_requirements.py` | Kane AI execution per criterion | Stage 1 |
| `requirements/analyzed_requirements.json` | Kane results with session links | Stage 1 → Stage 2 |
| `ci/manage_scenarios.py` | Diff and sync scenario pool | Stage 2 |
| `scenarios/scenarios.json` | Immutable scenario catalog (SC-001…) | Stage 2 → Stage 3 |
| `ci/agent.py` | Main orchestrator (Stages 2–7) | Stages 2–7 |
| `tests/playwright/test_powerapps.py` | Auto-generated Playwright tests | Stage 3 output |
| `tests/playwright/conftest.py` | Playwright browser fixture, LambdaTest CDP, result logging | Stage 5 |
| `hyperexecute.yaml` | HE config (concurrency=5, Python 3.11) | Stage 5 |
| `reports/pytest_selection.txt` | Test node IDs for HE discovery | Stage 4 → Stage 5 |
| `reports/api_details.json` | HE + LT session results | Stage 6 output |
| `ci/build_traceability.py` | Merge Kane + HE results | Stage 7a |
| `ci/release_recommendation.py` | Compute GREEN/YELLOW/RED verdict | Stage 7b |
| `reports/traceability_matrix.json` | Full requirement → result mapping | Stage 7 output |
| `.github/workflows/agentic-stlc.yml` | CI/CD workflow definition | CI trigger |

---

## How to Run Locally

```bash
# Prerequisites: Python 3.11+, Node.js (for kane-cli), LT credentials in env

# Stage 1: Kane AI requirement analysis
python ci/analyze_requirements.py --requirements requirements/search.txt

# Stages 2–7: Full orchestration (after Stage 1 completes)
python ci/agent.py

# Run with full regression (all scenarios, not just new/updated)
FULL_RUN=true python ci/agent.py

# Run tests directly via pytest (after Stage 3 generates test file)
PYTHONPATH=. pytest tests/playwright/test_powerapps.py --html=reports/report.html --junitxml=reports/junit.xml
```

---

## How to Add New Requirements

1. Edit `requirements/search.txt` — add new user stories and acceptance criteria following existing format
2. Push to the repo — GitHub Actions triggers automatically
3. The pipeline will:
   - Run Kane AI on new criteria → update `analyzed_requirements.json`
   - Assign new SC-xxx IDs → update `scenarios.json`
   - Generate new pytest functions in `test_powerapps.py`
   - Add Playwright body template to `PLAYWRIGHT_BODIES` dict in `ci/agent.py` (this step may need manual implementation for new scenario types)
   - Execute new tests on HyperExecute → produce updated traceability matrix

---

## What NOT to Do

- **Do NOT edit `tests/playwright/test_powerapps.py` directly** — it is overwritten on every run
- **Do NOT delete entries from `scenarios/scenarios.json`** — mark as "deprecated" instead
- **Do NOT add an LLM step to test generation** — pipeline is intentionally deterministic
- **Do NOT hardcode test IDs or scenario IDs** — they must flow from `scenarios.json`
- **Do NOT skip the Kane stage** — functional + regression combined verdict requires both data sources
- **Do NOT run HyperExecute without `pytest_selection.txt`** — it uses that file for test discovery

---

## GitHub Actions Workflow

**File:** `.github/workflows/agentic-stlc.yml`

**Triggers:** Push to `requirements/**`, `scenarios/**`, `tests/**`, `ci/**`, or workflow file; manual dispatch with optional `full_run` input.

**Jobs:**
- `analyze` (Job 1): Runs Stage 1 (Kane AI), uploads `analyzed_requirements.json` as artifact
- `orchestrate` (Job 2): Depends on Job 1, runs Stages 2–7 via `ci/agent.py`, uploads all reports

**HyperExecute Config (`hyperexecute.yaml`):**
- Concurrency: 5 parallel VMs
- Runtime: Python 3.11
- Retries: 1 per failing test
- Test discovery: Dynamic from `reports/pytest_selection.txt`
- Timeout per test: 90 seconds
- Browser: Chrome latest on Windows 10

---

## Autonomous Execution Policy

When the user says "proceed", "run", "execute", or similar, execute the full pipeline without interruption. **Never ask for confirmation or clarification** on any of the following — just proceed:

- Retry logic, flaky test handling, or backoff intervals
- Locator or selector patching for Playwright failures
- Sync timing fixes (wait_for_load_state, wait_for_timeout)
- Kane objective alignment or task override updates
- Playwright test regeneration after scenarios change
- Branch naming for generated test commits
- Artifact collection strategy (local vs. GitHub)
- Flaky test rerun thresholds
- RCA analysis depth or source selection
- GitHub Actions workflow rerun decisions
- Report generation format or verbosity
- Cache invalidation or pipeline cache hits
- Self-healing patch scope (Kane objectives, scenarios.json only — never application code)
- Login prerequisite injection into Kane objectives
- Test stabilization approach for known flaky steps
- HyperExecute rerun decisions after partial failures
- Selector regeneration strategy

**Principle:** The pipeline is deterministic. Claude's role during execution is to emit progress updates and deliver the final summary, not to deliberate. Fixing the application under test is the responsibility of Claude or Copilot agents acting on the guidance in `reports/failure_intelligence.md` and `reports/self_healing.md` — not the pipeline itself.
