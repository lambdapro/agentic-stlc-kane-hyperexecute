# Agentic STLC — Kane AI + HyperExecute

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Pipeline Status](https://github.com/lambdapro/agentic-stlc/actions/workflows/agentic-stlc.yml/badge.svg)](https://github.com/lambdapro/agentic-stlc/actions/workflows/agentic-stlc.yml)

> **Open source under the MIT License.** Fork it, adapt it, ship it.

An end-to-end **Agentic Software Testing Lifecycle (STLC)** where plain-English requirements drive every stage of QA — from requirement analysis to parallel cloud execution and a final release verdict. Kane AI CLI analyzes and verifies requirements against the live site; Selenium WebDriver tests are generated automatically and executed at scale on LambdaTest Grid via HyperExecute.

---

## How the Agentic STLC works — 7 steps

> Commit your requirements. Everything else is automatic.

**Step 1 — Commit requirements and trigger the pipeline**
Edit `requirements/search.txt` in plain English, then `git push`. GitHub Actions detects the change and starts the pipeline immediately — no manual trigger needed.

**Step 2 — Kane AI CLI verifies each acceptance criterion**
`ci/analyze_requirements.py` runs `kane-cli run` on each criterion against the live site. Kane AI drives a real browser, verifies the behaviour is achievable, and records a pass/fail result with a session link per criterion.

**Step 3 — Scenario pool is synchronized**
`ci/manage_scenarios.py` diffs the verified requirements against the existing `scenarios/scenarios.json`. New requirements get new scenario records. Changed requirements update their scenario. Requirements that no longer exist are deprecated. Nothing is deleted — the full history is preserved.

**Step 4 — Selenium automation scripts are generated**
`ci/generate_tests_from_scenarios.py` reads the scenario pool and writes a pytest test file (`tests/selenium/test_products.py`). Each scenario becomes one test function with site-specific Selenium actions derived from its steps and URL.

**Step 5 — Hub address and capabilities are injected**
`tests/selenium/conftest.py` provides a `driver` fixture that connects every test to the LambdaTest Selenium Grid (`hub.lambdatest.com/wd/hub`) with the correct capabilities — platform, browser, video recording, network logs — so no test file contains credentials or infrastructure details.

**Step 6 — HyperExecute CLI triggers the suite in parallel**
The CI job downloads the HyperExecute CLI and submits the selected tests. HyperExecute fans them out across multiple cloud VMs simultaneously. Each VM runs one pytest node, opens one real browser session on LambdaTest Grid, and uploads its artifacts on completion.

**Step 7 — Pipeline reports results for every phase with links**
`ci/build_traceability.py` maps every result back to its requirement. `ci/release_recommendation.py` emits a GREEN / YELLOW / RED verdict. `ci/write_github_summary.py` writes a single GitHub Actions summary covering all 7 stages — with clickable links to the HyperExecute job, per-test LambdaTest Automate session videos, and Kane AI verification sessions.

---

## 🚀 Core Architecture

| Tool | Role in the pipeline |
|---|---|
| **Kane CLI** (`@testmuai/kane-cli`) | AI browser agent — verifies each acceptance criterion against the live site in Stage 1; not used during test execution |
| **Selenium WebDriver** | Test executor — each generated test drives a real browser on LambdaTest Grid via `webdriver.Remote` |
| **HyperExecute CLI** | Cloud parallel test runner — fans out pytest Selenium tests across multiple VMs simultaneously |
| **pytest** | Test orchestration framework — runs Selenium tests, captures pass/fail per node, uploads artifacts |
| **Python CI Scripts** | Stage orchestrators — synchronize requirements, scenarios, generate test code, and build reports |

---

## 🛠️ How It Works

**Edit your requirements, commit, push.** That's it.

```bash
# 1. Add/edit requirements in plain English
vim requirements/search.txt

# 2. Commit and push
git add requirements/
git commit -m "feat: add new product search requirement"
git push
```

GitHub Actions picks up the push and runs the full pipeline:

```
Stage 1: Analyze   → Kane AI verifies each acceptance criterion on the live site
Stage 2: Manage    → Diffs scenarios.json, adds new, updates changed, deprecates removed
Stage 3: Generate  → Writes Selenium WebDriver pytest tests for every new/changed scenario
Stage 4: Execute   → HyperExecute fans out tests; each VM opens a real browser on LambdaTest Grid
Stage 5: Report    → Traceability matrix + GREEN / YELLOW / RED release recommendation
```

No human writes a single test. No one maps a requirement to code. The pipeline does it all.

---

## Why this architecture?

| Problem | Solution |
|---|---|
| LLMs burn tokens on repetitive UI clicks | **Kane AI** is a specialized testing agent — no wasted reasoning |
| One CI runner is too slow for 50+ tests | **HyperExecute** fans out to 4–1000 parallel VMs |
| Tests drift from requirements | **Scenarios and tests are regenerated** every time requirements change |
| QA verdict is manual and subjective | **Release recommendation** is generated from actual test data |
| Brittle test maintenance burden | **Tests are regenerated** from scenarios on every requirements change |

---

## Pipeline Automation

The `.github/workflows/agentic-stlc.yml` workflow executes the following Python-driven stages:

1. **Stage 1 - Analyze Requirements**: `ci/analyze_requirements.py` runs `kane-cli run` against the live site to verify each acceptance criterion and records a session link per criterion.
2. **Stage 2 - Manage Scenarios**: `ci/manage_scenarios.py` synchronizes the scenario catalog — new requirements produce new scenarios, changed requirements mark their scenario as updated, removed requirements are deprecated.
3. **Stage 3 - Generate Tests**: `ci/generate_tests_from_scenarios.py` generates Selenium WebDriver pytest tests — one function per scenario using site-specific locators and WebDriverWait assertions.
4. **Stage 4 - Execution**: Selected tests are submitted to **HyperExecute**; each VM runs `pytest "$test"` which connects to LambdaTest Selenium Grid via the `driver` fixture in `conftest.py`.
5. **Stage 5 - Reporting**: Requirement traceability matrix links every result to its acceptance criterion; a GREEN / YELLOW / RED release recommendation is generated from actual test data.

---

## Repository structure

```
.
├── PIPELINE.md                              # Natural language stage instructions
├── CLAUDE.md                                # Claude Code project config
├── LICENSE                                  # MIT License
├── hyperexecute.yaml                        # HyperExecute cloud execution config
├── requirements.txt                         # Python dependencies
│
├── requirements/
│   └── search.txt                           # INPUT: plain-English requirements
│
├── scenarios/
│   └── scenarios.json                       # Managed test scenarios (auto-updated)
│
├── kane/
│   └── objectives.json                      # Kane CLI objectives per scenario
│
├── ci/                                      # CI stage scripts
│   ├── analyze_requirements.py
│   ├── manage_scenarios.py
│   ├── generate_tests_from_scenarios.py
│   ├── select_tests.py
│   ├── build_traceability.py
│   ├── release_recommendation.py
│   ├── analyze_hyperexecute_failures.py
│   ├── run_pytest_node.py
│   └── write_github_summary.py
│
├── tests/selenium/
│   ├── conftest.py                          # LambdaTest hub driver fixture + marker registration
│   └── test_products.py                     # Selenium WebDriver tests (auto-generated)
│
├── reports/                                 # Runtime output — gitignored
│   ├── traceability_matrix.md
│   └── release_recommendation.md
│
└── .github/workflows/
    └── agentic-stlc.yml                     # Agentic STLC Pipeline
```

---

## Prerequisites

| Tool | Required for | Install |
|---|---|---|
| Node.js 18+ | Kane CLI (Stage 1) | [nodejs.org](https://nodejs.org) |
| Python 3.11+ | CI scripts + pytest | [python.org](https://python.org) |
| Kane CLI | Stage 1 requirement analysis | `npm install -g @testmuai/kane-cli` |
| HyperExecute CLI | Cloud parallel execution | Downloaded automatically by CI |
| LambdaTest account | Selenium Grid + HyperExecute | [lambdatest.com](https://www.lambdatest.com) |

---

## Setup

### 1. Clone and install

```bash
git clone https://github.com/lambdapro/agentic-stlc.git
cd agentic-stlc

npm install -g @testmuai/kane-cli
pip install -r requirements.txt
```

### 2. Set credentials

```bash
export LT_USERNAME=your_lambdatest_username
export LT_ACCESS_KEY=your_lambdatest_access_key
```

| Credential | Where to get it |
|---|---|
| `LT_USERNAME` | [LambdaTest Dashboard > Settings > Keys](https://accounts.lambdatest.com/security) |
| `LT_ACCESS_KEY` | Same page |

### 3. Add GitHub secrets

In your fork: **Settings > Secrets and variables > Actions > New repository secret**

| Secret name | Value |
|---|---|
| `LT_USERNAME` | Your LambdaTest username |
| `LT_ACCESS_KEY` | Your LambdaTest access key |

---

## GitHub Actions — automatic trigger

Push any change to `requirements/search.txt` and the full 5-stage pipeline runs automatically.

```bash
vim requirements/search.txt     # add or edit a requirement
git add requirements/search.txt
git commit -m "feat: add new acceptance criterion"
git push
```

| Workflow | Trigger | Description |
|---|---|---|
| **Agentic STLC Pipeline** | Push to `requirements/**` or `scenarios/**` | Automated STLC orchestration using Kane AI |

Watch it run: **GitHub > Actions**

### Manual trigger

Go to **Actions > Pure CI Pipeline > Run workflow**. Set `full_run` to `true` to run all scenarios (not just changed ones).

---

## Running locally

### Full pipeline

```bash
# Run each stage — credentials are passed inline, no kane-cli login needed
python ci/analyze_requirements.py
python ci/manage_scenarios.py
python ci/generate_tests_from_scenarios.py
python ci/select_tests.py
```

Then run on HyperExecute:

```bash
# Linux / macOS
curl -O https://downloads.lambdatest.com/hyperexecute/linux/hyperexecute
chmod +x hyperexecute
./hyperexecute --user $LT_USERNAME --key $LT_ACCESS_KEY --config hyperexecute.yaml

# Windows PowerShell
Invoke-WebRequest -Uri https://downloads.lambdatest.com/hyperexecute/windows/hyperexecute.exe -OutFile hyperexecute.exe
./hyperexecute.exe --user $LT_USERNAME --key $LT_ACCESS_KEY --config hyperexecute.yaml
```

Then generate reports:

```bash
python ci/build_traceability.py
python ci/release_recommendation.py
cat reports/release_recommendation.md
```

### Run a single Selenium test

```bash
# Set credentials first
export LT_USERNAME=your_username
export LT_ACCESS_KEY=your_access_key

# Single test — opens a real Chrome session on LambdaTest Grid
PYTHONPATH=. pytest "tests/selenium/test_products.py::test_sc_001_navigate_to_products_and_view_list" -v -s

# All tests
PYTHONPATH=. pytest tests/selenium/test_products.py -v -s
```

After each test the conftest fixture writes a session result and prints the LambdaTest Automate link:

```
PASSED  tests/selenium/test_products.py::test_sc_001_navigate_to_products_and_view_list

Session: https://automation.lambdatest.com/test?testID=...
```

---

## Kane CLI — verify any requirement manually (Stage 1)

```bash
# Verify a requirement directly — pass credentials inline, never use kane-cli login in scripts
kane-cli run \
  "Navigate to the product section and verify a list of available products is displayed" \
  --url https://ecommerce-playground.lambdatest.io/ \
  --username "$LT_USERNAME" \
  --access-key "$LT_ACCESS_KEY" \
  --agent --headless --timeout 120 --max-steps 15

# Exit codes: 0=passed, 1=failed, 2=error, 3=timeout
# Parse result
kane-cli run "..." --username "$LT_USERNAME" --access-key "$LT_ACCESS_KEY" \
  --agent --headless 2>/dev/null | tail -1 | jq '{status, one_liner, duration}'

# Run all Kane objectives in parallel
RESULTS_DIR=$(mktemp -d)
for obj in $(jq -r '.[] | @base64' kane/objectives.json); do
  data=$(echo "$obj" | base64 --decode)
  id=$(echo "$data" | jq -r '.scenario_id')
  kane-cli run \
    "$(echo "$data" | jq -r '.objective')" \
    --url "$(echo "$data" | jq -r '.url')" \
    --agent --headless --timeout "$(echo "$data" | jq -r '.timeout')" \
    > "$RESULTS_DIR/$id.ndjson" 2>&1 &
done
wait
for f in "$RESULTS_DIR"/*.ndjson; do
  id=$(basename "$f" .ndjson)
  result=$(tail -1 "$f")
  echo "$id | $(echo "$result" | jq -r '.status') | $(echo "$result" | jq -r '.one_liner')"
done
```

---

## Model Context Protocol (MCP)

Allow Claude to query LambdaTest directly from the chat interface — list tests, check run status, pull logs.

Add to `claude_desktop_config.json` or your MCP settings:

```json
{
  "mcpServers": {
    "mcp-lambdatest-stdio": {
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

---

## Adapting to other CI/CD tools

Each stage is a single portable command. Copy it into any CI tool:

### GitLab CI

```yaml
stages: [analyze, scenarios, tests, execute, report]

analyze-requirements:
  stage: analyze
  image: node:22
  script:
    - npm install -g @testmuai/kane-cli
    - kane-cli login --username $LT_USERNAME --access-key $LT_ACCESS_KEY
    - pip install -r requirements.txt
    - python ci/analyze_requirements.py
  artifacts:
    paths: [requirements/analyzed_requirements.json]
  variables:
    LT_USERNAME: $LT_USERNAME
    LT_ACCESS_KEY: $LT_ACCESS_KEY

manage-scenarios:
  stage: scenarios
  image: python:3.11
  script:
    - pip install -r requirements.txt
    - python ci/manage_scenarios.py
  artifacts:
    paths: [scenarios/scenarios.json]
```

### Jenkins (Declarative Pipeline)

```groovy
pipeline {
    agent any
    environment {
        LT_USERNAME   = credentials('lt-username')
        LT_ACCESS_KEY = credentials('lt-access-key')
    }
    stages {
        stage('Analyze')  { steps { sh 'python ci/analyze_requirements.py' } }
        stage('Manage')   { steps { sh 'python ci/manage_scenarios.py' } }
        stage('Generate') { steps { sh 'python ci/generate_tests_from_scenarios.py' } }
        stage('Execute')  {
            steps {
                sh 'curl -O https://downloads.lambdatest.com/hyperexecute/linux/hyperexecute && chmod +x hyperexecute'
                sh './hyperexecute --user $LT_USERNAME --key $LT_ACCESS_KEY --config hyperexecute.yaml'
            }
        }
        stage('Report') {
            steps {
                sh 'python ci/build_traceability.py'
                sh 'python ci/release_recommendation.py'
            }
        }
    }
    post { always { archiveArtifacts artifacts: 'reports/**', allowEmptyArchive: true } }
}
```

### Bitbucket Pipelines

```yaml
pipelines:
  default:
    - step:
        name: Analyze + Manage + Generate
        image: node:22
        script:
          - npm install -g @testmuai/kane-cli
          - pip install -r requirements.txt
          - python ci/analyze_requirements.py
          - python ci/manage_scenarios.py
          - python ci/generate_tests_from_scenarios.py
    - step:
        name: Execute on HyperExecute
        script:
          - curl -O https://downloads.lambdatest.com/hyperexecute/linux/hyperexecute && chmod +x hyperexecute
          - ./hyperexecute --user $LT_USERNAME --key $LT_ACCESS_KEY --config hyperexecute.yaml
```

---

## Traceability matrix (auto-generated)

`reports/traceability_matrix.md` maps every requirement to its end-to-end result:

| Requirement | Scenario | Test Case | Kane AI Result | Status |
|---|---|---|---|---|
| Navigate to products section and view list | SC-001 | TC-001 | Passed | Green |
| Use filters to refine product results | SC-002 | TC-002 | Passed | Green |
| Click a product to view details | SC-003 | TC-003 | Passed | Green |
| View highlights without login | SC-004 | TC-004 | Passed | Green |
| Relevant results for selected filter | SC-005 | TC-005 | Failed | Yellow |

`reports/release_recommendation.md` gives the final verdict:

```
VERDICT: YELLOW — 4/5 requirements fully verified. SC-005 requires investigation
before release. All other acceptance criteria confirmed on the live site.
```

---

## Scenario and test mapping

| Scenario | Test function | Acceptance criterion |
|---|---|---|
| SC-001 | `test_sc_001_navigate_to_products_and_view_list` | Navigate and view product list |
| SC-002 | `test_sc_002_filter_products_by_category` | Filter products by category |
| SC-003 | `test_sc_003_click_product_view_details` | Click product to view details |
| SC-004 | `test_sc_004_product_highlights_visible_without_login` | Highlights visible without login |
| SC-005 | `test_sc_005_relevant_results_for_selected_filter` | Relevant results per filter |

---

## Adding new requirements

1. Edit `requirements/search.txt` — add new user stories or acceptance criteria in plain English
2. Commit and push:

```bash
git add requirements/search.txt
git commit -m "feat: add requirement for product comparison"
git push
```

GitHub Actions automatically runs all 5 stages. New scenarios and Selenium tests are generated with no manual scripting.

To run just the affected stages locally:

```bash
python ci/analyze_requirements.py
python ci/manage_scenarios.py
python ci/generate_tests_from_scenarios.py
```

---

## License

MIT — see [LICENSE](./LICENSE).

Built with [Kane AI](https://lambdatest.com/kane-ai), [HyperExecute](https://lambdatest.com/hyperexecute), and [Claude Code](https://claude.ai/code).
