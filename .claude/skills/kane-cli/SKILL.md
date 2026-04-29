# Kane CLI Skill

## What is Kane CLI?

`kane-cli` is an AI-powered browser automation tool. Use it whenever the user asks you to:
- Test, verify, or check something on a website
- Automate browser interactions (clicks, form fills, navigation)
- Extract data from web pages
- Validate UI flows (login, checkout, search, settings)

## Authentication

Before running any test, verify auth:
```bash
kane-cli whoami
```

If not authenticated, use Basic Auth (OAuth requires a browser — incompatible with agent contexts):
```bash
kane-cli setup --auth-method basic --username YOUR_USERNAME --access-key YOUR_ACCESS_KEY
```

Credentials from env vars: LT_USERNAME and LT_ACCESS_KEY.

## Running a Test (Agent Mode)

Always use --agent and --headless in agent contexts:

```bash
kane-cli run "<plain English objective>" \
  --url <target URL> \
  --agent \
  --headless \
  --timeout 120
```

## Parsing Results

Last line of stdout is always the run_end JSON event:

```bash
kane-cli run "..." --agent --headless 2>/dev/null | tail -1 | jq .
```

Key fields from run_end:
- status: "passed" or "failed"
- summary: full description of what happened
- one_liner: short human-readable result
- reason: why it passed or failed
- duration: seconds
- final_state: extracted data key-value store
- run_dir: path to logs and screenshots

## Presenting Results

After parsing run_end, present:
1. Status (passed/failed)
2. Step count and duration
3. Summary of what was tested
4. Extracted values from final_state
5. On failure: inspect run_dir for screenshots/logs

## Parallel Tests

```bash
RESULTS_DIR=$(mktemp -d)
kane-cli run "..." --agent --headless --timeout 120 > "$RESULTS_DIR/test1.ndjson" 2>&1 &
kane-cli run "..." --agent --headless --timeout 120 > "$RESULTS_DIR/test2.ndjson" 2>&1 &
wait
# Parse each: tail -1 "$RESULTS_DIR/testN.ndjson" | jq .
```

## Exit Codes
- 0: passed
- 1: failed (assertion not met)
- 2: error (auth, Chrome crash)
- 3: timeout or cancelled

## Rules
- Always use --agent (NDJSON mode, no TUI)
- Always use --headless in agent contexts
- Always set --timeout
- Parse only run_end (last line) for final result
- On failure, read run_dir screenshots before reporting
# Kane CLI Skill for Claude Code

## What is Kane CLI?

`kane-cli` is an AI-powered browser automation tool. Use it whenever the user asks you to:
- Test, verify, or check something on a website
- Automate browser interactions (clicks, form fills, navigation)
- Extract data from web pages
- Validate UI flows (login, checkout, search, settings)

## Authentication

Before running any test, verify auth:
```bash
kane-cli whoami
```

If not authenticated, use Basic Auth (OAuth requires a browser — incompatible with agent contexts):
```bash
kane-cli setup --auth-method basic --username YOUR_USERNAME --access-key YOUR_ACCESS_KEY
```

Credentials from env vars: LT_USERNAME and LT_ACCESS_KEY.

## Running a Test (Agent Mode)

Always use --agent and --headless in agent contexts:

```bash
kane-cli run "<plain English objective>" \
  --url <target URL> \
  --agent \
  --headless \
  --timeout 120
```

## Parsing Results

Last line of stdout is always the run_end JSON event:

```bash
kane-cli run "..." --agent --headless 2>/dev/null | tail -1 | jq .
```

Key fields from run_end:
- status: "passed" or "failed"
- summary: full description of what happened
- one_liner: short human-readable result
- reason: why it passed or failed
- duration: seconds
- final_state: extracted data key-value store
- run_dir: path to logs and screenshots

## Presenting Results

After parsing run_end, present:
1. Status (passed/failed)
2. Step count and duration
3. Summary of what was tested
4. Extracted values from final_state
5. On failure: inspect run_dir for screenshots/logs

## Parallel Tests

```bash
RESULTS_DIR=$(mktemp -d)
kane-cli run "..." --agent --headless --timeout 120 > "$RESULTS_DIR/test1.ndjson" 2>&1 &
kane-cli run "..." --agent --headless --timeout 120 > "$RESULTS_DIR/test2.ndjson" 2>&1 &
wait
# Parse each: tail -1 "$RESULTS_DIR/testN.ndjson" | jq .
```

## Exit Codes
- 0: passed
- 1: failed (assertion not met)
- 2: error (auth, Chrome crash)
- 3: timeout or cancelled

## Rules
- Always use --agent (NDJSON mode, no TUI)
- Always use --headless in agent contexts
- Always set --timeout
- Parse only run_end (last line) for final result
- On failure, read run_dir screenshots before reporting
