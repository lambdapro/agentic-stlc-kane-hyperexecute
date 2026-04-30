# Agentic STLC Pipeline (Kane AI)

This file defines the stages of the Agentic STLC pipeline. The pipeline uses **Kane AI CLI** to verify requirements and discover site structure, while Python scripts orchestrate the synchronization between requirements, scenarios, and test code.

---

## Stage: ANALYZE_REQUIREMENTS

**Goal:** Parse requirements and confirm each acceptance criterion is observable on the live site using Kane AI.

Executed by: `python ci/analyze_requirements.py`

---

## Stage: MANAGE_SCENARIOS

**Goal:** Synchronise scenarios.json with the analyzed requirements — update changed, add new, deprecate removed.

Executed by: `python ci/manage_scenarios.py`

Instructions:
1. Load `requirements/analyzed_requirements.json`
2. Load `scenarios/scenarios.json` (treat as empty array if file is missing or empty)
3. For each analyzed requirement:
   a. Check if a scenario exists with matching `requirement_id`
   b. If **exists and description unchanged**: leave as-is, status stays "active"
   c. If **exists but description changed**: update `title`, `steps`, `expected_result`,
      `kane_objective`; set `status` to "updated"; update `last_verified`
   d. If **no matching scenario**: create a new scenario entry with status "new"
4. For any scenario whose `requirement_id` is no longer in analyzed_requirements: set status "deprecated"
5. New scenario schema:
   ```json
   {
     "id": "SC-001",
     "requirement_id": "AC-001",
     "title": "<short descriptive title>",
     "steps": [
       "Navigate to ecommerce-playground.lambdatest.io",
      "Click on Products navigation link",
      "Verify product listing section appears with multiple tiles"
     ],
     "expected_result": "<what success looks like>",
     "status": "new|active|updated|deprecated",
     "kane_objective": "<full plain-English objective for kane-cli run>",
     "kane_url": "https://ecommerce-playground.lambdatest.io/",
     "test_case_id": "TC-001",
     "last_verified": "<ISO date>"
   }
   ```
6. Save updated array to `scenarios/scenarios.json`
7. Print summary: N active, N updated, N new, N deprecated

---

## Stage: GENERATE_TESTS

**Goal:** Generate or update Selenium Python test cases for all new/updated scenarios, using Kane AI as the scripting agent for discovery.

Executed by: `python ci/generate_tests_from_scenarios.py`

Instructions:
1. Load `scenarios/scenarios.json`
2. Filter scenarios where `status` is "new" or "updated"
3. Load existing `tests/selenium/test_products.py` if it exists
4. **Kane AI Scripting Discovery:** For any new scenario, run `kane-cli run "<kane_objective>"` in `--agent` mode. 
   - Observe the `final_state` and steps taken by Kane to identify the correct selectors and page interactions.
4. For each new/updated scenario:
   a. Check if a test function named `test_<scenario_id_lowercase>` already exists in the file
   b. If exists: update the test body to match the new scenario steps and expected_result
   c. If not exists: append a new test function
5. Each test function must:
   - Be decorated with `@pytest.mark.scenario("<scenario_id>")` and `@pytest.mark.requirement("<requirement_id>")`
   - Use the `driver` fixture from conftest.py
   - Use the `ProductsPage` page object from `tests/selenium/pages/products_page.py`
   - Assert the expected_result condition
   - Have a docstring matching the scenario title
   - **Agent Note:** If selectors were discovered via Kane CLI in step 4, prioritize those over generic templates.
6. Also update `kane/objectives.json` — add/update entries for new/updated scenarios
7. Write the updated test file and objectives file
8. Print: N tests added, N tests updated

---

## Stage: SELECT_TESTS

**Goal:** Decide which tests to run based on what changed, and write an execution manifest.

Executed by: `python ci/select_tests.py`

Instructions:
1. Load `scenarios/scenarios.json`
2. Load `kane/objectives.json`
3. Build a selection list:
   - Always include: scenarios with status "new" or "updated"
   - Include on full run (FULL_RUN env var == "true"): all "active" scenarios
   - Exclude: "deprecated" scenarios
4. Write `reports/test_execution_manifest.json`:
   ```json
   {
     "run_type": "incremental|full",
     "selected_scenarios": ["SC-001", "SC-002"],
     "selected_test_ids": ["TC-001", "TC-002"],
     "excluded_scenarios": ["SC-005"],
     "exclusion_reason": {"SC-005": "deprecated"},
     "generated_at": "<ISO datetime>"
   }
   ```
5. Write `reports/pytest_selection.txt` — one test node ID per line (e.g. `tests/selenium/test_products.py::test_sc_001`)
6. Print the selection summary

---

## Stage: TRACEABILITY_REPORT

**Goal:** Generate a full traceability matrix linking requirements → scenarios → test cases → results.

Executed by: `python ci/build_traceability.py`

Instructions:
1. Load `requirements/analyzed_requirements.json`
2. Load `scenarios/scenarios.json`
3. Load `reports/test_execution_manifest.json`
4. Load pytest HTML/JSON report from `reports/` (parse junit XML if present, else infer from artifacts)
5. Load kane-cli results from `reports/kane_results.json` if present
6. Build the matrix table with columns:
   Requirement ID | Acceptance Criterion | Scenario ID | Test Case ID | Kane AI Result | Kane Link | Selenium Result | Overall
7. Compute:
   - Total requirements covered
   - Pass rate (passed / total executed)
   - Any untested requirements
   - Any failing scenarios
8. Write `reports/traceability_matrix.md` as a full markdown document with the table + summary stats

---

## Stage: RELEASE_RECOMMENDATION

**Goal:** Analyse the traceability matrix and produce a QA release recommendation.

Executed by: `python ci/release_recommendation.py`

Instructions:
1. Load `reports/traceability_matrix.md`
2. Load `scenarios/scenarios.json`
3. Evaluate:
   - GREEN (approve release) if: pass rate >= 90% AND no critical scenarios failing AND all requirements have at least one test
   - YELLOW (conditional approval) if: pass rate >= 75% AND failing tests are non-critical (marked low/medium priority)
   - RED (block release) if: pass rate < 75% OR any critical scenario is failing OR requirements exist with zero test coverage
4. Write `reports/release_recommendation.md`:
   ```markdown
   # QA Release Recommendation

   **Verdict:** ✅ GREEN / ⚠️ YELLOW / ❌ RED

   ## Summary
   - Requirements covered: N/N
   - Scenarios executed: N
   - Pass rate: N% (N passed, N failed)

   ## Failing Scenarios
   | Scenario | Test | Failure Reason | Severity |
   ...

   ## Untested Requirements
   ...

   ## Recommendation
   <Plain English paragraph: should QA sign off or not, and why>
   ```
5. Print the verdict and one-line reason to stdout
