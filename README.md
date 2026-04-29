# Agentic SDLC — Kane AI + Claude + Ollama + HyperExecute

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Pure CI Pipeline](https://github.com/lambdapro/agentic-sdlc-kane-claude-hyperexecute/actions/workflows/agentic-sdlc.yml/badge.svg)](https://github.com/lambdapro/agentic-sdlc-kane-claude-hyperexecute/actions/workflows/agentic-sdlc.yml)
[![Agentic Pipeline](https://github.com/lambdapro/agentic-sdlc-kane-claude-hyperexecute/actions/workflows/agentic-sdlc-claude.yml/badge.svg)](https://github.com/lambdapro/agentic-sdlc-kane-claude-hyperexecute/actions/workflows/agentic-sdlc-claude.yml)

> **Open source under the MIT License.** Fork it, adapt it, ship it.

An end-to-end **agentic Software Development Lifecycle** where plain-English requirements drive every stage of QA — from requirement analysis, through scenario management and test generation, to parallel cloud execution and a final release verdict.

---

## Tools at a glance

| Tool | Role in the pipeline |
|---|---|
| **Kane CLI** (`@testmuai/kane-cli`) | AI browser agent — verifies each acceptance criterion against the live site using natural-language objectives |
| **Claude CLI** (`@anthropic-ai/claude-code`) | Agentic orchestrator — reads `PIPELINE.md` and autonomously executes each stage: analyzing requirements, managing scenarios, generating Selenium tests, building traceability reports |
| **Ollama + Gemma** (`gemma4:e4b`) | Local LLM backend for the agentic workflow in CI — Claude CLI routes inference to a locally served Gemma model via `ANTHROPIC_BASE_URL`, so no cloud API key is required |
| **HyperExecute CLI** | Cloud parallel test runner — fans out Selenium tests across multiple VMs simultaneously, cutting execution time from hours to minutes |
| **Selenium + pytest** | Test execution framework — auto-generated test cases run on LambdaTest's cloud grid |

---

## The one step that triggers everything

**Edit `PIPELINE.md` or your requirements, commit, push.** That's it.

The agentic pipeline starts from `PIPELINE.md` — a natural-language instruction file that tells Claude exactly what to do in each stage. Every CI stage calls:

```bash
claude --model gemma-local -p "Execute stage: <STAGE_NAME> from PIPELINE.md"
```

Claude reads `PIPELINE.md`, finds the matching stage, and executes it autonomously — reading files, running `kane-cli`, writing test code, building reports. To change how any stage behaves, **edit `PIPELINE.md`**, not the CI YAML.

```bash
# 1. Describe new requirements in plain English
vim requirements/search.txt

# 2. Or update stage instructions to change pipeline behavior
vim PIPELINE.md

# 3. Commit and push — GitHub Actions runs all stages automatically
git add requirements/ PIPELINE.md
git commit -m "feat: add requirement for product detail navigation"
git push
```

GitHub Actions picks up the push and runs the full pipeline:

```
Stage 1: Analyze   → Kane AI browses the live site, verifies each acceptance criterion
Stage 2: Manage    → Diffs scenarios.json, adds new, updates changed, deprecates removed
Stage 3: Generate  → Writes Selenium Python test cases for every new/changed scenario
Stage 4: Execute   → HyperExecute runs selected tests in parallel across cloud VMs
Stage 5: Report    → Traceability matrix + GREEN / YELLOW / RED release recommendation
```

No human writes a single test. No one maps a requirement to code. The pipeline does it all.

---

## Why this architecture?

| Problem | Solution |
|---|---|
| LLMs burn tokens on repetitive UI clicks | **Kane AI** is a specialized testing agent — no wasted reasoning |
| One CI runner is too slow for 50+ tests | **HyperExecute** fans out to 4–1000 parallel VMs |
| Tests drift from requirements | **Scenarios are regenerated** every time requirements change |
| QA verdict is manual and subjective | **Release recommendation** is generated from actual test data |

---

## Two execution modes

This repo supports both approaches. Choose based on your team's tooling:

### Mode A — Agentic (Claude + Ollama/Gemma orchestrates everything)

Claude CLI reads `PIPELINE.md` and executes each stage autonomously. In CI, inference is served locally by **Ollama running `gemma4:e4b`** — no cloud API key required. Claude routes to it via `ANTHROPIC_BASE_URL=http://localhost:11434/v1`.

**How it works in CI:**

```yaml
# Each job installs Ollama, pulls the model, then runs Claude against it
- name: Install Ollama
  run: curl -fsSL https://ollama.com/install.sh | sh && ollama serve &

- name: Pull and Configure Gemma Model
  run: |
    ollama pull gemma4:e4b
    echo "FROM gemma4:e4b\nPARAMETER num_ctx 128000" | ollama create gemma-local -f -

- name: Execute stage via Claude Agent
  env:
    ANTHROPIC_BASE_URL: http://localhost:11434/v1
    ANTHROPIC_API_KEY: ollama
  run: claude --dangerously-skip-permissions --model gemma-local -p \
         "Execute stage: ANALYZE_REQUIREMENTS from PIPELINE.md"
```

**Locally (with Anthropic API key):**

```bash
claude -p "Execute stage: ANALYZE_REQUIREMENTS from PIPELINE.md"
claude -p "Execute stage: MANAGE_SCENARIOS from PIPELINE.md"
claude -p "Execute stage: GENERATE_TESTS from PIPELINE.md"
claude -p "Execute stage: SELECT_TESTS from PIPELINE.md"
claude -p "Execute stage: TRACEABILITY_REPORT from PIPELINE.md"
claude -p "Execute stage: RELEASE_RECOMMENDATION from PIPELINE.md"
```

The same `claude -p "Execute stage: X from PIPELINE.md"` command works identically in any CI tool — GitHub Actions, GitLab CI, Jenkins, Bitbucket. Only the secret injection and artifact syntax differ.

### Mode B — Pure CI (Python scripts, no Claude needed)

The `ci/` directory contains deterministic Python scripts that run the same stages without any LLM. Requires only `LT_USERNAME` and `LT_ACCESS_KEY`.

```bash
python ci/analyze_requirements.py       # Stage 1: runs Kane CLI against requirements/search.txt
python ci/manage_scenarios.py           # Stage 2: diffs and updates scenarios/scenarios.json
python ci/generate_tests_from_scenarios.py  # Stage 3: writes tests/selenium/test_products.py
python ci/select_tests.py               # Stage 4: writes reports/pytest_selection.txt
python ci/build_traceability.py         # Stage 5a: generates reports/traceability_matrix.md
python ci/release_recommendation.py    # Stage 5b: generates reports/release_recommendation.md
```

The checked-in GitHub Actions workflow at [`.github/workflows/agentic-sdlc.yml`](.github/workflows/agentic-sdlc.yml) uses **Mode B** — no `ANTHROPIC_API_KEY` required.

---

## Pipeline architecture

```
requirements/search.txt  (plain English user story)
        |
        v
[Stage 1: ANALYZE] ci/analyze_requirements.py
  Kane AI browses live site, confirms each AC is observable
  Output: requirements/analyzed_requirements.json
        |
        v
[Stage 2: MANAGE] ci/manage_scenarios.py
  Diffs scenarios.json — updates changed, adds new, deprecates removed
  Output: scenarios/scenarios.json
        |
        v
[Stage 3: GENERATE] ci/generate_tests_from_scenarios.py
  Writes Selenium Python tests for every new or changed scenario
  Output: tests/selenium/test_products.py
        |
        v
[Stage 4: SELECT + EXECUTE] ci/select_tests.py + HyperExecute
  Selects tests to run, submits to HyperExecute (4 parallel VMs)
  Output: reports/junit/*.xml  reports/html/*.html
        |
        v
[Stage 5: REPORT] ci/build_traceability.py + ci/release_recommendation.py
  Requirement -> Scenario -> Test -> Result matrix
  GREEN / YELLOW / RED release verdict
  Output: reports/traceability_matrix.md  reports/release_recommendation.md
```

---

## Repository structure

```
.
├── PIPELINE.md                              # Natural language stage instructions for Claude
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
├── ci/                                      # Pure CI stage scripts (no LLM needed)
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
│   ├── conftest.py                          # pytest fixtures + LambdaTest WebDriver
│   ├── pages/
│   │   └── products_page.py                 # Page Object Model
│   └── test_products.py                     # Selenium test cases (auto-generated)
│
├── reports/                                 # Runtime output — gitignored
│   ├── traceability_matrix.md
│   └── release_recommendation.md
│
└── .github/workflows/
    ├── agentic-sdlc.yml                     # Pure CI pipeline (Python scripts, no LLM in CI)
    └── agentic-sdlc-claude.yml              # Agentic pipeline (Claude CLI + Ollama/Gemma)
```

---

## Prerequisites

| Tool | Required for | Install |
|---|---|---|
| Node.js 18+ | Kane CLI + Claude CLI | [nodejs.org](https://nodejs.org) |
| Python 3.11+ | CI scripts + Selenium | [python.org](https://python.org) |
| Kane CLI | Requirement verification (all modes) | `npm install -g @testmuai/kane-cli` |
| Claude CLI | Mode A (agentic) only | `npm install -g @anthropic-ai/claude-code` |
| Ollama | Mode A in CI (local LLM) | `curl -fsSL https://ollama.com/install.sh \| sh` |
| Gemma 4 (`gemma4:e4b`) | Mode A in CI (model) | `ollama pull gemma4:e4b` (after Ollama) |
| HyperExecute CLI | Cloud parallel test execution | Downloaded automatically by CI |
| Google Chrome | Local Selenium runs | [google.com/chrome](https://www.google.com/chrome) |

---

## Setup

### 1. Clone and install

```bash
git clone https://github.com/lambdapro/agentic-sdlc-kane-claude-hyperexecute.git
cd agentic-sdlc-kane-claude-hyperexecute

# Install Kane CLI (required for all modes)
npm install -g @testmuai/kane-cli

# Install Python dependencies
pip install -r requirements.txt

# For agentic mode: install Claude CLI
npm install -g @anthropic-ai/claude-code

# For agentic mode in CI: install Ollama + pull Gemma model
curl -fsSL https://ollama.com/install.sh | sh
ollama serve &
ollama pull gemma4:e4b
printf 'FROM gemma4:e4b\nPARAMETER num_ctx 128000\n' | ollama create gemma-local -f -
```

### 2. Set credentials

```bash
export LT_USERNAME=your_lambdatest_username
export LT_ACCESS_KEY=your_lambdatest_access_key

# For agentic mode locally (uses Anthropic API directly)
export ANTHROPIC_API_KEY=your_anthropic_api_key

# For agentic mode with local Ollama (no Anthropic key needed)
export ANTHROPIC_BASE_URL=http://localhost:11434/v1
export ANTHROPIC_API_KEY=ollama
```

| Credential | Where to get it |
|---|---|
| `LT_USERNAME` | [LambdaTest Dashboard > Settings > Keys](https://accounts.lambdatest.com/security) |
| `LT_ACCESS_KEY` | Same page |
| `ANTHROPIC_API_KEY` | [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys) (not needed with Ollama) |

### 3. Add GitHub secrets

In your fork: **Settings > Secrets and variables > Actions > New repository secret**

| Secret name | Value | Required for |
|---|---|---|
| `LT_USERNAME` | Your LambdaTest username | Both pipelines |
| `LT_ACCESS_KEY` | Your LambdaTest access key | Both pipelines |

`ANTHROPIC_API_KEY` is **not** required — the agentic pipeline uses Ollama + Gemma locally in each CI job.

---

## GitHub Actions — automatic trigger

Push any change to `requirements/search.txt` and the full 5-stage pipeline runs automatically.

```bash
vim requirements/search.txt     # add or edit a requirement
git add requirements/search.txt
git commit -m "feat: add new acceptance criterion"
git push
```

Two pipelines are available:

| Workflow | Trigger | What runs |
|---|---|---|
| **Pure CI Pipeline** | Push to `requirements/**` or `scenarios/**` | Python scripts — fast, deterministic, no LLM in CI |
| **Agentic SDLC** | Push to `requirements/**` or `PIPELINE.md` | Claude CLI + Ollama/Gemma — fully agentic, update `PIPELINE.md` to change behavior |

Watch it run: **GitHub > Actions**

### Manual trigger

Go to **Actions > [pipeline name] > Run workflow**. Set `full_run` to `true` to run all scenarios (not just changed ones).

---

## Running locally

### Full pipeline — Pure CI mode (no Claude needed)

```bash
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

### Full pipeline — Agentic mode (Claude + Ollama/Gemma)

Start Ollama locally first, then run Claude against it:

```bash
# Start local LLM server
ollama serve &
export ANTHROPIC_BASE_URL=http://localhost:11434/v1
export ANTHROPIC_API_KEY=ollama

# Run each stage — Claude reads PIPELINE.md and executes autonomously
claude --model gemma-local -p "Execute stage: ANALYZE_REQUIREMENTS from PIPELINE.md"
claude --model gemma-local -p "Execute stage: MANAGE_SCENARIOS from PIPELINE.md"
claude --model gemma-local -p "Execute stage: GENERATE_TESTS from PIPELINE.md"
claude --model gemma-local -p "Execute stage: SELECT_TESTS from PIPELINE.md"
claude --model gemma-local -p "Execute stage: TRACEABILITY_REPORT from PIPELINE.md"
claude --model gemma-local -p "Execute stage: RELEASE_RECOMMENDATION from PIPELINE.md"
```

Or with Anthropic API directly (no Ollama needed):

```bash
export ANTHROPIC_API_KEY=your_anthropic_api_key
claude -p "Execute stage: ANALYZE_REQUIREMENTS from PIPELINE.md"
# ... same pattern for each stage
```

**To change how a stage behaves, edit `PIPELINE.md`** — not the CI YAML. The YAML just calls `claude -p "Execute stage: X from PIPELINE.md"`; all the intelligence lives in `PIPELINE.md`.

### Selenium only — run tests directly

```bash
# All tests, local headless Chrome
pytest tests/selenium/ -v

# Single test
pytest tests/selenium/test_credit_cards.py::test_sc_001_navigate_to_credit_cards_and_view_list -v

# With HTML report
pytest tests/selenium/ -v --html=reports/results.html --self-contained-html

# On LambdaTest remote grid
LT_USERNAME=your_user LT_ACCESS_KEY=your_key pytest tests/selenium/ -v
```

---

## Kane CLI — verify any requirement manually

```bash
# Verify AC-001: product listing visible
kane-cli run \
  "Navigate to the product section and verify a list of available products is displayed" \
  --url https://ecommerce-playground.lambdatest.io/ \
  --username $LT_USERNAME --access-key $LT_ACCESS_KEY \
  --agent --headless --timeout 120

# Parse result
kane-cli run "..." --agent --headless 2>/dev/null | tail -1 | jq '{status, one_liner, duration}'

# Run all Kane objectives in parallel
RESULTS_DIR=$(mktemp -d)
for obj in $(jq -r '.[] | @base64' kane/objectives.json); do
  data=$(echo "$obj" | base64 --decode)
  id=$(echo "$data" | jq -r '.scenario_id')
  kane-cli run \
    "$(echo "$data" | jq -r '.objective')" \
    --url "$(echo "$data" | jq -r '.url')" \
    --username $LT_USERNAME --access-key $LT_ACCESS_KEY \
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

# Agentic variant — add ANTHROPIC_API_KEY and swap script line:
# script: claude -p "Execute stage: MANAGE_SCENARIOS from PIPELINE.md"
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
        image: python:3.11
        script:
          - pip install -r requirements.txt
          - npm install -g @testmuai/kane-cli
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

| Requirement | Scenario | Test Case | Kane AI | Selenium | Status |
|---|---|---|---|---|---|
| Navigate to credit cards and view list | SC-001 | TC-001 | Passed | Passed | Green |
| Use filters to refine results | SC-002 | TC-002 | Passed | Passed | Green |
| Click card to view details | SC-003 | TC-003 | Failed | Flaky | Yellow |
| View highlights without login | SC-004 | TC-004 | Passed | Passed | Green |
| Relevant results for selected filter | SC-005 | TC-005 | Failed | Pending | Yellow |

`reports/release_recommendation.md` gives the final verdict:

```
VERDICT: YELLOW — 3/5 requirements fully verified. SC-003 and SC-005 require investigation
before release. All other acceptance criteria confirmed on the live site.
```

---

## Scenario and test mapping

| Scenario | Test function | Acceptance criterion |
|---|---|---|
| SC-001 | `test_sc_001_navigate_to_credit_cards_and_view_list` | Navigate and view card list |
| SC-002 | `test_sc_002_filter_cards_by_category` | Filter cards by category |
| SC-003 | `test_sc_003_click_card_view_details` | Click card to view details |
| SC-004 | `test_sc_004_card_highlights_visible_without_login` | Highlights visible without login |
| SC-005 | `test_sc_005_relevant_results_for_selected_filter` | Relevant results per filter |

---

## Adding new requirements

1. Edit `requirements/search.txt` — add new user stories or acceptance criteria in plain English
2. Commit and push:

```bash
git add requirements/search.txt
git commit -m "feat: add requirement for card comparison table"
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

Built with [Kane AI](https://lambdatest.com/kane-ai), [HyperExecute](https://lambdatest.com/hyperexecute), [Claude Code](https://claude.ai/code), and [Ollama](https://ollama.com) running [Gemma](https://ollama.com/library/gemma4).
