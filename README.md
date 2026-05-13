# Agentic STLC — Autonomous QA Pipeline

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Pipeline](https://github.com/lambdapro/agentic-stlc-kane-hyperexecute/actions/workflows/agentic-stlc.yml/badge.svg)](https://github.com/lambdapro/agentic-stlc-kane-hyperexecute/actions/workflows/agentic-stlc.yml)
[![Platform](https://img.shields.io/badge/platform-LambdaTest-blue)](https://lambdatest.com)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://python.org)

> Plain-English requirements go in. Executed, traced, and verdicted test results come out. No human writes a single test.

---

## What This Is

**Agentic STLC** is a fully autonomous Software Testing Lifecycle pipeline. It ingests plain-English acceptance criteria, verifies them functionally with Kane AI on a live browser, generates executable Playwright regression tests from Kane's own exported code, executes those tests in parallel across Chrome, Firefox, Safari, and Android via LambdaTest HyperExecute, and produces a requirement-level traceability matrix with a GREEN / YELLOW / RED release verdict — all without a human touching test code.

The pipeline targets **[LambdaTest Ecommerce Playground](https://ecommerce-playground.lambdatest.io/)** and is designed to be adapted to any web application by editing `requirements/*.txt` and the fallback bodies in `ci/collect_kane_exports.py`.

### Business Value

| Stakeholder | What They Get |
|---|---|
| **QA Lead** | Every requirement traced to a verified functional result AND a regression result across 4 browsers |
| **Engineering** | Tests regenerate automatically when requirements change — zero manual maintenance |
| **Release Manager** | Deterministic GREEN / YELLOW / RED verdict with evidence links per criterion |
| **Exec / Demo** | One GitHub Actions summary page shows the complete end-to-end QA story |

---

## Architecture Overview

```
requirements/*.txt          (plain-English acceptance criteria)
        │
        ▼
┌─────────────────────────────────────────────────────────────────────┐
│  STAGE 1 · KaneAI Functional Verification           [Job: analyze]  │
│                                                                     │
│  kane-cli run  ×N criteria  (5 parallel workers)                    │
│  ├── Drives real Chrome browser on LambdaTest CDP                   │
│  ├── Exports Python Playwright code per criterion                   │
│  └── Emits: passed/failed, one_liner, steps, session link           │
│                                                                     │
│  Output: requirements/analyzed_requirements.json                    │
└───────────────────────────┬─────────────────────────────────────────┘
                            │  artifact upload → Job 2 download
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│  STAGES 2–9 · Orchestrator                       [Job: orchestrate] │
│  ci/agent.py                                                        │
│                                                                     │
│  Stage 2 · Scenario Sync                                            │
│  ├── Diffs requirements vs scenarios/scenarios.json                 │
│  └── new / updated / active / deprecated — history never deleted    │
│                                                                     │
│  Stage 3 · Playwright Code Generation                               │
│  ├── Priority 1: Kane-exported Python bodies (ci/collect_kane_exports.py) │
│  ├── Priority 2: Curated fallback bodies (AC-001 through AC-015)    │
│  ├── Syntax validates generated file (py_compile)                   │
│  └── Output: tests/playwright/test_powerapps.py                     │
│                                                                     │
│  Stage 4 · Test Selection                                           │
│  ├── Full run: all non-deprecated scenarios                         │
│  ├── Incremental: only new + updated scenarios                      │
│  └── Output: reports/pytest_selection.txt                           │
│                                                                     │
│  Stage 5 · HyperExecute Regression                                  │
│  ├── Submits to LambdaTest HyperExecute (concurrency=5 VMs)        │
│  ├── Each VM: pytest "$test" → conftest.py → LambdaTest CDP        │
│  ├── Browsers: chrome, firefox, safari, android (real device)       │
│  └── Output: job_id, per-test session links, JUnit XML              │
│                                                                     │
│  Stage 6 · Result Aggregation                                       │
│  ├── MCP → HyperExecute API → LambdaTest Automation API (cascade)  │
│  ├── normalize_artifacts.py merges conftest + JUnit + HE API       │
│  └── Output: reports/normalized_results.json, api_details.json      │
│                                                                     │
│  Stage 7 · Traceability                                             │
│  ├── Maps every result → requirement (Kane + Playwright combined)   │
│  └── Output: reports/traceability_matrix.{md,json}                  │
│                                                                     │
│  Stage 8 · Release Recommendation                                   │
│  └── GREEN (≥90% pass, full coverage) / YELLOW (≥75%) / RED (<75%) │
│                                                                     │
│  Stage 9 · GitHub Summary                                           │
│  └── Full pipeline report written to GitHub Actions Step Summary    │
│                                                                     │
│  Advisory (non-blocking):                                           │
│  ├── Coverage analysis, quality gates, impact analysis              │
│  ├── LambdaTest AI root cause analysis for failed tests             │
│  └── Pipeline metrics                                               │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Pipeline Stages — Complete Reference

### Stage 1 · KaneAI Functional Verification

**Script:** `ci/analyze_requirements.py`
**CI job:** `analyze` (Job 1)

Kane AI is a specialized browser automation agent — not a general-purpose LLM. It receives a task description and a target URL, drives a real Chrome browser via LambdaTest's CDP endpoint, and returns a structured NDJSON result per criterion.

**What it does:**
- Parses all `requirements/*.txt` files, extracting lines under `Acceptance Criteria:` sections
- Assigns IDs `AC-001` through `AC-N` in order
- Calls `kane-cli run` for each criterion via a `ThreadPoolExecutor` with 5 parallel workers
- Each Kane session: real browser, video recorded, full session replay available
- Parses NDJSON output: `step_end` events → step summaries, `run_end` event → overall result
- **Code export:** Kane generates Python Playwright code for its browser actions via `--code-export --code-language python`. This exported code is stored at `~/.testmuai/kaneai/sessions/<session_id>/code-export/` and collected in Stage 3.

**Inputs:**
```
requirements/search.txt         (primary requirements file)
requirements/cart.txt           (additional requirements file)
```

**Outputs:**
```
requirements/analyzed_requirements.json   — full Kane results per AC
reports/kane_results.json                 — summarized Kane results
```

**Per-criterion record:**
```json
{
  "id": "AC-001",
  "title": "Add a product to the cart",
  "description": "User can add a product to the cart from the product detail page",
  "kane_status": "passed",
  "kane_one_liner": "Searched for products on ecommerce-playground.lambdatest.io",
  "kane_summary": "...",
  "kane_steps": ["Navigate to product page", "Click Add to Cart", "..."],
  "kane_links": ["https://automation.lambdatest.com/test?testID=..."],
  "kane_session_id": "uuid-of-kane-session",
  "kane_code_export_dir": "/home/runner/.testmuai/kaneai/sessions/<id>/code-export"
}
```

**Kane CLI invocation (per criterion):**
```bash
kane-cli run "On https://ecommerce-playground.lambdatest.io/ — <acceptance criterion>" \
  --username $LT_USERNAME \
  --access-key $LT_ACCESS_KEY \
  --ws-endpoint "wss://cdp.lambdatest.com/playwright?capabilities=..." \
  --agent --headless \
  --timeout 120 --max-steps 15 \
  --code-export --code-language python --skip-code-validation
```

**Kane exit codes:** `0=passed`, `1=failed`, `2=error`, `3=timeout`

**Cache strategy:** Results are cached in GitHub Actions by `hashFiles('requirements/*.txt')`. If requirements files are unchanged, the cached `analyzed_requirements.json` is reused and live Kane calls are skipped entirely.

**Demo mode:** Set `DEMO_MODE=true` (or use the workflow dispatch toggle) to load pre-generated results from `ci/demo_kane_results.json` — completes in under 5 seconds for demos.

---

### Stage 2 · Scenario Synchronization

**Function:** `sync_scenarios()` in `ci/agent.py`

Maintains `scenarios/scenarios.json` as the authoritative, append-only catalog of test scenarios. Scenario IDs (`SC-001`, `SC-002`, ...) are **immutable** — once assigned, a scenario ID always maps to the same requirement.

**Diff logic:**

| Condition | Action | Status |
|---|---|---|
| Requirement is new (no existing scenario) | Assign next SC-NNN, TC-NNN | `new` |
| Requirement description changed | Keep existing SC-NNN | `updated` |
| Requirement unchanged | Keep as-is | `active` |
| Requirement removed from requirements files | Keep in catalog forever | `deprecated` |

**Why deprecation instead of deletion:** Deprecated scenarios stay in `scenarios.json` permanently. This enables trend analysis, rollback comparison, and audit trail — removing a scenario from requirements does not mean it never existed.

**Outputs:**
```
scenarios/scenarios.json      — updated scenario catalog
kane/objectives.json          — Kane objective per scenario (scenario_id → objective text)
```

---

### Stage 3 · Playwright Code Generation

**Scripts:** `ci/collect_kane_exports.py` (primary), `generate_tests()` in `ci/agent.py` (fallback)

This is the test generation engine. It assembles `tests/playwright/test_powerapps.py` from real executable code — not templates.

**Priority order per scenario:**

```
Priority 1: Kane-exported Python Playwright code
            (collected from kane_code_export_dir in analyzed_requirements.json)
            ↓ if not available
Priority 2: Curated fallback body
            (hand-written Playwright actions in ci/collect_kane_exports.py,
             AC-001 through AC-015, covering all current acceptance criteria)
            ↓ if not available
Priority 3: pytest.skip() placeholder
            (scenario exists but has no implementation — visible in report)
```

**How Kane export collection works:**

Kane CLI writes Python Playwright code to `~/.testmuai/kaneai/sessions/<session_id>/code-export/`. After Stage 1, `ci/collect_kane_exports.py` reads each active scenario's `kane_code_export_dir` path from `analyzed_requirements.json`, parses the exported `.py` file using Python's `ast` module to extract the test function body, strips the function signature and `await` keywords (sync Playwright compatibility), and embeds the body into a pytest function with the correct markers.

**Generated test structure:**
```python
@pytest.mark.scenario("SC-001")
@pytest.mark.requirement("AC-001")
def test_sc_001_searched_for_products_on_ecommerce_playground(page):
    """SC-001: Searched for products on ecommerce-playground.lambdatest.io."""
    # <Kane-exported or curated Playwright body here>
    page.goto("https://ecommerce-playground.lambdatest.io/index.php?route=product/product&product_id=28")
    page.wait_for_load_state("domcontentloaded")
    add_btn = page.locator("#button-cart")
    add_btn.wait_for(timeout=15000)
    add_btn.click()
    # ... assertions
```

**Post-generation validation:** The generated file is compiled with `py_compile.compile()`. A syntax error aborts the pipeline before HyperExecute submission.

**Outputs:**
```
tests/playwright/test_powerapps.py    — auto-generated, never edit manually
kane/objectives.json                  — scenario_id → objective text
```

---

### Stage 4 · Test Selection

**Function:** `write_test_selection()` in `ci/agent.py`

Determines which tests HyperExecute will execute. Controlled by the `FULL_RUN` environment variable.

| Mode | Selected Scenarios | When Used |
|---|---|---|
| **Incremental** (`FULL_RUN=false`) | `status=new` and `status=updated` only | Default on push |
| **Full** (`FULL_RUN=true`) | All non-deprecated scenarios | Manual dispatch, or first run |

**Outputs:**
```
reports/pytest_selection.txt          — one test node ID per line
reports/test_execution_manifest.json  — {selected_scenarios: [...], run_type: "full|incremental"}
```

**Example `pytest_selection.txt`:**
```
tests/playwright/test_powerapps.py::test_sc_001_searched_for_products_on_ecommerce_playground_lamb
tests/playwright/test_powerapps.py::test_sc_002_attempted_to_open_the_cart_and_select_a_product_op
tests/playwright/test_powerapps.py::test_sc_003_opened_the_laptops_product_catalog_on_ecommerce_pl
```

---

### Stage 5 · HyperExecute Regression

**Function:** `run_hyperexecute()` in `ci/agent.py`
**Config:** `hyperexecute.yaml`

HyperExecute is LambdaTest's distributed test orchestration platform. It takes the test selection file, fans tests out across parallel cloud VMs, and runs each pytest node against a real browser on the LambdaTest Grid.

**HyperExecute configuration (`hyperexecute.yaml`):**

| Parameter | Value | Purpose |
|---|---|---|
| `concurrency` | `5` | Up to 5 VMs running tests simultaneously |
| `autosplit` | `true` | HE distributes tests across VMs automatically |
| `retryOnFailure` | `true` | Failed tests retry once |
| `maxRetries` | `1` | Maximum retry attempts per test |
| `runtime` | Python 3.11, Linux | Execution environment |
| `testDiscovery` | `cat reports/pytest_selection.txt` | Dynamic test list from Stage 4 |
| `testRunnerCommand` | `PYTHONPATH=. pytest "$test" -v --tb=short -s` | Per-test execution |
| `mergeArtifacts` | `true` | Consolidate artifacts from all VMs |

**Multi-browser execution:**

The `BROWSERS` environment variable (`chrome,firefox,safari,android`) drives pytest parametrization in `conftest.py`. Each test function runs once per browser — 7 scenarios × 4 browsers = 28 total test executions.

**Browser → LambdaTest capability mapping (`conftest.py`):**

| Browser Key | Playwright Launcher | LT browserName | Platform |
|---|---|---|---|
| `chrome` | `chromium` | `Chrome` | Windows 10 |
| `firefox` | `firefox` | `Firefox` | Windows 10 |
| `safari` | `webkit` | `Safari` | macOS Ventura |
| `android` | `chromium` | `Chrome` | Android (Galaxy S22, OS 12) |

**Android execution:** The Android browser key routes to a real LambdaTest Android device (Galaxy S22, Android 12) via the Playwright wire protocol. The HyperExecute VM remains Linux — only the browser session lands on the physical device.

**LambdaTest connection:** Tests connect via `wss://cdp.lambdatest.com/playwright?capabilities=<JSON>` using Playwright's `browser.connect()` wire protocol (not `connect_over_cdp()` — the wire protocol is required for correct session metadata).

**Per-test conftest fixture behavior:**
1. Builds LambdaTest capabilities JSON (platform, browser, build name, session name)
2. Connects to LambdaTest CDP endpoint via Playwright wire protocol
3. Creates browser context and page
4. Yields `page` to the test function
5. After test: reads pass/fail from pytest report hook
6. Calls `window['lambda-status'] = 'passed|failed'` on the LambdaTest session
7. Writes `reports/kane_result_<SC-ID>_<browser>.json` with full timing and status

**Status normalization:** HyperExecute job status is normalized from raw API values to enterprise-grade labels:

| Raw Status | Normalized | Meaning |
|---|---|---|
| `completed` / `passed` | `PASSED` | All tasks finished successfully |
| `failed` | `FAILED` | One or more tasks failed |
| `error` | `INFRA_FAILURE` | HyperExecute infrastructure error |
| `aborted` / `cancelled` | `CANCELLED` | Job manually stopped |
| `running` / `queued` | `RUNNING` | Job in progress |
| `unknown` + tasks present | Derived from tasks | MCP unavailable — derived from per-task results |
| `unknown` + no tasks | `NOT_EXECUTED` | Stage was skipped |

**Outputs:**
```
reports/hyperexecute-cli.log           — full CLI output
reports/junit.xml                      — JUnit XML (merged from all VMs)
reports/report.html                    — pytest HTML report
reports/kane_result_SC-*_<browser>.json — per-test per-browser result files
reports/api_details.json               — HE job summary + per-task session links
```

---

### Stage 6 · Result Aggregation

**Functions:** `fetch_and_save_mcp_results()` in `ci/agent.py`, then `ci/normalize_artifacts.py`

**Result fetching (three-tier cascade):**

```
Tier 1: MCP (Model Context Protocol)
        sse_client → getHyperExecuteJobInfo → polls until terminal status
        (max 30 attempts × 30s = 15 minutes)
        ↓ if MCP fails
Tier 2: HyperExecute REST API
        GET https://api.hyperexecute.cloud/v2.0/job/{job_id}
        GET https://api.hyperexecute.cloud/v2.0/job/{job_id}/sessions
        ↓ if HE API fails (403 or network error)
Tier 3: LambdaTest Automation API
        GET /automation/api/v1/builds?s=<build_name>
        GET /automation/api/v1/sessions?build_id=<id>
```

**Status derivation when API is unreachable:** If job-level status cannot be fetched but task results are available, the pipeline derives the job status from individual task outcomes: all passed → `completed`; any failed → `failed`. This eliminates the `"unknown"` state entirely.

**Artifact normalization (`ci/normalize_artifacts.py`):**

Merges three data sources into a unified result record per scenario+browser:

| Priority | Source | Data |
|---|---|---|
| 1 (highest) | `reports/kane_result_SC-*_<browser>.json` | Real timing, real status, error messages |
| 2 | `reports/junit*.xml` | pytest pass/fail, duration |
| 3 | `reports/api_details.json` he_tasks | HE session links |

When data is missing for a scenario+browser combination, status is set to `data_unavailable` — never fabricated.

**Outputs:**
```
reports/api_details.json          — HE job summary (status, normalized_status, parser_status,
                                    task_pass_count, task_fail_count) + per-task session links
reports/normalized_results.json   — unified result per scenario+browser
```

---

### Stage 7 · Requirement Traceability

**Script:** `ci/build_traceability.py`

Constructs the full requirement → scenario → test → result traceability chain. Combines Kane AI functional results (from Stage 1) with Playwright regression results (from Stage 6) at the requirement level.

**Combined verdict logic:**

```
requirement.overall = "passed"  iff  kane_status == "passed"
                                 AND  playwright_status == "passed"
                                      (across all browsers)

requirement.overall = "failed"  if   kane_status == "failed"
                                  OR  any browser playwright_status == "failed"

requirement.overall = "data_unavailable"  if  no Playwright execution data exists
```

**Feature classification:** Each requirement is automatically classified into a feature domain based on keyword matching:

| Feature | Keywords | Criticality |
|---|---|---|
| `AUTH` | register, login, logout, account, password | HIGH |
| `CHECKOUT` | checkout, shipping, flat rate | HIGH |
| `CART` | cart, add to cart, remove, update quantity | HIGH |
| `SEARCH` | search, find product, search result | MEDIUM |
| `CATALOG` | catalog, laptops, browse, category, grid | MEDIUM |
| `PRODUCT_DETAIL` | product detail, price, thumbnail | MEDIUM |
| `FILTER` | filter, brand, sidebar | LOW |
| `SORT` | sort, price low to high | LOW |
| `WISHLIST` | wish list, wishlist | LOW |

**Coverage category annotation per requirement:**

| Category | Detection |
|---|---|
| `happy_path` | Has a scenario assigned |
| `negative` | Keywords: invalid, error, fail, reject, remove, delete |
| `edge_case` | Keywords: empty cart, boundary, duplicate, persistence |
| `mobile` | Any mobile browser (android, ios) in results |
| `android` | Android browser in results |
| `he_executed` | Has a HyperExecute session link |
| `regression` | Playwright status is not data_unavailable |

**Outputs:**
```
reports/traceability_matrix.md     — human-readable markdown table
reports/traceability_matrix.json   — machine-readable with summary + rows + result_analysis
```

**Traceability matrix structure (JSON):**
```json
{
  "summary": {
    "run_type": "full",
    "requirements_covered": 7,
    "requirements_total": 7,
    "executed": 7,
    "passed": 4,
    "pass_rate": 57.1,
    "browsers_tested": ["chrome", "firefox", "safari", "android"],
    "failing_scenarios": ["SC-001", "SC-002", "SC-004"]
  },
  "rows": [...],
  "result_analysis": {
    "overall_health": "at_risk",
    "risk_level": "medium",
    "kane_pass_rate": 57.1,
    "playwright_pass_rate": 57.1,
    "key_findings": [...],
    "recommendation_hint": "..."
  }
}
```

---

### Stage 8 · Release Recommendation

**Script:** `ci/release_recommendation.py`

Computes a deterministic GREEN / YELLOW / RED verdict from the traceability summary.

| Verdict | Condition |
|---|---|
| 🟢 **GREEN** | Pass rate ≥ 90%, no failing scenarios, no untested requirements, risk ≠ HIGH |
| 🟡 **YELLOW** | Pass rate ≥ 75%, no untested requirements, risk ≠ HIGH |
| 🔴 **RED** | Pass rate < 75%, or untested requirements exist, or risk = HIGH |

**Output:** `reports/release_recommendation.md`

---

### Stage 9 · GitHub Actions Summary

**Script:** `ci/write_github_summary.py`

Writes the full pipeline report to the GitHub Actions Step Summary (`$GITHUB_STEP_SUMMARY`). The summary is a single Markdown page containing every stage result, every requirement result, browser breakdown, traceability matrix, quality gates, coverage analysis, impact analysis, RCA findings, and the release verdict — with clickable links to every LambdaTest session.

---

### Advisory Scripts (Non-Blocking)

These scripts run after the critical pipeline and log warnings but never block the pipeline or change the exit code.

| Script | Purpose | Output |
|---|---|---|
| `ci/coverage_analysis.py` | Per-requirement coverage scoring, missing scenario detection, flakiness analysis, feature heatmap | `reports/coverage_report.json`, `reports/missing_scenarios.json`, `reports/flaky_requirements.json` |
| `ci/quality_gates.py` | Evaluate configurable pass rate, coverage, and flakiness thresholds | `reports/quality_gates.json` |
| `ci/impact_analysis.py` | Determine which requirements are impacted by recent git file changes | `reports/impacted_requirements.json` |
| `ci/fetch_rca.py` | Call LambdaTest Insights RCA API for AI-generated root cause on each failed test | `reports/rca_report.json`, `reports/rca_report.md` |
| `ci/validate_report.py` | Integrity checks on traceability matrix | `reports/validation_report.json` |
| `ci/pipeline_metrics.py` | Stage timing, cache hits, test counts | `reports/pipeline_metrics.json` |

---

## Requirement Traceability

Every acceptance criterion traces through the full pipeline:

```
AC-001 (plain English)
  └── SC-001 (scenario — immutable ID)
        └── TC-001 (test case)
              ├── Kane AI: passed ✅  →  session link, steps observed, one-liner summary
              └── Playwright regression:
                    ├── chrome:  passed ✅  →  LambdaTest session link
                    ├── firefox: passed ✅  →  LambdaTest session link
                    ├── safari:  passed ✅  →  LambdaTest session link
                    └── android: failed ❌  →  LambdaTest session link + RCA
              └── Overall: FAILED (any browser fail = requirement fails)
```

**Example traceability matrix row:**

| Req | Acceptance Criterion | Scenario | Test Case | Kane AI | Kane Session | What Kane Saw | Chrome | Firefox | Safari | Android | Playwright | Session | Overall |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `AC-001` | User can add a product to the cart from the product detail page | `SC-001` | `TC-001` | passed | [session](...) | Added HTC Touch HD to cart, cart count updated | ✅ | ✅ | ✅ | ❌ | failed | [session](...) | ❌ failed |

---

## Playwright Generation Engine

### Kane Export Pipeline

Kane AI does not just verify requirements — it writes the test code. Every Kane session with `--code-export` produces a Python Playwright `.py` file at a deterministic path:

```
~/.testmuai/kaneai/sessions/<session_uuid>/code-export/<test>.py
```

`ci/collect_kane_exports.py` collects these files after Stage 1, extracts the test function body using Python's `ast` module (for reliability), strips `async/await` for sync Playwright compatibility, and embeds the bodies into pytest functions.

**Why Kane code export matters:** The regression tests are not templates — they are the actual browser actions Kane performed when verifying the requirement. This means regression tests and functional verification share the same executable logic, reducing the gap between "it works in Kane" and "it works in pytest."

### Fallback Bodies

When Kane has no exported code (session skipped, credentials absent, demo mode), `ci/collect_kane_exports.py` contains curated Playwright implementations for AC-001 through AC-015. These are real, executable Playwright actions — not placeholder stubs.

**Supported acceptance criteria (fallback coverage):**

| AC ID | Feature | Test Action |
|---|---|---|
| AC-001 | CART | Add product to cart, verify cart count |
| AC-002 | CART | Open cart dropdown, verify items visible |
| AC-003 | CATALOG | Navigate to Laptops category, verify product grid |
| AC-004 | FILTER | Apply Apple brand filter, verify content updates |
| AC-005 | PRODUCT_DETAIL | Open product detail page, verify name and price |
| AC-006 | GUEST | Browse homepage without login, verify content |
| AC-007 | SEARCH | Search for "iPhone", verify results returned |
| AC-008 | AUTH | Register new account with unique email |
| AC-009 | AUTH | Login with credentials, verify dashboard |
| AC-010 | AUTH | Login then logout, verify redirect |
| AC-011 | CART | Add product, navigate to cart, remove item, verify empty |
| AC-012 | CART | Add product, update quantity to 3, verify updated |
| AC-013 | SORT | Sort Laptops by price low→high, verify page updates |
| AC-014 | WISHLIST | Login, add to wishlist, verify wishlist contains item |
| AC-015 | CHECKOUT | Add to cart, guest checkout with billing details |

### Locator Strategy

Playwright tests use resilient locators in priority order:
1. **Semantic locators** (`page.get_by_role()`, `page.get_by_label()`) where available
2. **ID-based** (`#button-cart`, `#input-firstname`) for stable application IDs
3. **Attribute selectors** (`input[name='search']`, `input[value='Login']`)
4. **Class + text filter** (`.list-group-item` filtered by `has_text="Apple"`)
5. **Composite with fallback** (try primary locator, fall back to secondary if count=0)

### Android Support

Android tests run on a real LambdaTest device (Galaxy S22, Android 12). The `conftest.py` fixture injects device-specific capabilities:

```python
_ANDROID_EXTRA = {
    "deviceName": "Galaxy S22",
    "osVersion":  "12",
    "isRealMobile": True,
}
```

The HyperExecute VM stays Linux. Only the browser session runs on the physical device via LambdaTest's device farm.

---

## HyperExecute Integration

### Execution Flow

```
ci/agent.py  →  hyperexecute CLI  →  HyperExecute Cloud
                                          │
                              ┌───────────┴───────────┐
                          VM 1 (pytest SC-001)    VM 2 (pytest SC-002)
                          VM 3 (pytest SC-003)    VM 4 (pytest SC-004)
                          VM 5 (pytest SC-005)
                              │
                        conftest.py fixture
                              │
                        LambdaTest CDP Grid
                              │
                   ┌──────────┼──────────┐
               Chrome      Firefox    Safari
               (Win 10)   (Win 10)  (macOS Ventura)
```

### Test Discovery

HyperExecute discovers tests dynamically from `reports/pytest_selection.txt` (generated in Stage 4):

```yaml
testDiscovery:
  type: raw
  mode: dynamic
  command: cat reports/pytest_selection.txt
```

This means HyperExecute reads the file at job start and distributes the listed test nodes across VMs. Adding or removing tests from requirements automatically changes what HE runs — no YAML changes needed.

### Artifact Collection

Each VM writes per-test artifacts. `mergeArtifacts: true` consolidates them:

```
VM 1 reports/ ─┐
VM 2 reports/ ─┤──→ merged reports/ → uploaded as "TestReports" artifact
VM 3 reports/ ─┤
VM 4 reports/ ─┤
VM 5 reports/ ─┘
```

### Job ID Extraction

The pipeline extracts the HyperExecute job ID from CLI output using multiple regex patterns to handle format variations across CLI versions:

```python
_JOB_ID_PATTERNS = [
    re.compile(r"jobId=([\w-]+)"),
    re.compile(r"job[_\s-]?id[:\s=]+([0-9a-f]{8}-...)", re.IGNORECASE),
    re.compile(r"hyperexecute/task\?jobId=([\w-]+)"),
    re.compile(r"Job\s+(?:ID|Id)[:\s]+([0-9a-f]{8}-...)", re.IGNORECASE),
]
```

If the job ID cannot be extracted, the pipeline derives the job status from task-level results rather than failing the report.

---

## KaneAI Integration

### CLI Orchestration

Kane CLI is invoked directly as a subprocess per acceptance criterion. The pipeline builds a LambdaTest CDP WebSocket endpoint with full capability JSON and passes it via `--ws-endpoint`, giving Kane a real browser session on LambdaTest infrastructure.

```
Session name: "AC-001 | User can add a product to the cart from..."
Build name:   "Agentic STLC #42 | 2026-05-12"
```

This naming convention ensures Kane sessions appear in the same LambdaTest build as the Playwright regression sessions, enabling cross-verification in the LambdaTest dashboard.

### Result Parsing

Kane CLI emits two output formats simultaneously:

| Format | Content |
|---|---|
| **NDJSON** | `step_end` events (step summaries), `run_end` event (overall result, session_id, one_liner) |
| **Plain text** | Links box with `CodeExport file:///...` path |

The parser handles both formats, extracts the session UUID from any output line matching a UUID pattern, resolves the code-export directory via `~/.testmuai/kaneai/sessions/<uuid>/code-export/`, and returns a structured result regardless of which format Kane used for a given version.

### Code Export Collection

```
Kane CLI runs with --code-export
        │
        ▼
~/.testmuai/kaneai/sessions/<uuid>/code-export/<test>.py
        │
        ▼
collect_kane_exports.py
  → ast.parse() extracts function body
  → strips async/await for sync Playwright
  → wraps in @pytest.mark.scenario + @pytest.mark.requirement
        │
        ▼
tests/playwright/test_powerapps.py
```

---

## Requirement Coverage Analysis

**Script:** `ci/coverage_analysis.py`

Produces per-requirement and per-feature coverage scoring beyond simple pass/fail.

### Coverage Status per Requirement

| Status | Condition |
|---|---|
| `FULL` | Has scenario, executed across all browsers, all passed |
| `PARTIAL` | Has scenario, executed, but some browsers failed or coverage categories missing |
| `NONE` | No scenario assigned, or no execution data |

### Coverage Categories

Each requirement is assessed across seven coverage dimensions:

| Category | What It Checks |
|---|---|
| `happy_path` | Is there a passing scenario for the core user flow? |
| `negative` | Is there a test for invalid input, rejection, or error state? |
| `edge_case` | Is there a test for boundary, duplicate, or session edge cases? |
| `mobile` | Did any mobile browser (Android, iOS) execute this requirement? |
| `android` | Did Android specifically execute this requirement? |
| `he_executed` | Did HyperExecute produce a session link (proof of cloud execution)? |
| `regression` | Does a Playwright result exist (not data_unavailable)? |

### Missing Scenario Detection

For each requirement, the coverage engine compares existing coverage categories against the feature's required scenario types. Missing coverage gaps are reported in `reports/missing_scenarios.json`:

```json
{
  "missing": [
    {
      "requirement_id": "AC-001",
      "feature": "CART",
      "criticality": "HIGH",
      "missing": [
        {"type": "negative", "description": "Test adding an out-of-stock product"},
        {"type": "edge_case", "description": "Test adding duplicate items to cart"}
      ]
    }
  ]
}
```

### Flakiness Detection

A requirement is marked flaky if:
- `retries > 0` in any browser result
- Mixed pass/fail status across retries of the same test

Flaky requirements are reported in `reports/flaky_requirements.json` and surfaced in the GitHub summary.

### Feature Coverage Heatmap

Requirements are grouped by feature domain and presented as a heatmap:

| Feature | Criticality | Total | Covered | Partial | Uncovered |
|---|---|---|---|---|---|
| AUTH | 🔴 HIGH | 3 | 2 | 1 | 0 |
| CHECKOUT | 🔴 HIGH | 1 | 1 | 0 | 0 |
| CART | 🔴 HIGH | 4 | 3 | 1 | 0 |
| SEARCH | 🟡 MEDIUM | 1 | 1 | 0 | 0 |
| CATALOG | 🟡 MEDIUM | 1 | 1 | 0 | 0 |

---

## Quality Gates

**Script:** `ci/quality_gates.py`
**Configuration:** Environment variables (all optional, sensible defaults)

Quality gates evaluate the pipeline output against configurable thresholds. CRITICAL gates exit 1 and block downstream steps. WARNING gates log but do not block.

| Gate | Default Threshold | Severity | Environment Variable |
|---|---|---|---|
| Minimum requirement coverage | 50% | WARNING | `GATE_MIN_COVERAGE_PCT` |
| Minimum Playwright pass rate | 75% | CRITICAL | `GATE_MIN_PASS_RATE` |
| Maximum flaky requirements | 5 | WARNING | `GATE_MAX_FLAKY` |
| HIGH-criticality requirements must be covered | true | CRITICAL | `GATE_REQUIRE_CRITICAL` |
| Maximum uncovered HIGH-risk requirements | 999 (disabled) | WARNING | `GATE_MAX_HIGH_RISK` |
| Minimum HyperExecute execution coverage | 0% (disabled) | WARNING | `GATE_MIN_HE_PCT` |

**Gate output example (`reports/quality_gates.json`):**
```json
{
  "gates_passed": false,
  "critical_failures": 1,
  "warnings": 2,
  "gates": [
    {
      "gate": "Playwright pass rate",
      "severity": "CRITICAL",
      "passed": false,
      "actual": 57.1,
      "threshold": 75.0,
      "unit": "%"
    }
  ]
}
```

---

## Reporting & Analytics

### GitHub Actions Step Summary

The primary report surface. Written by `ci/write_github_summary.py` to `$GITHUB_STEP_SUMMARY`. Contains:

- **Pipeline Stage Status table** — normalized status per stage with evidence
- **Stage 1: KaneAI Verification** — per-criterion pass/fail, Kane session links
- **Stage 2: Scenario Catalog** — new/updated/active/deprecated counts
- **Stage 3: Generated Tests** — function names per scenario
- **Stage 4: Test Selection** — run type, scenario count
- **Stage 5: HyperExecute Regression** — normalized status, task counts, dashboard link, parser diagnostics
- **Stage 6: Traceability Matrix** — per-requirement per-browser results, session links
- **Coverage Analysis** — heatmap, missing scenarios, flaky requirements
- **Quality Gates** — gate-by-gate pass/fail with thresholds
- **Impact Analysis** — requirements affected by recent file changes
- **Root Cause Analysis** — LambdaTest AI RCA for failed tests
- **Release Recommendation** — GREEN / YELLOW / RED with reasoning

### Stage 5 Evidence Table

Stage 5 now surfaces full diagnostic information for every pipeline run:

| Metric | Raw Value | Normalized | Evidence |
|---|---|---|---|
| HyperExecute Job | `0d040374-...` | — | [Open in LambdaTest ↗](...) |
| Job Status | `completed` | **PASSED** | source: api_ok |
| Parser Status | `api_ok` | — | how status was resolved |
| Total tasks | 14 | — | submitted to HyperExecute |
| ✅ Passed | 14 | — | task-level results |
| ❌ Failed | 0 | — | task-level results |

The `parser_status` field documents exactly how the status was resolved:

| Parser Status | Meaning |
|---|---|
| `api_ok` | Status fetched directly from HyperExecute API |
| `derived_from_tasks` | MCP unreachable — status derived from individual task results |
| `mcp_unavailable` | MCP and REST API both failed — check LT credentials |
| `not_executed` | HyperExecute stage was skipped (no job submitted) |

### LambdaTest Artifacts

Every test produces a clickable LambdaTest Automate session link with:
- Full video recording
- Network traffic capture
- Console logs
- Visual screenshots at each step
- LambdaTest AI RCA for failures (`ci/fetch_rca.py`)

---

## Project Structure

```
agentic-stlc/
│
├── requirements/
│   ├── search.txt                        ← INPUT: plain-English requirements (edit this)
│   ├── cart.txt                          ← Additional requirements file
│   └── analyzed_requirements.json        ← Stage 1 output: Kane results per AC (auto-generated)
│
├── scenarios/
│   └── scenarios.json                    ← Immutable scenario catalog (SC-001…, never delete)
│
├── kane/
│   └── objectives.json                   ← Kane objective per scenario (scenario_id → text)
│
├── tests/playwright/
│   ├── conftest.py                       ← Multi-browser fixture, LambdaTest CDP, result logging
│   └── test_powerapps.py                 ← AUTO-GENERATED — do not edit manually
│
├── ci/
│   ├── agent.py                          ← Main orchestrator: Stages 2–9
│   ├── analyze_requirements.py           ← Stage 1: Kane CLI execution per criterion
│   ├── collect_kane_exports.py           ← Stage 3a: Assemble Kane-exported Playwright code
│   ├── generate_tests_from_scenarios.py  ← Stage 3b: Template-based fallback generator
│   ├── select_tests.py                   ← Stage 4: Build pytest_selection.txt
│   ├── normalize_artifacts.py            ← Stage 6a: Merge conftest + JUnit + HE API results
│   ├── build_traceability.py             ← Stage 7: Requirement → scenario → test → result matrix
│   ├── release_recommendation.py         ← Stage 8: GREEN/YELLOW/RED verdict
│   ├── write_github_summary.py           ← Stage 9: GitHub Actions Step Summary
│   ├── coverage_analysis.py              ← Advisory: coverage scoring, missing scenarios, flakiness
│   ├── quality_gates.py                  ← Advisory: configurable pass/coverage thresholds
│   ├── impact_analysis.py                ← Advisory: git-diff → impacted requirements
│   ├── fetch_rca.py                      ← Advisory: LambdaTest AI RCA for failed tests
│   ├── validate_report.py                ← Advisory: traceability integrity checks
│   ├── pipeline_metrics.py               ← Advisory: stage timing and cache metrics
│   ├── analyze_hyperexecute_failures.py  ← HE failure log parser
│   ├── run_pytest_node.py                ← Single test executor (called by HE per VM)
│   ├── manage_scenarios.py               ← Standalone scenario sync script
│   ├── fetch_api_details.py              ← Standalone LambdaTest API fetcher
│   └── stage_utils.py                    ← Shared stage header/result printer
│
├── reports/                              ← Runtime artifacts (gitignored, generated per run)
│   ├── analyzed_requirements.json        (duplicated from requirements/ by Stage 1)
│   ├── api_details.json                  ← HE job summary + per-task session links
│   ├── normalized_results.json           ← Merged results per scenario+browser
│   ├── traceability_matrix.md            ← Human-readable traceability table
│   ├── traceability_matrix.json          ← Machine-readable traceability with summary
│   ├── release_recommendation.md         ← GREEN/YELLOW/RED verdict with reasoning
│   ├── coverage_report.json              ← Per-requirement coverage scores
│   ├── missing_scenarios.json            ← Coverage gaps per requirement
│   ├── flaky_requirements.json           ← Flaky requirement list
│   ├── quality_gates.json                ← Gate evaluation results
│   ├── impacted_requirements.json        ← Git-diff impact analysis
│   ├── rca_report.json                   ← LambdaTest AI RCA findings
│   ├── validation_report.json            ← Traceability integrity check results
│   ├── pipeline_metrics.json             ← Stage timing and cache data
│   ├── junit.xml                         ← pytest JUnit XML (merged from all VMs)
│   ├── report.html                       ← pytest HTML report
│   ├── pytest_selection.txt              ← Test node IDs for HyperExecute
│   ├── test_execution_manifest.json      ← Selected scenarios + run type
│   ├── kane_results.json                 ← Summarized Kane results
│   └── kane_result_SC-*_<browser>.json   ← Per-test per-browser result files
│
├── hyperexecute.yaml                     ← HyperExecute config: concurrency, runtime, discovery
├── pytest.ini                            ← pytest marker definitions
├── requirements.txt                      ← Python dependencies
├── CLAUDE.md                             ← Project context for Claude Code
├── PIPELINE.md                           ← Stage definitions in natural language
└── .github/workflows/
    └── agentic-stlc.yml                  ← 2-job GitHub Actions workflow
```

---

## GitHub Actions Workflow

**File:** `.github/workflows/agentic-stlc.yml`

### Triggers

| Trigger | Condition |
|---|---|
| Push | Changes to `requirements/**`, `scenarios/**`, `tests/**`, `ci/**`, `hyperexecute.yaml`, or the workflow file |
| Pull Request | Same path filters |
| Manual dispatch | `full_run` (boolean), `demo_mode` (boolean) |

### Jobs

**Job 1 — `analyze` (Stage 1)**

Runs `ci/analyze_requirements.py`. Uploads `requirements/analyzed_requirements.json` as the `analyzed-requirements` artifact.

Optimizations:
- **npm cache:** Kane CLI install cached by Node version
- **pip cache:** Python dependencies cached by `requirements.txt` hash
- **Kane results cache:** `analyzed_requirements.json` cached by `hashFiles('requirements/*.txt')`. Cache hit = skip live Kane calls entirely.

**Job 2 — `orchestrate` (Stages 2–9)**

Depends on Job 1. Downloads the `analyzed-requirements` artifact, validates it, downloads the HyperExecute CLI binary, then runs `ci/agent.py`.

```
Validate Stage 1 artifact
→ Download HyperExecute CLI (curl + ELF validation)
→ python ci/agent.py   (Stages 2–9)
→ python ci/pipeline_metrics.py  (always, even on failure)
→ Upload pipeline-reports artifact
```

### Artifact Retention

| Artifact | Contents | Retention |
|---|---|---|
| `analyzed-requirements` | `requirements/analyzed_requirements.json` | 30 days |
| `pipeline-reports` | `reports/`, `scenarios/scenarios.json`, `tests/playwright/test_powerapps.py` | 30 days |

---

## Prerequisites

| Tool | Version | Role | Install |
|---|---|---|---|
| Python | 3.11+ | CI scripts, pytest, Playwright | [python.org](https://python.org) |
| Node.js | 22 | Kane CLI | [nodejs.org](https://nodejs.org) |
| Kane CLI | latest | Stage 1 functional verification | `npm install -g @testmuai/kane-cli` |
| Playwright | latest | Regression test execution | `pip install playwright && playwright install chromium firefox webkit` |
| HyperExecute CLI | latest | Cloud parallel execution | Downloaded automatically by CI |
| LambdaTest account | — | CDP grid + HyperExecute + device farm | [lambdatest.com](https://lambdatest.com) |

---

## Setup

### 1. Clone and install dependencies

```bash
git clone https://github.com/lambdapro/agentic-stlc-kane-hyperexecute.git
cd agentic-stlc-kane-hyperexecute

pip install -r requirements.txt
npm install -g @testmuai/kane-cli
playwright install chromium firefox webkit
```

### 2. Configure environment credentials

```bash
export LT_USERNAME=your_lambdatest_username
export LT_ACCESS_KEY=your_lambdatest_access_key
```

| Variable | Where to Get | Required |
|---|---|---|
| `LT_USERNAME` | [LambdaTest Dashboard → Settings → Keys](https://accounts.lambdatest.com/security) | Yes |
| `LT_ACCESS_KEY` | Same page | Yes |
| `TARGET_URL` | Override the default ecommerce playground URL | No |
| `BROWSERS` | Comma-separated: `chrome,firefox,safari,android` | No (defaults to `chrome`) |
| `FULL_RUN` | `true` = run all scenarios, `false` = incremental | No (defaults to `true`) |
| `DEMO_MODE` | `true` = use pre-generated Kane results | No |

### 3. Configure GitHub Secrets

**Settings → Secrets and variables → Actions → New repository secret**

| Secret | Value |
|---|---|
| `LT_USERNAME` | Your LambdaTest username |
| `LT_ACCESS_KEY` | Your LambdaTest access key |

### 4. Configure Kane CLI project (once)

```bash
kane-cli config project 01J2VAWPNBPA21T0BW44JW026X
kane-cli config folder 01KPD0NC5ZXZD9EXB23QCATTG2
```

---

## Running the Pipeline

### Automated (GitHub Actions)

Push any change to a `requirements/` file:

```bash
# Add a new acceptance criterion
echo "
Title: Product Comparison
Acceptance Criteria:
User can add two products to a comparison list and view differences side by side
" >> requirements/search.txt

git add requirements/
git commit -m "feat: add product comparison requirement"
git push
```

The pipeline runs automatically. Kane AI verifies the new criterion, a Playwright test is generated (from Kane's own exported code, or the curated fallback), and HyperExecute executes it across all configured browsers.

**Manual dispatch with options:**

Go to **Actions → Agentic STLC Pipeline → Run workflow**

| Input | Description |
|---|---|
| `full_run` | `true` = run all active scenarios, `false` = only new/updated (incremental) |
| `demo_mode` | `true` = skip live Kane calls, use pre-generated results (for demos) |

### Local Execution

**Stage 1 — Kane AI verification:**
```bash
export LT_USERNAME=your_username
export LT_ACCESS_KEY=your_access_key

python ci/analyze_requirements.py --requirements requirements/search.txt
```

**Stages 2–9 — Full orchestration:**
```bash
python ci/agent.py
```

**Full run (all scenarios):**
```bash
FULL_RUN=true python ci/agent.py
```

**Download HyperExecute CLI manually (Linux/macOS):**
```bash
curl -fsSL -O https://downloads.lambdatest.com/hyperexecute/linux/hyperexecute
chmod +x hyperexecute
./hyperexecute --user $LT_USERNAME --key $LT_ACCESS_KEY --config hyperexecute.yaml
```

**Run Playwright tests directly (after Stage 3 generates the file):**
```bash
# Single test, single browser
PYTHONPATH=. pytest "tests/playwright/test_powerapps.py::test_sc_001_..." -v -s

# All tests, all browsers
BROWSERS=chrome,firefox PYTHONPATH=. pytest tests/playwright/test_powerapps.py -v

# With debug artifact output
REPORT_DEBUG=true python ci/normalize_artifacts.py
```

**Generate reports only (from existing artifacts):**
```bash
python ci/normalize_artifacts.py
python ci/build_traceability.py
python ci/release_recommendation.py
python ci/coverage_analysis.py
python ci/write_github_summary.py
cat reports/release_recommendation.md
```

**Verify a single requirement with Kane AI:**
```bash
kane-cli run \
  "On https://ecommerce-playground.lambdatest.io/ — User can search for a product by name and see relevant results" \
  --username "$LT_USERNAME" \
  --access-key "$LT_ACCESS_KEY" \
  --agent --headless --timeout 120 --max-steps 15
```

---

## Adding New Requirements

1. Edit `requirements/search.txt` — add user stories with `Acceptance Criteria:` sections:

```
Title: Product Comparison
As a shopper, I want to compare products side by side.

Acceptance Criteria:
User can add two products to a comparison list from the catalog page
User can view the comparison page showing product attributes in columns
User can remove a product from the comparison list
```

2. Commit and push. The pipeline:
   - Runs Kane AI on each new criterion (functional verification + code export)
   - Assigns new SC-NNN / TC-NNN IDs (incremental, never reused)
   - Generates Playwright tests from Kane's exported code
   - Executes new tests on HyperExecute (incremental mode — only new criteria)
   - Updates the traceability matrix with the new requirements

3. For the first run after adding new criteria, set `FULL_RUN=true` if you want all scenarios to re-run together.

---

## Model Context Protocol (MCP)

The pipeline uses MCP to communicate with LambdaTest services. For local Claude Code usage, add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "mcp-lambdatest": {
      "disabled": false,
      "timeout": 100,
      "command": "npx",
      "args": ["-y", "mcp-lambdatest", "--transport=stdio"],
      "env": {
        "LT_USERNAME": "<YOUR_LT_USERNAME>",
        "LT_ACCESS_KEY": "<YOUR_LT_ACCESS_KEY>"
      },
      "transportType": "stdio"
    }
  }
}
```

This enables Claude Code to query LambdaTest directly — list test sessions, check build status, pull failure logs — during local debugging.

---

## Adapting to Other CI/CD Tools

Each stage is a single portable Python command. The CI tool only needs Python 3.11, LambdaTest credentials, and the HyperExecute CLI binary.

### GitLab CI

```yaml
stages: [analyze, orchestrate]

analyze:
  stage: analyze
  image: node:22
  script:
    - pip install -r requirements.txt
    - npm install -g @testmuai/kane-cli
    - python ci/analyze_requirements.py
  artifacts:
    paths: [requirements/analyzed_requirements.json]
  variables:
    LT_USERNAME: $LT_USERNAME
    LT_ACCESS_KEY: $LT_ACCESS_KEY

orchestrate:
  stage: orchestrate
  image: python:3.11
  dependencies: [analyze]
  script:
    - pip install -r requirements.txt
    - curl -fsSL -O https://downloads.lambdatest.com/hyperexecute/linux/hyperexecute
    - chmod +x hyperexecute
    - python ci/agent.py
  artifacts:
    paths: [reports/]
  variables:
    LT_USERNAME: $LT_USERNAME
    LT_ACCESS_KEY: $LT_ACCESS_KEY
    FULL_RUN: "true"
```

### Jenkins

```groovy
pipeline {
    agent any
    environment {
        LT_USERNAME   = credentials('lt-username')
        LT_ACCESS_KEY = credentials('lt-access-key')
    }
    stages {
        stage('Stage 1 — KaneAI') {
            steps { sh 'python ci/analyze_requirements.py' }
        }
        stage('Stages 2–9 — Orchestrate') {
            steps {
                sh 'curl -fsSL -O https://downloads.lambdatest.com/hyperexecute/linux/hyperexecute && chmod +x hyperexecute'
                sh 'python ci/agent.py'
            }
        }
    }
    post {
        always { archiveArtifacts artifacts: 'reports/**', allowEmptyArchive: true }
    }
}
```

---

## Sample Pipeline Output

### Stage Status Summary

```
| Stage | Name                          | Status | Normalized | Details                              |
|-------|-------------------------------|--------|------------|--------------------------------------|
| 1     | KaneAI Verification           | ✅     | PASSED     | 7/7 criteria passed                  |
| 2–4   | Scenarios + Test Gen          | ✅     | PASSED     | 7 active tests generated             |
| 5     | HyperExecute Regression       | ✅     | PASSED     | 28/28 tasks · parser: api_ok         |
| 6     | Result Aggregation            | ✅     | PASSED     | 28 results normalized                |
| 7–8   | Traceability + Verdict        | 🟢     | GREEN      | 100% pass rate across 4 browsers     |
```

### Release Recommendation

```markdown
# QA Release Recommendation

**Verdict:** GREEN

## Summary
- Requirements covered: 7/7
- Scenarios executed: 7
- Pass rate: 100.0% (7 passed, 0 failed)
- Overall health: healthy
- Risk level: low
- Kane AI pass rate: 100.0%

## Failing Scenarios
- None

## Recommendation
Approve release because coverage is complete and executed tests passed.
```

### Coverage Heatmap

```
| Feature        | Criticality | Total | Covered | Partial | Uncovered |
|----------------|-------------|-------|---------|---------|-----------|
| CART           | 🔴 HIGH     | 2     | 2       | 0       | 0         |
| AUTH           | 🔴 HIGH     | 0     | 0       | 0       | 0         |
| SEARCH         | 🟡 MEDIUM   | 1     | 1       | 0       | 0         |
| CATALOG        | 🟡 MEDIUM   | 1     | 1       | 0       | 0         |
| PRODUCT_DETAIL | 🟡 MEDIUM   | 1     | 1       | 0       | 0         |
| FILTER         | 🟢 LOW      | 1     | 1       | 0       | 0         |
| GUEST          | 🟢 LOW      | 1     | 1       | 0       | 0         |
```

---

## Architectural Decisions

| Decision | Rationale |
|---|---|
| **Scenario IDs are immutable** | SC-001 always maps to the same requirement. Renumbering breaks traceability history. Deprecated scenarios stay in the catalog forever for audit and trend analysis. |
| **`test_powerapps.py` is auto-generated** | The file is overwritten on every pipeline run. Editing it manually creates drift between requirements and tests — the entire point of the pipeline is to eliminate that drift. |
| **No LLM for test generation** | The pipeline is intentionally deterministic. Kane AI is a specialized browser automation agent that exports the Playwright code it actually executed. LLMs would introduce non-determinism and token cost into a step that has a better tool. |
| **Both Kane AND Playwright must pass** | Kane verifies the requirement is observable on the live site (functional). Playwright verifies it remains observable across browsers and builds (regression). A requirement passing only one is incomplete evidence. |
| **Incremental execution by default** | Only new and updated scenarios run on each push. This keeps the feedback loop fast. `FULL_RUN=true` is available for full regression on demand. |
| **Status derived from tasks when API fails** | The HyperExecute job status API (via MCP) can be temporarily unreachable. Rather than reporting `"unknown"`, the pipeline derives the status from individual task results — if all 14 tasks passed, the job status is `PASSED`. This makes reporting reliable regardless of API availability. |
| **Multi-pattern job ID extraction** | HyperExecute CLI output format varies across CLI versions. Using four regex patterns ensures job ID extraction is resilient to format changes without requiring a CLI version pin. |

---

## Roadmap

| Capability | Description |
|---|---|
| **Self-healing locators** | When a locator fails, automatically suggest an updated selector using LambdaTest AI |
| **AI risk scoring** | Score requirements by failure probability based on historical run data |
| **Visual regression** | Add screenshot comparison via LambdaTest Smart UI to the regression stage |
| **API test orchestration** | Extend Kane AI verification to API-level acceptance criteria alongside UI tests |
| **Autonomous flaky remediation** | Detect flaky tests, auto-add retry logic or locator improvements via CI |
| **Accessibility analysis** | Integrate axe-core or LambdaTest Accessibility to surface a11y violations per requirement |
| **Cross-repo traceability** | Link acceptance criteria to GitHub Issues or Jira tickets in the traceability matrix |
| **Progressive coverage scoring** | Track coverage score across pipeline runs to detect coverage regression over time |

---

## License

MIT — see [LICENSE](./LICENSE).

Built with [Kane AI](https://lambdatest.com/kane-ai), [HyperExecute](https://lambdatest.com/hyperexecute), and [Claude Code](https://claude.ai/code).
