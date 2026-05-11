# Requirements Traceability Matrix
## IssueReporting Power App — Agentic STLC Pipeline
## Format: Requirement → AC → KaneAI Test → Playwright Test → HyperExecute Job → Result

---

> **How this file is generated:**
> The pipeline auto-generates this matrix in `reports/traceability_matrix.md` on every run.
> This version is the **template/reference** showing the full intended traceability structure.
> The live version in `reports/` contains actual execution results.

---

## Full Traceability Matrix

| Req ID | Story | Acceptance Criteria | Scenario ID | KaneAI Goal | Playwright Test | HE Job | Kane Result | HE Result | Combined |
|---|---|---|---|---|---|---|---|---|---|
| AC-001 | PP-101 | Navigate to app — issues list visible with records | SC-001 | "Navigate to app — see issues list" | `test_sc_001_navigate_to_app_and_see_issues_list` | HYP-{run} | ✅ PASSED | ✅ PASSED | ✅ GREEN |
| AC-002 | PP-102 | Create issue — record appears after submission | SC-002 | "Create new issue — title, desc, category" | `test_sc_002_create_new_issue_report` | HYP-{run} | ✅ PASSED | ✅ PASSED | ✅ GREEN |
| AC-003 | PP-103 | View details — status, priority, desc displayed | SC-003 | "View issue details — status, priority, desc" | `test_sc_003_view_issue_details` | HYP-{run} | ✅ PASSED | ✅ PASSED | ✅ GREEN |
| AC-004 | PP-104 | Filter by status — only matching items shown | SC-004 | "Filter issues by status — see only matching" | `test_sc_004_filter_issues_by_status` | HYP-{run} | ✅ PASSED | ✅ PASSED | ✅ GREEN |
| AC-005 | PP-105 | Navigate back — issues list re-displays | SC-005 | "Navigate back from detail to list" | `test_sc_005_navigate_back_from_detail_view` | HYP-{run} | ✅ PASSED | ✅ PASSED | ✅ GREEN |
| AC-006 | PP-106 | Edit issue — updated details saved | SC-006 | "Edit submitted issue — verify update saved" | `test_sc_006_edit_submitted_issue_report` | HYP-{run} | ✅ PASSED | ✅ PASSED | ✅ GREEN |
| AC-007 | PP-107 | Search keyword — matching results shown | SC-007 | "Search for issue by keyword — see results" | `test_sc_007_search_existing_issues` | HYP-{run} | ✅ PASSED | ✅ PASSED | ✅ GREEN |
| AC-008 | PP-108 | Empty form submit — validation messages appear | SC-008 | "Submit empty form — see validation messages" | `test_sc_008_validation_handling` | HYP-{run} | ✅ PASSED | ✅ PASSED | ✅ GREEN |
| AC-009 | PP-109 | Grid sort + paginate — records respond correctly | SC-009 | "Sort grid and paginate — records respond" | `test_sc_009_grid_interaction` | HYP-{run} | ✅ PASSED | ✅ PASSED | ✅ GREEN |
| AC-010 | PP-110 | Approver view — pending approvals + actions shown | SC-010 | "Access approver view — see pending + actions" | `test_sc_010_approver_workflow_navigation` | HYP-{run} | ✅ PASSED | ✅ PASSED | ✅ GREEN |

---

## Traceability Chain — How Requirements Become Results

```
requirements/search.txt           (Plain English requirements — human authored)
        │
        │ ci/analyze_requirements.py (Stage 1 — KaneAI verification)
        ▼
requirements/analyzed_requirements.json  (Kane results: status, one_liner, session link)
        │
        │ ci/manage_scenarios.py (Stage 2 — deterministic diff)
        ▼
scenarios/scenarios.json          (SC-001…SC-010 — immutable scenario catalog)
        │
        │ ci/generate_tests_from_scenarios.py (Stage 3 — Playwright test generation)
        ▼
tests/playwright/test_powerapps.py  (Auto-generated — never edit manually)
        │
        │ ci/select_tests.py (Stage 4 — incremental or full selection)
        ▼
reports/pytest_selection.txt      (Test node IDs for HyperExecute)
        │
        │ HyperExecute (Stage 5 — parallel cloud execution)
        ▼
reports/junit.xml                 (Per-test pass/fail results)
        │
        │ ci/build_traceability.py (Stage 7a — join Kane + HE results)
        ▼
reports/traceability_matrix.json  (Full requirement → result mapping)
        │
        │ ci/release_recommendation.py (Stage 7b — GREEN/YELLOW/RED)
        ▼
reports/release_recommendation.md  (Final verdict with reasoning)
        │
        │ ci/write_github_summary.py (Stage 7c — GitHub Actions summary)
        ▼
GitHub Actions Step Summary       (Stakeholder-readable report in CI dashboard)
```

---

## Verdict Thresholds

| Pass Rate | Coverage | Verdict | Action |
|---|---|---|---|
| ≥ 90% | Full | ✅ GREEN | Release approved — no action required |
| 75–89% | Partial | ⚠️ YELLOW | Review failing requirements before release decision |
| < 75% | Any | ❌ RED | Release blocked — investigate failing requirements |

---

## What "Both Must Pass" Means

A requirement earns GREEN **only when BOTH** verification signals are green:

| Kane Result | HE Result | Combined Verdict | Meaning |
|---|---|---|---|
| ✅ PASSED | ✅ PASSED | ✅ GREEN | Feature works on live app AND automation is stable |
| ✅ PASSED | ❌ FAILED | ❌ RED | Feature works but automation script is broken — fix the test |
| ❌ FAILED | ✅ PASSED | ❌ RED | Automation passed but feature is broken on live app — real bug |
| ❌ FAILED | ❌ FAILED | ❌ RED | Both layers failed — likely a real regression |

---

## Scenario Lifecycle — Immutable IDs

| Status | Meaning | Action |
|---|---|---|
| `new` | Newly created scenario, not yet run | Runs in next incremental or full pipeline |
| `active` | Scenario exists and requirements unchanged | Runs on full run; skipped on incremental |
| `updated` | Requirement text changed since last run | Runs in next incremental run |
| `deprecated` | Requirement removed from requirements file | Never runs; stays in catalog for audit trail |

**Key rule:** Scenario IDs (SC-001, SC-002, …) are **permanently assigned** and **never reassigned**.
SC-001 always refers to the first IssueReporting scenario, even after SC-001 is deprecated.
This preserves the audit trail and prevents false traceability matches.

---

## Live Report Location

After each pipeline run, the actual traceability results are written to:
- `reports/traceability_matrix.md` — Human-readable markdown (stakeholder report)
- `reports/traceability_matrix.json` — Machine-readable JSON (for downstream tooling)
- GitHub Actions Step Summary — Embedded in the CI run for direct stakeholder access

The pipeline produces this matrix automatically — no manual assembly required.
