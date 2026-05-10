# Agentic STLC — Kane AI + HyperExecute

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Pipeline Status](https://github.com/lambdapro/agentic-stlc/actions/workflows/agentic-stlc.yml/badge.svg)](https://github.com/lambdapro/agentic-stlc/actions/workflows/agentic-stlc.yml)

> **Open source under the MIT License.** Fork it, adapt it, ship it.

An end-to-end **Agentic Software Testing Lifecycle (STLC)** where plain-English requirements drive every stage of QA — from requirement analysis to parallel cloud execution and a final release verdict.

**Kane AI** creates and runs functional test cases, verifying each acceptance criterion against the live app in real browser sessions. **HyperExecute** then executes those same tests as a full Playwright regression suite at scale, fanning them out across parallel cloud VMs simultaneously.

The pipeline targets **Microsoft Teams Power Apps templates** (IssueReporting, Milestones, Bulletins) from the [teams-powerapps-app-templates](https://github.com/microsoft/teams-powerapps-app-templates) repo. Tests authenticate via Microsoft 365 and run against your deployed Power Apps environment.

---

## How the Agentic STLC works — 5 stages

> Commit your requirements. Everything else is automatic.

**Stage 1 — Kane AI analyzes and verifies each acceptance criterion (functional)**
`ci/analyze_requirements.py` runs `kane-cli run` on each acceptance criterion against the live site. Kane AI drives a real browser, confirms the behaviour is observable, and records a pass/fail result with a session link per criterion. These are your **functional test cases** — created and executed entirely by Kane AI with no human scripting.

**Stage 2 — Scenario pool is synchronized**
The orchestrator diffs the verified requirements against `scenarios/scenarios.json`. New requirements produce new scenario records; changed requirements mark their scenario as updated; removed requirements are deprecated. Nothing is deleted — the full history is preserved.

**Stage 3 — Selenium regression tests are generated**
The orchestrator reads the scenario pool and writes a pytest test file (`tests/selenium/test_products.py`). Each scenario becomes one Selenium test function mapped back to its acceptance criterion — ready for regression execution at scale.

**Stage 4 — HyperExecute runs regression at scale**
The CI job downloads the HyperExecute CLI and submits the generated Selenium tests. HyperExecute fans them out across multiple cloud VMs simultaneously. Each VM runs one pytest node, opens a real browser on LambdaTest Grid via `conftest.py`, and uploads its artifacts on completion. This is the **regression at scale** phase — the same functional scenarios Kane AI verified, now stress-tested in parallel across browsers and platforms.

**Stage 5 — Full traceability report with Functional + Regression results**
`ci/build_traceability.py` maps every result back to its requirement, combining Kane AI functional results with HyperExecute regression results in a single traceability matrix. `ci/write_github_summary.py` writes a GitHub Actions summary with clickable links to the HyperExecute job, per-test LambdaTest Automate session videos, and Kane AI verification sessions. A GREEN / YELLOW / RED release verdict is generated from the combined data.

---

## 🚀 Core Architecture

| Tool | Role in the pipeline |
|---|---|
| **Kane AI** (`@testmuai/kane-cli`) | Functional testing — verifies each acceptance criterion against the live Power App, creates functional test cases with real browser sessions, records pass/fail with session links |
| **HyperExecute CLI** | Regression at scale — fans out the generated Playwright tests across parallel cloud VMs so all scenarios run simultaneously, not sequentially |
| **Playwright (Python)** | Regression executor — each generated test drives a real browser on LambdaTest via CDP connection, supporting M365 login and Power Apps canvas UI |
| **pytest + pytest-playwright** | Test orchestration framework — runs Playwright tests, captures pass/fail per node, uploads JUnit + HTML artifacts |
| **Python CI Scripts** | Stage orchestrators — synchronize requirements, scenarios, generate test code, fetch results, and build reports |

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
Stage 1: Kane AI   → Verifies each acceptance criterion (functional) — real browser, session link per criterion
Stage 2: Scenarios → Diffs scenarios.json, adds new, updates changed, deprecates removed
Stage 3: Generate  → Writes Selenium regression tests for every scenario
Stage 4: Regress   → HyperExecute fans out all tests in parallel across cloud VMs
Stage 5: Report    → Traceability matrix combining Kane AI (functional) + HyperExecute (regression) results
                     → GREEN / YELLOW / RED release verdict
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

The `.github/workflows/agentic-stlc.yml` workflow runs two jobs:

**Job 1 — `analyze` (Stage 1):** `ci/analyze_requirements.py` runs `kane-cli run` against the live site for each acceptance criterion. Kane AI drives a real browser session, confirms the criterion is observable, and records pass/fail + a session link. These are the **functional test results**.

**Job 2 — `orchestrate` (Stages 2-5):** `ci/agent.py` runs the remaining stages end-to-end:

1. **Stage 2 - Scenario Sync**: Diffs `scenarios/scenarios.json` against analyzed requirements — new scenarios added, changed ones updated, removed ones deprecated.
2. **Stage 3 - Test Generation**: Generates `tests/selenium/test_products.py` — one pytest function per scenario with site-specific Selenium actions and WebDriverWait assertions.
3. **Stage 4 - Regression at Scale (HyperExecute)**: Submits selected tests to HyperExecute. Tests fan out across parallel cloud VMs; each VM runs one `pytest "$test"` node connected to LambdaTest Selenium Grid via `conftest.py`.
4. **Stage 5 - Traceability + Verdict**: `ci/build_traceability.py` maps Kane AI functional results and HyperExecute regression results to every requirement. `ci/write_github_summary.py` produces the GitHub Actions summary with a combined **Functional + Regression Result** column per requirement and a GREEN / YELLOW / RED release verdict.

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
| Playwright | Regression tests (Stage 4) | `pip install playwright && playwright install chromium` |
| HyperExecute CLI | Cloud parallel execution | Downloaded automatically by CI |
| LambdaTest account | CDP grid + HyperExecute | [lambdatest.com](https://www.lambdatest.com) |
| Microsoft 365 account | Power Apps access | Your org's M365 tenant |
| Deployed Power App | Test target | Deploy from [teams-powerapps-app-templates](https://github.com/microsoft/teams-powerapps-app-templates) |

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
export M365_USERNAME=your_m365_email
export M365_PASSWORD=your_m365_password
export POWERAPPS_URL=https://apps.powerapps.com/play/your-environment-id/your-app-id
```

| Credential | Where to get it |
|---|---|
| `LT_USERNAME` | [LambdaTest Dashboard > Settings > Keys](https://accounts.lambdatest.com/security) |
| `LT_ACCESS_KEY` | Same page |
| `M365_USERNAME` | Your Microsoft 365 account email |
| `M365_PASSWORD` | Your Microsoft 365 account password |
| `POWERAPPS_URL` | Power Apps player URL for your deployed IssueReporting app |

### 3. Add GitHub secrets

In your fork: **Settings > Secrets and variables > Actions > New repository secret**

| Secret name | Value |
|---|---|
| `LT_USERNAME` | Your LambdaTest username |
| `LT_ACCESS_KEY` | Your LambdaTest access key |
| `M365_USERNAME` | Microsoft 365 account email |
| `M365_PASSWORD` | Microsoft 365 account password |
| `POWERAPPS_URL` | Power Apps player URL for the IssueReporting app |

---

## GitHub Actions — automatic trigger

Push any change to `requirements/search.txt` and the full pipeline runs automatically.

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

Go to **Actions > Agentic STLC Pipeline > Run workflow**. Set `full_run` to `true` to run all scenarios (not just changed ones).

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

`reports/traceability_matrix.md` maps every requirement to its end-to-end result, combining Kane AI functional verification with HyperExecute regression execution:

| Requirement | Scenario | Test Case | Kane AI (Functional) | HyperExecute (Regression) | Functional + Regression Result |
|---|---|---|---|---|---|
| Navigate to IssueReporting app and see issues list | SC-001 | TC-001 | ✅ passed | ✅ passed | ✅ passed |
| Create a new issue report | SC-002 | TC-002 | ✅ passed | ✅ passed | ✅ passed |
| View issue details with status and description | SC-003 | TC-003 | ✅ passed | ✅ passed | ✅ passed |
| Filter issues list by status | SC-004 | TC-004 | ✅ passed | ✅ passed | ✅ passed |
| Navigate back from detail view to main list | SC-005 | TC-005 | ✅ passed | ❌ failed | ❌ failed |

`reports/release_recommendation.md` gives the final verdict:

```
VERDICT: YELLOW — 4/5 requirements fully verified. SC-005 requires investigation
before release. All other acceptance criteria confirmed on the live site.
```

---

## Scenario and test mapping

| Scenario | Test function | Acceptance criterion |
|---|---|---|
| SC-001 | `test_sc_001_navigate_to_app_and_see_issues_list` | Navigate to IssueReporting app and see issues list |
| SC-002 | `test_sc_002_create_new_issue_report` | Create a new issue report with title and category |
| SC-003 | `test_sc_003_view_issue_details` | View issue details including status and description |
| SC-004 | `test_sc_004_filter_issues_by_status` | Filter issues by status to see active/resolved items |
| SC-005 | `test_sc_005_navigate_back_from_detail_view` | Navigate back from detail view to main issues list |

---

## Adding new requirements

1. Edit `requirements/search.txt` — add new user stories or acceptance criteria in plain English
2. Commit and push:

```bash
git add requirements/search.txt
git commit -m "feat: add requirement for product comparison"
git push
```

GitHub Actions automatically runs the full pipeline. Kane AI verifies the new criterion (functional), the orchestrator generates the regression test, and HyperExecute runs it at scale — no manual scripting.

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
