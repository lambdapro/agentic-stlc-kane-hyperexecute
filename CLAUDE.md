# Claude Code — Agentic SDLC Project Config

## Project Overview
End-to-end agentic SDLC demo using Kane AI CLI + Selenium Python + HyperExecute targeting an eCommerce playground.
Requirements drive the entire pipeline; stages are defined in PIPELINE.md.

## How to Execute a Pipeline Stage
```bash
claude -p "Execute stage: <STAGE_NAME> from PIPELINE.md"
```
Available stages: ANALYZE_REQUIREMENTS, MANAGE_SCENARIOS, GENERATE_TESTS,
SELECT_TESTS, TRACEABILITY_REPORT, RELEASE_RECOMMENDATION

## Key Files
- `PIPELINE.md` — Natural language stage instructions (read this to understand what to do)
- `requirements/search.txt` — Source requirements (user stories + acceptance criteria)
- `requirements/analyzed_requirements.json` — Output of ANALYZE_REQUIREMENTS stage
- `scenarios/scenarios.json` — Managed test scenarios (updated by MANAGE_SCENARIOS)
- `kane/objectives.json` — Kane CLI objectives per scenario
- `tests/selenium/` — Selenium Python test suite (pytest + page objects)
- `hyperexecute.yaml` — HyperExecute execution config
- `reports/` — Runtime output: traceability matrix, recommendation (gitignored)

## Credentials (from environment)
- `LT_USERNAME` — LambdaTest username
- `LT_ACCESS_KEY` — LambdaTest access key
- `ANTHROPIC_API_KEY` — For Claude Code agentic steps

## Kane CLI Usage (Agent Mode)
Always use `--agent --headless` in CI. Pass credentials via flags:
```bash
kane-cli run "<objective>" \
  --url https://ecommerce-playground.lambdatest.io/ \
  --username $LT_USERNAME --access-key $LT_ACCESS_KEY \
  --agent --headless --timeout 120 --max-steps 15
```
Parse results: `tail -1 output.ndjson | jq .`

## Selenium Test Suite
- Framework: pytest
- Page objects: `tests/selenium/pages/`
- Run locally: `pytest tests/selenium/ -v`
- Run on HyperExecute: `./hyperexecute --user $LT_USERNAME --key $LT_ACCESS_KEY --config hyperexecute.yaml`

## Permissions Granted
- Run kane-cli commands
- Run pytest
- Run pip install
- Read/write all files in this repo
- Execute hyperexecute CLI binary

## Target Application
- URL: https://ecommerce-playground.lambdatest.io/
- Feature under test: Product browsing, search, and details
