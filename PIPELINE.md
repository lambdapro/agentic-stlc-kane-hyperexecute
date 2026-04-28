# Agentic SDLC Pipeline

This file is the natural language instruction file for the agentic CI/CD pipeline.
Any CI tool invokes a stage by running:
  claude -p "Execute stage: <STAGE_NAME> from PIPELINE.md"

Claude Code reads this file, finds the matching stage, and executes it autonomously
using the tools available (file read/write, kane-cli, bash commands).

---

## Stage: ANALYZE_REQUIREMENTS

**Goal:** Parse requirements and confirm each acceptance criterion is observable on the live site.

Instructions:
1. Read all files inside `requirements/` directory
2. Extract every acceptance criterion as a structured item with fields:
   - id: sequential (AC-001, AC-002, ...)
   - title: short label
   - description: full acceptance criterion text
   - url: https://ecommerce-playground.lambdatest.io/
3. For each acceptance criterion, run a kane-cli verification:
   ```
   kane-cli run "<criterion as objective>" --url https://ecommerce-playground.lambdatest.io/ \
     --username $LT_USERNAME --access-key $LT_ACCESS_KEY \
     --agent --headless --timeout 120 --max-steps 15
   ```
4. Parse the run_end event (last line of stdout) for each kane run:
   - Record status (passed/failed), one_liner, final_state, duration, link
5. Write output to `requirements/analyzed_requirements.json` with schema:
   ```json
   [
     {
       "id": "AC-001",
       "title": "...",
       "description": "...",
       "url": "https://ecommerce-playground.lambdatest.io/",
       "kane_status": "passed|failed",
       "kane_summary": "...",
       "kane_final_state": {},
       "kane_links": ["https://testmu.lambdatest.com/ai/session/..."],
       "last_analyzed": "<ISO date>"
     }
   ]
   ```
6. Print a summary table: requirement ID, title, Kane status, Kane Link

---

## Stage: MANAGE_SCENARIOS

**Goal:** Synchronise scenarios.json with the analyzed requirements — update changed, add new, deprecate removed.

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
       "Click on credit cards navigation link",
       "Verify card listing section appears with multiple tiles"
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

**Goal:** Generate or update Selenium Python test cases for all new/updated scenarios.

Instructions:
1. Load `scenarios/scenarios.json`
2. Filter scenarios where `status` is "new" or "updated"
3. Load existing `tests/selenium/test_credit_cards.py` if it exists
4. For each new/updated scenario:
   a. Check if a test function named `test_<scenario_id_lowercase>` already exists in the file
   b. If exists: update the test body to match the new scenario steps and expected_result
   c. If not exists: append a new test function
5. Each test function must:
   - Be decorated with `@pytest.mark.scenario("<scenario_id>")` and `@pytest.mark.requirement("<requirement_id>")`
   - Use the `driver` fixture from conftest.py
   - Use the `CreditCardsPage` page object from `tests/selenium/pages/credit_cards_page.py`
   - Assert the expected_result condition
   - Have a docstring matching the scenario title
6. Also update `kane/objectives.json` — add/update entries for new/updated scenarios
7. Write the updated test file and objectives file
8. Print: N tests added, N tests updated

---

## Stage: SELECT_TESTS

**Goal:** Decide which tests to run based on what changed, and write an execution manifest.

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
5. Write `reports/pytest_selection.txt` — one test node ID per line (e.g. `tests/selenium/test_credit_cards.py::test_sc_001`)
6. Print the selection summary

---

## Stage: TRACEABILITY_REPORT

**Goal:** Generate a full traceability matrix linking requirements → scenarios → test cases → results.

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

---

## Pure CI Variant (No Claude Code)

This section provides an equivalent, pure CI implementation of the same stages without using `claude -p`. Use these snippets directly in your CI job steps. Secrets must still be provided via CI secret stores (`LT_USERNAME`, `LT_ACCESS_KEY`, `ANTHROPIC_API_KEY` if needed).

Notes:
- Always use `--agent --headless` for `kane-cli` runs in CI.
- Set `--timeout` and `--max-steps` to prevent hanging runs.
- Upload `~/.testmuai/kaneai/sessions/` or `reports/` as artifacts for debugging failures.

---

### ANALYZE_REQUIREMENTS (CI)

Install dependencies, then run a kane-cli check for each requirement/objective. Example (POSIX shell):

