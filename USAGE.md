# Agentic STLC Platform — Usage Guide

> **Enterprise-grade autonomous QA orchestration.**  
> Transform plain-English requirements into executed, traced test results — zero manual test writing.

---

## Table of Contents

- [Quick Start](#quick-start)
- [Installation](#installation)
- [CLI Reference](#cli-reference)
- [Configuration](#configuration)
- [Platform Architecture](#platform-architecture)
- [Agent Skills](#agent-skills)
- [Adapters](#adapters)
  - [CI/CD Adapters](#cicd-adapters)
  - [Git Adapters](#git-adapters)
  - [Execution Adapters](#execution-adapters)
- [Pipeline Stages](#pipeline-stages)
- [Quality Gates](#quality-gates)
- [Confidence Analysis](#confidence-analysis)
- [Root Cause Analysis](#root-cause-analysis)
- [Claude Feedback Loop](#claude-feedback-loop)
- [Multi-Repo Support](#multi-repo-support)
- [GitHub Actions Integration](#github-actions-integration)
- [Onboarding a New Project](#onboarding-a-new-project)
- [Troubleshooting](#troubleshooting)
- [Extensibility](#extensibility)
- [Versioning](#versioning)

---

## Quick Start

```bash
# 1. Install
pip install agentic-stlc          # Python package
npm install -g agentic-stlc       # Node.js CLI wrapper (optional)

# 2. Scaffold config in your project
agentic-stlc init

# 3. Edit agentic-stlc.config.yaml — set project.repository and target.url

# 4. Validate your environment
agentic-stlc validate

# 5. Run the full pipeline
agentic-stlc run
```

---

## Installation

### Python (recommended)

```bash
pip install agentic-stlc
# or from source:
pip install -e ".[all]"
```

**Requirements:** Python 3.11+

### Node.js CLI wrapper

```bash
npm install -g agentic-stlc
```

The Node.js package installs the `agentic-stlc` CLI and automatically invokes
the Python backend. Run `agentic-stlc validate` after install to confirm setup.

### From source

```bash
git clone https://github.com/lambdapro/agentic-stlc-kane-hyperexecute
cd agentic-stlc-kane-hyperexecute
pip install -r requirements.txt
```

---

## CLI Reference

### `agentic-stlc run`

Run the full pipeline end-to-end.

```bash
agentic-stlc run [OPTIONS]

Options:
  --repo        URL      Repository URL (overrides config)
  --branch      BRANCH   Git branch (overrides config)
  --requirements FILE    Requirements file path (overrides config)
  --target-url  URL      Application URL under test (overrides config)
  --full                 Run ALL scenarios (default: incremental)
  --stages      IDS      Comma-separated stage IDs: "1,2,2b,3"
  --config, -c  PATH     Path to agentic-stlc.config.yaml

Examples:
  agentic-stlc run
  agentic-stlc run --full
  agentic-stlc run --repo https://github.com/org/app --branch feature-x
  agentic-stlc run --target-url https://staging.myapp.com
  agentic-stlc run --stages 2b,7a,7b   # re-run confidence + reports only
```

### `agentic-stlc analyze`

Run KaneAI requirement analysis only (Stage 1).

```bash
agentic-stlc analyze [--requirements FILE]

Examples:
  agentic-stlc analyze
  agentic-stlc analyze --requirements requirements/cart.txt
```

### `agentic-stlc generate`

Generate Playwright tests from the current scenario pool (Stage 3).

```bash
agentic-stlc generate [--scenarios FILE] [--target-url URL]

Examples:
  agentic-stlc generate
  agentic-stlc generate --target-url https://staging.myapp.com
```

### `agentic-stlc report`

Re-generate reports from existing artifacts without re-running tests.

```bash
agentic-stlc report [--output DIR]
```

### `agentic-stlc status`

Show the latest pipeline results at a glance.

```bash
agentic-stlc status

# Example output:
# 🟢  Verdict: GREEN
#    Pass rate: 92.3%
#
# ✅  Quality gates: 7/9 passed
#    Critical failures: 0 | Warnings: 2
#
#    Confidence distribution:
#    HIGH: 4
#    MEDIUM: 2
#    LOW: 1
```

### `agentic-stlc init`

Scaffold `agentic-stlc.config.yaml` in the current directory.

```bash
agentic-stlc init
```

### `agentic-stlc validate`

Verify that your config is valid and all required tools are installed.

```bash
agentic-stlc validate

# Example output:
# Config validation: PASS
#   ✅ python: found
#   ✅ kane-cli: found
#   ✅ node: found
#   ✅ hyperexecute: found
```

---

## Configuration

All platform behaviour is controlled by `agentic-stlc.config.yaml`.

### Minimal config

```yaml
version: "1.0"
project:
  name: "my-app"
  repository: "https://github.com/org/my-app"
target:
  url: "https://staging.my-app.com"
```

### Full config reference

See [templates/config/agentic-stlc.config.yaml.example](templates/config/agentic-stlc.config.yaml.example)
for a fully-annotated example with all available options.

### Environment variable overrides

Any config key can be overridden at runtime using env vars:

```
ASTLC_<SECTION>_<KEY>=value
```

Examples:
```bash
ASTLC_EXECUTION_CONCURRENCY=10 agentic-stlc run
ASTLC_EXECUTION_MODE=full agentic-stlc run
ASTLC_QUALITY_GATES_MIN_PASS_RATE=90 agentic-stlc run
```

### Supported requirement formats

| Format | Description | Example |
|--------|-------------|---------|
| `acceptance_criteria` | `AC-NNN: description` per line | `AC-001: User can add product to cart` |
| `gherkin` | Given/When/Then Scenario blocks | Standard `.feature` file |
| `plain` | One non-empty line = one requirement | Free-form text |

---

## Platform Architecture

```
agentic-stlc/
├── platform/           # Core engine: config, pipeline, registry, telemetry
├── skills/             # 11 agent skills (reusable, independently testable)
├── adapters/           # 7 integration adapters (GitHub, GitLab, Jenkins, AzureDevOps,
│                       #   HyperExecute, KaneAI, Playwright)
├── cli/                # CLI entry point + command handlers
├── templates/          # Reusable workflow/config/test templates
├── .github/actions/    # Composite GitHub Actions (analyze + orchestrate)
└── ci/                 # Pipeline-specific stage scripts (existing codebase)
```

### Data flow

```
requirements/*.txt
       │
       ▼
[Stage 1] KaneAI Adapter ──► analyzed_requirements.json
                                       │
                                       ▼
                     [Stage 2] ScenarioGenerationSkill ──► scenarios.json
                                       │
                                       ▼
                     [Stage 2b] ConfidenceAnalysisSkill ──► confidence reports
                                       │
                                       ▼
                     [Stage 3] PlaywrightGenerationSkill ──► test_powerapps.py
                                       │
                                       ▼
                     [Stage 4] Test selection ──► pytest_selection.txt
                                       │
                                       ▼
                     [Stage 5] HyperExecuteAdapter ──► parallel cloud execution
                                       │
                                       ▼
                     [Stage 6] ArtifactCollectionSkill ──► api_details.json
                                       │
                                       ▼
                     [Stage 7a] CoverageAnalysisSkill ──► traceability_matrix.json
                     [Stage 7b] RCASkill ──► rca_report.json
                     [Stage 7c] ClaudeFeedbackSkill ──► claude_feedback_context.md
                     [Stage 7d] QualityGates ──► quality_gates.json
                                       │
                                       ▼
                               GitHub Actions Summary
```

---

## Agent Skills

Skills are the core reusable units of the platform. Each skill:
- Is framework-agnostic and repository-agnostic
- Accepts `PlatformConfig` at construction
- Returns a plain `dict` from `run(**inputs)`
- Can be used standalone, in a pipeline, or from the CLI

| Skill | Stage | Description |
|-------|-------|-------------|
| `RequirementParsingSkill` | 1 | Parse requirements files into structured objects |
| `ScenarioGenerationSkill` | 2 | Sync requirements → scenario pool (deterministic diff) |
| `ConfidenceAnalysisSkill` | 2b | Score scenario sufficiency; detect coverage gaps |
| `PlaywrightGenerationSkill` | 3 | Generate Playwright test file from active scenarios |
| `WorkflowTriggerSkill` | — | Trigger CI/CD workflows (adapter-backed) |
| `HyperExecuteMonitoringSkill` | 5 | Submit HE job and poll for completion |
| `ArtifactCollectionSkill` | 6 | Collect, validate, and manifest pipeline artifacts |
| `CoverageAnalysisSkill` | 7a | Map results to requirements; compute coverage |
| `RCASkill` | 7b | Collect failures; identify probable root causes |
| `ClaudeFeedbackSkill` | 7c | Assemble debugging context for AI agent consumption |

### Using a skill programmatically

```python
from platform.config import PlatformConfig
from skills.confidence_analysis import ConfidenceAnalysisSkill

cfg  = PlatformConfig.load()
skill = ConfidenceAnalysisSkill(config=cfg)
result = skill.run()
print(result["confidence_gate_passed"])
```

---

## Adapters

### CI/CD Adapters

| Adapter | Provider | Key env vars |
|---------|----------|--------------|
| `GitHubActionsAdapter` | GitHub Actions | `GITHUB_TOKEN` |
| `GitLabAdapter` | GitLab CI | `GITLAB_TOKEN`, `GITLAB_PROJECT_ID` |
| `JenkinsAdapter` | Jenkins | `JENKINS_URL`, `JENKINS_USER`, `JENKINS_API_TOKEN` |
| `AzureDevOpsAdapter` | Azure Pipelines | `AZURE_DEVOPS_ORG`, `AZURE_DEVOPS_PROJECT`, `AZURE_DEVOPS_PAT` |

#### Triggering a workflow

```python
from adapters.jenkins import JenkinsAdapter

adapter = JenkinsAdapter(
    base_url="https://jenkins.example.com",
    username="ci-bot",
    api_token="my-api-token",
)
run_id = adapter.trigger_workflow("agentic-stlc", "main", {"FULL_RUN": "true"})
status = adapter.get_workflow_status(run_id)
logs   = adapter.get_build_log(status["html_url"])
```

```python
from adapters.azure_devops import AzureDevOpsAdapter

adapter = AzureDevOpsAdapter(org="myorg", project="MyProject")
run_id = adapter.trigger_workflow("agentic-stlc-pipeline", "main", {"FULL_RUN": "true"})
status = adapter.get_workflow_status(run_id)
```

```python
from adapters.gitlab import GitLabAdapter

adapter = GitLabAdapter(project_id="mygroup/myproject")
run_id = adapter.trigger_workflow(None, "main", {"FULL_RUN": "true"})
status = adapter.get_workflow_status(run_id)
logs   = adapter.get_job_trace("12345")
```

### Git Adapters

```python
from adapters.github import GitHubAdapter
from adapters.gitlab import GitLabAdapter

# GitHub
gh = GitHubAdapter(repo="org/repo")
gh.push("product", "feat: add scenario confidence", ["platform/config.py"])
gh.create_pull_request("Add confidence analysis", "...", head="product", base="main")

# GitLab
gl = GitLabAdapter(project_id="org/repo")
gl.clone("https://gitlab.com/org/repo.git", "main", "/tmp/repo")
gl.create_pull_request("Add confidence analysis", "...", head="product", base="main")
```

### Execution Adapters

```python
from adapters.hyperexecute import HyperExecuteAdapter

he = HyperExecuteAdapter()
job_id  = he.submit_job("hyperexecute.yaml", ["tests/playwright/test_powerapps.py::test_sc_001"], {})
results = he.poll_until_complete(job_id, max_wait_s=900)
```

```python
from adapters.kaneai import KaneAIAdapter

kane = KaneAIAdapter(project_id="...", folder_id="...")
result = kane.run_test(
    objective="Verify user can search for 'laptop' and see results",
    target_url="https://ecommerce-playground.lambdatest.io/",
)
print(result["status"], result["session_url"])

# Batch (parallel)
results = kane.run_batch([
    {"objective": "...", "target_url": "...", "requirement_id": "AC-001"},
    {"objective": "...", "target_url": "...", "requirement_id": "AC-002"},
], parallel_workers=5)
```

---

## Pipeline Stages

| Stage | Name | Description | Blocking |
|-------|------|-------------|----------|
| 1 | KANE_ANALYZE | KaneAI functional verification | WARNING |
| 2 | MANAGE_SCENARIOS | Deterministic diff + SC-NNN assignment | CRITICAL |
| 2b | CONFIDENCE_ANALYSIS | Scenario sufficiency scoring | WARNING |
| 3 | GENERATE_TESTS | Playwright test file generation | CRITICAL |
| 4 | SELECT_TESTS | Incremental / full test selection | CRITICAL |
| 5 | HYPEREXECUTE | Cloud parallel execution | CRITICAL |
| 6 | FETCH_RESULTS | Collect HE session results | WARNING |
| 7a | BUILD_TRACEABILITY | Requirement → test → result mapping | WARNING |
| 7b | RELEASE_RECOMMENDATION | GREEN/YELLOW/RED verdict | WARNING |
| 7c | WRITE_SUMMARY | GitHub Actions step summary | WARNING |
| 7d | QUALITY_GATES | Threshold enforcement | CRITICAL |

### Running a subset of stages

```bash
# Re-run confidence analysis + reporting only (fast, no HyperExecute)
agentic-stlc run --stages 2b,7a,7b,7c,7d
```

---

## Quality Gates

Quality gates enforce coverage and quality thresholds. Gates that fail with
`CRITICAL` severity block the pipeline (exit code 1). `WARNING` severity
logs the issue but allows the pipeline to continue.

| Gate | Severity | Default threshold | Description |
|------|----------|-------------------|-------------|
| Minimum requirement coverage | WARNING | 50% | % requirements with full coverage |
| Minimum test pass rate | CRITICAL | 75% | Playwright test pass rate |
| Flaky test threshold | WARNING | 5 | Max flaky requirement count |
| Critical requirements covered | WARNING | 0 uncovered | HIGH-criticality requirements |
| No failing high-risk requirements | CRITICAL | 0 failing | HIGH-risk requirements must not fail |
| Scenario confidence (HIGH criticality) | WARNING | 0 LOW/CRITICAL_GAP | HIGH-crit reqs with LOW confidence |
| Negative test coverage (HIGH criticality) | WARNING | 0 missing | HIGH-crit reqs need negative tests |

### Overriding gate thresholds

```bash
# Via env vars (gate-specific)
GATE_MIN_PASS_RATE=90 agentic-stlc run
GATE_MAX_FLAKY=2 agentic-stlc run
GATE_REQUIRE_CRITICAL=false agentic-stlc run

# Via config
quality_gates:
  min_pass_rate: 90
  max_flaky: 2
```

---

## Confidence Analysis

The platform evaluates whether your scenarios are **sufficient** to validate
each requirement — not just whether tests exist.

### Confidence levels

| Level | Meaning |
|-------|---------|
| `VERY_HIGH` | All key dimensions covered; minor gaps acceptable |
| `HIGH` | Core flow validated; some coverage classes missing |
| `MEDIUM` | Happy path present but important gaps exist |
| `LOW` | Significant gaps; Kane failure or no negative tests |
| `CRITICAL_GAP` | No scenario mapped — zero automated coverage |

### How confidence is scored

Confidence is determined by a deterministic rule table:

```
HIGH criticality requirement:
  Kane:pass + has_negative → HIGH
  Kane:pass + no negative  → MEDIUM
  Kane:fail + any          → LOW

MEDIUM criticality requirement:
  Kane:pass + has_negative → VERY_HIGH
  Kane:pass + no negative  → HIGH
  Kane:fail + has_negative → MEDIUM
  Kane:fail + no negative  → LOW

LOW criticality requirement:
  Kane:pass               → VERY_HIGH
  Kane:fail + has_negative → HIGH
  Kane:fail + no negative  → MEDIUM
```

### Coverage gap reports

For each requirement the confidence engine identifies:
- Missing **negative test** scenarios
- Missing **edge case** scenarios (boundary values, empty states)
- Missing **recovery flow** scenarios
- Missing **mobile/Android** coverage
- Shallow **Playwright body** (generic page-load-only assertion)

Reports are written to `reports/`:
- `scenario-confidence-report.json`
- `requirement-confidence-summary.md`
- `coverage-gap-analysis.json`
- `high-risk-requirements.json`

---

## Root Cause Analysis

The RCA engine (`skills/rca.py`) automatically collects failures from:

1. **JUnit XML** — Playwright failure messages + stack traces
2. **KaneAI results** — `kane_status: failed` + one-liner messages
3. **HyperExecute sessions** — session URL enrichment

Each failure is classified into:

| Category | Likely cause |
|----------|-------------|
| `TIMEOUT` | Element/page did not load within timeout |
| `SELECTOR` | CSS/XPath selector mismatch after UI change |
| `NETWORK` | Target URL unreachable from CI environment |
| `AUTH` | Credential or session handling failure |
| `SERVER` | 5xx from target application |
| `ASSERTION` | Test assertion failed (actual ≠ expected state) |
| `STALE_DOM` | DOM changed between element lookup and interaction |
| `OVERLAY` | Click intercepted by modal/cookie banner |
| `UNKNOWN` | Manual investigation required |

Reports: `reports/rca_report.json`, `reports/rca_summary.md`

---

## Claude Feedback Loop

`ClaudeFeedbackSkill` assembles a complete debugging context document that
you can paste directly into Claude Code or any AI coding assistant.

The context includes:
- Pipeline verdict + pass rate
- All test failures with categories and session links
- Confidence gaps with specific recommendations
- Suggested next actions (fix selectors, add negative tests, etc.)

```bash
# After a pipeline run:
cat reports/claude_feedback_context.md
# → paste into Claude Code for targeted fix suggestions
```

Or programmatically:

```python
from skills.claude_feedback import ClaudeFeedbackSkill
from platform.config import PlatformConfig

skill = ClaudeFeedbackSkill(config=PlatformConfig.load())
result = skill.run()
# result["context_path"] → "reports/claude_feedback_context.md"
```

---

## Multi-Repo Support

### Mono-repo

Organize requirements by component:

```yaml
requirements:
  paths:
    - "requirements/search.txt"
    - "requirements/cart.txt"
    - "requirements/checkout.txt"
    - "requirements/auth.txt"
```

### Multiple test repositories

Run the platform against any repository by passing `--repo`:

```bash
# Frontend app
agentic-stlc run --repo https://github.com/org/frontend --branch main \
                 --requirements my-frontend-requirements.txt

# Backend API
agentic-stlc run --repo https://github.com/org/api --branch main \
                 --requirements my-api-requirements.txt
```

### Shared test repository

Point multiple application repos to a shared test repo:

```yaml
# app-a/agentic-stlc.config.yaml
project:
  repository: "https://github.com/org/shared-tests"
requirements:
  paths: ["requirements/app-a-requirements.txt"]
scenarios:
  path: "scenarios/app-a-scenarios.json"
```

---

## GitHub Actions Integration

### Using composite actions directly

The platform ships two reusable composite actions:

```yaml
# .github/workflows/agentic-stlc.yml
jobs:
  analyze:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: ./.github/actions/analyze
        with:
          lt-username:   ${{ secrets.LT_USERNAME }}
          lt-access-key: ${{ secrets.LT_ACCESS_KEY }}

  orchestrate:
    needs: analyze
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: ./.github/actions/orchestrate
        with:
          lt-username:   ${{ secrets.LT_USERNAME }}
          lt-access-key: ${{ secrets.LT_ACCESS_KEY }}
          full-run:      "true"
```

### Required GitHub Secrets

| Secret | Description |
|--------|-------------|
| `LT_USERNAME` | LambdaTest account username |
| `LT_ACCESS_KEY` | LambdaTest API access key |

### Optional secrets (for non-GitHub CI adapters)

| Secret | Adapter |
|--------|---------|
| `JENKINS_API_TOKEN` | JenkinsAdapter |
| `AZURE_DEVOPS_PAT` | AzureDevOpsAdapter |
| `GITLAB_TOKEN` | GitLabAdapter |

---

## Onboarding a New Project

Follow these 10 steps to onboard any web application:

1. **Install the platform**
   ```bash
   pip install agentic-stlc
   ```

2. **Scaffold config**
   ```bash
   cd /path/to/your/project
   agentic-stlc init
   ```

3. **Edit `agentic-stlc.config.yaml`**
   - Set `project.name`, `project.repository`
   - Set `target.url` (your app's URL)
   - Set `kaneai.project_id` and `kaneai.folder_id`

4. **Write requirements**
   - Edit `requirements/search.txt`
   - Format: `AC-001: User can <action>`

5. **Set credentials**
   ```bash
   export LT_USERNAME=your-username
   export LT_ACCESS_KEY=your-access-key
   ```

6. **Validate environment**
   ```bash
   agentic-stlc validate
   ```

7. **Run Stage 1 (KaneAI analysis)**
   ```bash
   agentic-stlc analyze
   ```

8. **Review analyzed requirements**
   ```bash
   cat requirements/analyzed_requirements.json
   ```

9. **Run full pipeline**
   ```bash
   agentic-stlc run --full
   ```

10. **Review results**
    ```bash
    agentic-stlc status
    cat reports/requirement-confidence-summary.md
    cat reports/release_recommendation.md
    ```

---

## Troubleshooting

### kane-cli not found

```bash
npm install -g @testmuai/kane-cli
kane-cli --version
```

### HyperExecute CLI not found

```bash
# Linux/macOS
curl -fsSL -O https://downloads.lambdatest.com/hyperexecute/linux/hyperexecute
chmod +x hyperexecute

# Windows
Invoke-WebRequest -Uri "https://downloads.lambdatest.com/hyperexecute/windows/hyperexecute.exe" -OutFile "hyperexecute.exe"
```

### PyYAML not installed (config file not loading)

```bash
pip install PyYAML
```

Without PyYAML the platform falls back to JSON parsing and uses all defaults.

### UnicodeEncodeError on Windows console

```powershell
$env:PYTHONIOENCODING = "utf-8"
agentic-stlc run
```

### Quality gate failures blocking CI

Gates at `WARNING` severity are non-blocking. To adjust:

```yaml
quality_gates:
  confidence:
    gate_severity: "WARNING"   # never blocks pipeline
```

### Kane results cached but stale

Delete the cache:
```bash
rm requirements/analyzed_requirements.json
agentic-stlc analyze
```

---

## Extensibility

### Adding a custom skill

```python
# my_skills/custom_reporter.py
from skills.base import AgentSkill

class CustomReporterSkill(AgentSkill):
    name = "custom_reporter"
    description = "Send results to my internal dashboard"

    def run(self, **inputs):
        # ... your logic ...
        return {"success": True, "dashboard_url": "https://..."}

# Register it
from platform.registry import SkillRegistry
SkillRegistry.register("custom_reporter", CustomReporterSkill)
```

### Adding a custom adapter

```python
# my_adapters/teamcity.py
from adapters.base import CIAdapter

class TeamCityAdapter(CIAdapter):
    def trigger_workflow(self, workflow_id, ref, inputs):
        # Call TeamCity REST API
        ...

    def get_workflow_status(self, run_id):
        ...

    def download_artifacts(self, run_id, output_dir):
        ...

    def list_recent_runs(self, workflow_id, limit=10):
        ...

# Register it
from platform.registry import AdapterRegistry
AdapterRegistry.register("ci", "teamcity", TeamCityAdapter)
```

Then in your config:

```yaml
adapters:
  ci: "teamcity"
```

---

## Versioning

The platform follows [Semantic Versioning](https://semver.org/):

| Version | Change |
|---------|--------|
| `1.0.x` | Bug fixes; backward-compatible |
| `1.x.0` | New features; backward-compatible |
| `x.0.0` | Breaking changes |

**Current version:** `1.0.0`

### Upgrade

```bash
pip install --upgrade agentic-stlc
npm update -g agentic-stlc
```

---

*Built on [LambdaTest](https://lambdatest.com) · [KaneAI](https://kaneai.lambdatest.com) · [HyperExecute](https://hyperexecute.lambdatest.com)*