```bash
# Install tools
npm install -g @testmuai/kane-cli

# If you keep kane/objectives.json, iterate it; else generate objectives from requirements/*.txt
RESULTS_DIR=$(mktemp -d)
for obj in $(jq -c '.[]' kane/objectives.json); do
   id=$(echo "$obj" | jq -r '.scenario_id')
   objective=$(echo "$obj" | jq -r '.objective')
   kane-cli run "$objective" \
      --url https://ecommerce-playground.lambdatest.io/ \
      --username "$LT_USERNAME" --access-key "$LT_ACCESS_KEY" \
      --agent --headless --timeout 120 --max-steps 15 > "$RESULTS_DIR/${id}.ndjson" 2>&1 &
done
wait

# Parse last line of each ndjson into a JSON array
jq -s 'map(try (fromjson) catch null)' "$RESULTS_DIR"/*.ndjson > requirements/analyzed_requirements.json || true

# Print Summary Table
echo "| ID | Status | Time | Link | Summary |"
echo "|----|--------|------|------|---------|"
for f in "$RESULTS_DIR"/*.ndjson; do
  result=$(tail -1 "$f")
  id=$(basename "$f" .ndjson)
  status=$(echo "$result" | jq -r '.status')
  duration=$(echo "$result" | jq -r '.duration')
  link=$(echo "$result" | jq -r '.link')
  summary=$(echo "$result" | jq -r '.one_liner')
  echo "| $id | $status | ${duration}s | [View]($link) | $summary |"
done

rm -rf "$RESULTS_DIR"
```

### MANAGE_SCENARIOS (CI)

Run a small script to reconcile `requirements/analyzed_requirements.json` → `scenarios/scenarios.json`. Example using Python:

```bash
python3 - <<'PY'
import json, pathlib
req = json.loads(pathlib.Path('requirements/analyzed_requirements.json').read_text())
scn_path = pathlib.Path('scenarios/scenarios.json')
scenarios = json.loads(scn_path.read_text()) if scn_path.exists() else []
# reconciliation logic (same rules as agent version)
... # implement minimal reconciliation or reuse existing project script
PY
```

(You can commit a small helper script `ci/manage_scenarios.py` and call it here.)

### GENERATE_TESTS (CI)

Use a generator script to write/update `tests/selenium/test_credit_cards.py` and `kane/objectives.json`. Example:

```bash
python3 ci/generate_tests_from_scenarios.py --scenarios scenarios/scenarios.json --out tests/selenium/test_credit_cards.py
```

### SELECT_TESTS (CI)

Build `reports/test_execution_manifest.json` and `reports/pytest_selection.txt` (one pytest node per line). Example (bash):

```bash
# Full run or incremental
if [ "$FULL_RUN" = "true" ]; then
   jq -r '.[] | "tests/selenium/test_credit_cards.py::test_\(.id|ascii_downcase)"' scenarios/scenarios.json > reports/pytest_selection.txt
else
   jq -r '.[] | select(.status=="new" or .status=="updated") | "tests/selenium/test_credit_cards.py::test_\(.id|ascii_downcase)"' scenarios/scenarios.json > reports/pytest_selection.txt
fi
```

### EXECUTE TESTS (CI)

Run Selenium tests locally (headless) or on HyperExecute / LambdaTest grid.

Option A — run pytest directly (local runner with Chrome installed):

```bash
pytest -q -k "$(paste -sd ' or ' reports/pytest_selection.txt)" --html=reports/results.html --self-contained-html
```

Option B — run via HyperExecute (parallel cloud):

```bash
# Ensure hyperexecute binary present in runner
./hyperexecute --user $LT_USERNAME --key $LT_ACCESS_KEY --config hyperexecute.yaml
```

(Note: Ensure `hyperexecute.yaml` uses a robust testDiscovery command — avoid `echo -e`. Use a Python here-doc, as shown in the repo's `hyperexecute.yaml`.)

### TRACEABILITY_REPORT (CI)

Collect artifacts and produce the traceability matrix as before. Example:

```bash
python3 ci/build_traceability.py \
   --requirements requirements/analyzed_requirements.json \
   --scenarios scenarios/scenarios.json \
   --pytest-reports reports/ --kane-results reports/kane_results.json \
   --out reports/traceability_matrix.md
```

### RELEASE_RECOMMENDATION (CI)

Run the same analyzer script used by the agent version to compute the GREEN/YELLOW/RED verdict and write `reports/release_recommendation.md`.

```bash
python3 ci/release_recommendation.py --trace reports/traceability_matrix.md --out reports/release_recommendation.md
```

---

Add these steps as separate CI jobs (analyze → manage → generate → select → execute → report) in your CI YAML. Provide secrets via the CI provider's secret manager and upload the `reports/` and `~/.testmuai/kaneai/sessions/` directories as artifacts for debugging.
