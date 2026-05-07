# Agentic STLC — Live Demo Script
### Kane AI + HyperExecute | Presenter Guide

---

## Before You Begin

**What to have open:**
- This repository in VS Code or your terminal
- The GitHub Actions run (latest or in-progress) in a browser tab
- The LambdaTest Automation dashboard in a second tab
- The HyperExecute dashboard in a third tab

**Open source repo (share this with the audience early):**
👉 [github.com/lambdapro/agentic-stlc-kane-hyperexecute](https://github.com/lambdapro/agentic-stlc-kane-hyperexecute)

**Connect with the author:**
👉 [linkedin.com/in/mudassar-syed-19a87b239](https://www.linkedin.com/in/mudassar-syed-19a87b239/)

**What to know:** This is a live, end-to-end pipeline. Every result shown in the report was produced by running real browsers against a real site. There are no mocks, no recorded responses, and no hardcoded outcomes.

---

## Opening — Set the Scene (2 min)

> "Every QA team faces the same three problems.
>
> First — **requirements live in documents, tests live in code**. No one keeps them in sync. A criterion gets added to Jira; six months later the test suite has drifted and nobody knows which tests actually cover which requirements.
>
> Second — **writing tests is slow**. A senior engineer spends days scripting Selenium for a feature that took hours to build. That pace cannot scale with modern release cycles.
>
> Third — **running tests is sequential by default**. Five tests, five minutes. Fifty tests, fifty minutes. The CI queue becomes the bottleneck.
>
> What you are about to see solves all three. We call it the **Agentic STLC** — a pipeline where plain-English requirements drive every stage of QA automatically, from verification to parallel cloud execution to a release verdict. Two tools make it possible: **Kane AI** and **HyperExecute**."

---

## The One Sentence Version

> "You write requirements in plain English. Kane AI verifies them on the live site and creates functional test cases. HyperExecute runs those tests in parallel across cloud VMs. The pipeline produces a full traceability report and a GREEN / YELLOW / RED release verdict — with no human writing a single line of test code."

---

## Part 1 — Show the Input (2 min)

Open `requirements/search.txt`.

```
Title: Browse and search products on ecommerce playground

As a shopper
I want to explore products on ecommerce-playground.lambdatest.io
So that I can find and buy what I need

Acceptance Criteria:
User can navigate to the product catalog and see a list of products
User can apply a brand filter from the sidebar to narrow product results
User can click a product to open its detail page and see the name and price
User can browse products and the homepage without logging in
User can search for a product by name and see relevant results
```

> "This is the entire input. Plain English. User stories. Acceptance criteria written by a product manager, not an engineer.
>
> Now open `requirements/cart.txt` — we added this file this morning to test whether the pipeline picks up new requirements automatically."

Open `requirements/cart.txt`.

```
Acceptance Criteria:
User can add a product to the cart and see the cart item count update
User can open the cart and see the list of added items with their names and prices
```

> "Two new criteria. No test code. No Jira ticket to an engineer. Just commit and push — the pipeline does the rest.
>
> **Cost angle:** In a traditional team, each of these criteria translates to a test-case document, a review cycle, a scripted Selenium test, and a maintenance burden when the UI changes. With this pipeline, the cost of adding a new requirement is the time it takes to type one sentence."

---

## Part 2 — Stage 1: Kane AI Functional Verification (4 min)

> "Stage 1 is where the AI does its work. And this is important: **it is the only stage where AI is involved.** I will come back to that."

Show `ci/analyze_requirements.py` — specifically the `run_kane()` function.

> "For each acceptance criterion, `kane-cli run` is called. Kane AI spins up a real Chrome browser on LambdaTest's cloud infrastructure — not a headless simulator, a real browser — navigates to the target site, and attempts to verify the criterion step by step.
>
> It returns structured output: a pass/fail status, a one-line summary of what it actually observed on the page, the steps it took, and a session link you can click to watch the recording."

Show the Kane AI session video in LambdaTest for one criterion.

> "Watch this — Kane navigated to the ecommerce site, found the product catalog, confirmed products are visible, and returned `passed`. This happened autonomously. No selector was written. No locator was hardcoded.
>
> **Security angle:** The credentials — LambdaTest username and access key — are passed inline to `kane-cli` on every call. There is no `kane-cli login` step in CI. That command opens an OAuth browser flow, which has no place in a headless pipeline. By passing credentials at runtime, we get per-invocation authentication with no stored session tokens, no OAuth refresh tokens sitting on the CI runner, and no credential files in the repository. The CI runner is stateless."

Point out the parallel execution in `analyze_requirements.py`:

```python
with ThreadPoolExecutor(max_workers=5) as executor:
    results = list(executor.map(_run_kane_indexed, enumerate(criteria, start=1)))
```

> "All five criteria run in parallel — five simultaneous Kane AI sessions. The Stage 1 wall-clock time is bounded by the slowest single criterion, not the sum of all of them.
>
> **Cost angle:** Kane AI sessions are billed per run. By running in parallel, we complete Stage 1 in roughly the time of one serial session. That is five criteria verified in the cost of five sessions but the time of one."

---

## Part 3 — Stages 2 and 3: Deterministic, No AI (4 min)

> "Here is where I want to push back against a misconception that is common in conversations about agentic systems.
>
> **Not every stage of an intelligent pipeline needs to use AI. In fact, the stages that should not use AI are the ones where you need guaranteed, reproducible outcomes.**"

Open `ci/agent.py` — show the `sync_scenarios()` function.

> "Stage 2 is pure Python. No model. No prompt. It reads the analyzed requirements, loads the existing `scenarios/scenarios.json`, and diffs them deterministically.
>
> If a requirement is new, a new scenario is created with a unique ID. If a requirement's description changed, the scenario is marked `updated`. If a requirement was removed, the scenario is marked `deprecated` — never deleted, always traceable. This logic runs identically on every machine, in every timezone, on every CI run. The output is always the same for the same input."

Show the `generate_tests()` function.

> "Stage 3 is also deterministic. Each scenario ID maps to a fixed test function name. Each test function has a pre-written Selenium body with the right selectors and assertions for this site. There is no LLM hallucinating a selector, no prompt engineering to worry about, no test that works in staging but fails in prod because the model generated slightly different code this run.
>
> The test file `tests/selenium/test_products.py` is reproducibly generated. You can regenerate it a thousand times and get the same output.
>
> **The benefit of determinism in QA:** In testing, non-determinism is a defect. Flaky tests — tests that sometimes pass and sometimes fail for the same code — are one of the most expensive problems in software delivery. If your test generation is non-deterministic, your test suite is non-deterministic by construction. Stages 2 and 3 are deliberately not AI because determinism matters more than flexibility at this point in the pipeline.
>
> **Cost angle:** Deterministic stages cost nothing to run beyond compute. No LLM tokens. No API calls to external models. A CI runner running Stage 2 and Stage 3 costs the same whether you have 5 scenarios or 500."

---

## Part 4 — Stage 4: HyperExecute Regression at Scale (4 min)

> "Stage 4 is where scale enters the picture."

Show `hyperexecute.yaml`:

```yaml
autosplit: true
concurrency: 5

testDiscovery:
  type: raw
  mode: dynamic
  command: cat reports/pytest_selection.txt

testRunnerCommand: PYTHONPATH=. pytest "$test" -v --tb=short -s
```

> "The HyperExecute CLI receives a list of test node IDs — one per line in `pytest_selection.txt`. It discovers them, splits them across five parallel cloud VMs, and executes them simultaneously. Each VM runs a single `pytest` node, opens a real browser on LambdaTest Selenium Grid, and uploads its artifacts when done.
>
> With sequential execution on a single runner, five Selenium tests take roughly five minutes. With HyperExecute at concurrency five, they all finish in the time of the slowest single test — typically under two minutes.
>
> As you add more requirements — ten, twenty, fifty — the wall-clock time barely changes. HyperExecute absorbs the parallelism."

Open the HyperExecute dashboard and show the job.

> "Every task is visible here. Click any task to see its logs, its browser recording, its artifacts. This is not a black box — every execution is fully auditable.
>
> **Security angle:** HyperExecute runs inside LambdaTest's SOC 2 Type II compliant infrastructure. Your test code runs on isolated VMs — no shared state between jobs, no leftover session data, no cross-tenant exposure. Credentials reach the VM via environment variables set by the HyperExecute CLI at runtime, not stored in the VM image.
>
> **Cost angle:** HyperExecute is billed by concurrent session minutes. Sequential testing wastes that budget — a ten-minute test suite running on one VM costs ten session-minutes. The same suite at concurrency five costs two session-minutes of wall-clock time. You spend more session-minutes in parallel, but you save real time — and time is what blocks releases.
>
> More importantly: HyperExecute's `retryOnFailure: true, maxRetries: 1` setting means a flaky test gets one automatic retry. The pipeline fetches the latest result — so if a test failed on its first attempt but passed on the retry, the final report shows `passed`. No false negatives inflating your failure count."

---

## Part 5 — The Report: What It Tells You (5 min)

Switch to the GitHub Actions run. Open the Summary tab.

> "The pipeline writes a single GitHub Actions summary that covers everything. Let me walk through it section by section — because the structure of this report is deliberate."

### Stage 1 — Requirement Analysis

> "The first section tells you what Kane AI found. For each acceptance criterion, you see the Kane AI status — passed or failed — a one-line summary of what it actually observed on the live site, and a link to the session recording.
>
> This is your **functional test result**. Kane AI has verified, against the real site right now, that the criterion is achievable. If a criterion shows `failed` here, it means the feature is genuinely broken on the live site — not a test script problem, not a flaky selector. The AI could not demonstrate the behaviour."

### Stage 2 — Scenario Management

> "The second section shows what the pipeline did to the scenario catalog. New scenarios are flagged — these are the ones that triggered new test generation. Active scenarios confirm that existing coverage is intact. Deprecated scenarios show requirements that were removed from the requirements file."

### Stage 3 — Test Generation

> "Stage 3 confirms which Selenium test cases were generated this run. Each one maps to a scenario ID and a test case ID — the full chain from requirement to code is explicit."

### Stage 4a — Test Selection

> "Stage 4a shows what was queued for HyperExecute. On a full run — which this is — all active scenarios are selected. On an incremental run, only new and updated scenarios run, which reduces session spend when requirements are mostly stable."

### Stage 4b — HyperExecute Execution

> "Stage 4b is the execution summary from HyperExecute: job ID, overall status, pass count, fail count. Click the job link and you land directly on the HyperExecute dashboard for this specific run."

### Regression on HyperExecute — Per-Test Detail

> "This table shows every test individually — function name, pass/fail status, and a direct link to the LambdaTest Automate session for that test. Click any session link and you see the browser recording, the network log, the console log, the screenshots at each step.
>
> If a test failed, you are one click away from watching exactly what happened in the browser. This is not a log file. It is a video."

### Stage 5 — Functional + Regression Result (Traceability)

> "This is the most important section. The traceability matrix joins every layer:
>
> - The **requirement** — what the product said it should do
> - The **scenario** — the testable version of that requirement
> - The **test case** — the Selenium automation that verifies it
> - The **Kane AI result** — did AI confirm it works on the live site?
> - **What Kane Saw** — the one-liner from Kane's session
> - The **Functional + Regression Result** — the combined verdict
>
> The last column is the key one. A requirement passes in this column only when the Selenium regression test on HyperExecute actually passed. Kane AI tells you the feature exists. HyperExecute tells you the automation is stable under real-world conditions. Both need to be green for a requirement to earn a passing result in the traceability matrix.
>
> Expand the Kane AI verification detail — you see the exact steps Kane took, the full narrative summary, and a link to the TestMu AI dashboard session. This is your audit trail for the functional verification.
>
> At the bottom: the release verdict."

### Release Recommendation

> "GREEN means pass rate is at or above 80% across all regression tests. YELLOW is 60-79% — conditional, review the failures. RED is below 60% — stop the release, investigate.
>
> These thresholds are in code. They are not a manual judgement call. The same criteria apply to every run, every team, every release cycle. QA sign-off is no longer a conversation — it is a computed outcome from actual test data."

---

## Part 6 — Cost and Security Summary (2 min)

> "Let me consolidate the cost and security story before we close.
>
> **Cost — where you save:**
>
> - No engineer spends time writing test scripts. Kane AI generates the functional case. The Selenium test is generated deterministically. Zero person-hours of test authoring per requirement.
> - Parallel execution on HyperExecute means your CI time does not grow linearly with your test count. 50 tests at concurrency 10 take the same wall-clock time as 10 tests at concurrency 10.
> - AI runs only in Stage 1. Stages 2, 3, and all the reporting logic are pure Python — no LLM token spend beyond the Kane AI sessions.
> - Incremental runs — the default for pushes that change existing requirements — only re-run new and updated scenarios. You do not burn session minutes re-verifying things that did not change.
>
> **Security — what you get by default:**
>
> - Credentials are runtime environment variables. They are never written to disk, never stored in the repository, never embedded in test code.
> - Kane AI sessions run on LambdaTest's cloud infrastructure — not on your CI runner. Your network, your internal systems, your secrets are not exposed to the browser automation.
> - HyperExecute VMs are isolated per job. No shared state. No cross-run data leakage.
> - The pipeline is fully auditable. Every Kane AI session, every HyperExecute task, every test result has a URL. Nothing is a black box."

---

## Part 7 — Subscription Model: Optimize Agentic Usage (3 min)

> "Before I close, I want to talk about how Kane AI and HyperExecute are priced — because the pipeline architecture was designed around these models, not imposed on top of them.

### Kane AI

> "Kane AI is priced per session. One `kane-cli run` call = one session. In this pipeline, Kane runs once per acceptance criterion, in Stage 1 only.
>
> The design implication: **Kane runs exactly as many times as you have requirements, not as many times as you run tests.** Once a criterion is verified, the Kane session is done. The Selenium regression test that HyperExecute runs does not touch Kane. You are not paying for Kane on every CI push — only when requirements are verified.
>
> On an incremental run, only new and updated requirements trigger new Kane sessions. If you push a bug fix that does not change any acceptance criteria, Stage 1 produces zero Kane sessions. Your Kane spend is tied to the rate of requirements change, not the rate of CI triggers.
>
> For teams that push to CI dozens of times per day, this is a significant optimization. Kane AI is used precisely — for what only AI can do: verifying that a human-language criterion is demonstrably true on a real site."

### HyperExecute

> "HyperExecute is priced by concurrent session minutes. The optimization here is concurrency.
>
> A team running 20 Selenium tests sequentially on a free LambdaTest plan spends 20 × (average test time) = roughly 20-40 minutes of CI time per push. At concurrency 5 on HyperExecute, that collapses to 4-8 minutes wall-clock — and the session-minute spend is roughly the same, just compressed.
>
> For release gates — where CI time directly impacts how fast code reaches production — HyperExecute parallelism has a compounding effect. Faster CI means more releases per day. More releases per day means smaller batch sizes. Smaller batch sizes mean lower risk and faster rollback when something goes wrong.
>
> HyperExecute's `retryOnFailure` is part of the subscription value. A flaky test that fails once and passes on retry is automatically resolved — the pipeline shows the latest result, not the first. You do not need to re-trigger the entire pipeline for one flaky test.
>
> The combined model: **Kane AI spend is tied to requirements change frequency. HyperExecute spend is tied to test suite size and execution frequency.** These scale independently. A stable product with a growing test suite will see Kane AI spend stay flat while HyperExecute spend grows slowly with test count. A product in active feature development will see Kane AI spend grow with requirements and HyperExecute spend stay flat if the test count is managed with incremental runs."

---

## Closing — The Power of the CLI (3 min)

> "I want to end with something that gets overlooked when people talk about agentic testing: the power is in the CLI.
>
> Every AI capability in this pipeline is accessible from a terminal. No GUI. No point-and-click workflow. That means it integrates into any CI system — GitHub Actions today, GitLab tomorrow, Jenkins next quarter. The pipeline is not locked to any platform."

Show in the terminal:

```bash
# Verify a single acceptance criterion on the live site — right now, from this terminal
kane-cli run \
  "On https://ecommerce-playground.lambdatest.io/ — User can navigate to the product catalog and see a list of products" \
  --username "$LT_USERNAME" \
  --access-key "$LT_ACCESS_KEY" \
  --agent --headless --timeout 120 --max-steps 15
```

> "That command. One line. Kane AI spins up a real browser, navigates to that site, verifies the criterion, and returns a structured result with a session link — from your terminal. No dashboard. No manual steps.
>
> Now the same for HyperExecute:"

```bash
# Submit the full test suite to HyperExecute — run in parallel on cloud VMs right now
./hyperexecute \
  --user "$LT_USERNAME" \
  --key "$LT_ACCESS_KEY" \
  --config hyperexecute.yaml
```

> "One command. HyperExecute picks up the test selection file, fans the tests across cloud VMs, streams the results back, and writes the artifacts. From your terminal. In CI. In a Docker container. Anywhere you can run a binary.
>
> This is the key insight: **the agentic STLC is not a SaaS product you log into. It is a set of CLI tools you orchestrate.** The intelligence lives in Kane AI — verifying requirements. The scale lives in HyperExecute — executing tests. The traceability, the reporting, the verdict logic — that is plain Python that you own and can modify.
>
> You are not buying a black box. You are buying two powerful CLIs and composing them into a pipeline that your team controls completely."

---

## Closing Statement

> "To summarize what you have seen today:
>
> - Plain-English requirements go in. A release verdict comes out.
> - **Kane AI** does the functional verification — the only AI in the pipeline. One session per criterion. Real browser. Real site. Full session recording.
> - **Stages 2 and 3 are deterministic Python** — no AI, no randomness, guaranteed reproducibility. Because in testing, determinism is not a limitation, it is a requirement.
> - **HyperExecute** runs the regression suite in parallel — collapsing test time from linear to constant regardless of suite size.
> - The report gives you full traceability from requirement to result, a per-test session link for every failure, and a computed release verdict based on your own thresholds.
> - Kane AI spend tracks requirements change. HyperExecute spend tracks test execution frequency. Neither over-charges you for what the other does.
> - And everything is a CLI. It runs anywhere. It integrates with anything. You own the pipeline.
>
> The agentic STLC is not about replacing QA engineers. It is about removing the work that slows them down — manual test authoring, sequential execution, disconnected reporting — so they can focus on the judgment calls that only humans can make.
>
> The entire pipeline is open source. Fork it, adapt it to your stack, and ship it:
>
> 👉 **github.com/lambdapro/agentic-stlc-kane-hyperexecute**
>
> And if you want to go deeper — questions, customisations, or a conversation about how this applies to your team — connect with me directly on LinkedIn:
>
> 👉 **linkedin.com/in/mudassar-syed-19a87b239**
>
> Questions?"

---

## Try It Yourself

> Share this slide / card at the end of every session.

### Open Source — Run This Pipeline Today

**Repo:** [github.com/lambdapro/agentic-stlc-kane-hyperexecute](https://github.com/lambdapro/agentic-stlc-kane-hyperexecute)

Everything in this demo is in that repository. MIT licensed. Fork it, point it at your own site, and push a requirements file. The first pipeline run takes care of the rest.

**What you need to get started:**
1. A LambdaTest account — [lambdatest.com](https://www.lambdatest.com) (free tier available)
2. Two GitHub secrets: `LT_USERNAME` and `LT_ACCESS_KEY`
3. A `requirements/*.txt` file written in plain English

That is it. No test framework knowledge required. No Selenium experience required. No prompt engineering required.

```bash
# Clone, set your credentials, push
git clone https://github.com/lambdapro/agentic-stlc-kane-hyperexecute
cd agentic-stlc-kane-hyperexecute

# Edit requirements in plain English
vim requirements/search.txt

# Commit and push — the pipeline runs automatically
git add requirements/
git commit -m "feat: add my acceptance criteria"
git push
```

### Connect Directly

Have questions about the pipeline, want to adapt it to your stack, or just want to talk agentic testing? Reach out directly:

**LinkedIn:** [linkedin.com/in/mudassar-syed-19a87b239](https://www.linkedin.com/in/mudassar-syed-19a87b239/)

---

## Quick Reference — Key Points by Audience

| If talking to... | Lead with... |
|---|---|
| **Engineering leaders** | Time-to-release impact; parallel execution; CI queue elimination |
| **Security / compliance** | Stateless credentials; isolated VMs; full audit trail with session links |
| **Finance / procurement** | Kane AI spend tied to requirements change rate (not CI frequency); HyperExecute parallelism vs sequential session cost |
| **QA managers** | Full traceability matrix; computed verdict removes subjectivity; deterministic Stages 2-3 eliminate flaky test generation |
| **Developers** | CLI-first; integrates with any CI; plain Python orchestration you can fork and modify |

---

## Appendix — Objection Handling

**"What happens when Kane AI gets the wrong answer?"**
> "Kane AI's output feeds into Stage 1 as a signal, not a gate. The `kane_status` field in the traceability matrix shows what Kane observed. The actual release gate is the HyperExecute Selenium result in the `overall` column. A requirement earns a passing result when the Selenium regression test passes on HyperExecute — not when Kane says it looked right. The two signals are independent and both are visible in the report."

**"What if the site changes and the Selenium selectors break?"**
> "The selectors in the generated tests target robust, semantic attributes — heading tags, form inputs, ARIA roles — not generated class names or positional XPaths. When they do break, the HyperExecute run flags the failure, the session recording shows exactly where the selector failed, and you update the test. Because the test is code you own, the fix is a code change — not a re-training cycle."

**"Is this just for ecommerce?"**
> "No. The requirements file is plain text. The Kane AI command takes a URL and an instruction. The Selenium tests are generated from scenario data that lives in JSON. Swap the requirements file and the target URL — everything else stays the same. This demo uses an ecommerce site because it is a publicly accessible, realistic app with real product flows."

**"What does this cost to run?"**
> "For this demo run: Stage 1 made 7 Kane AI calls (5 existing + 2 new from `cart.txt`). Stage 4 ran 5-7 Selenium tests on HyperExecute at concurrency 5. Stages 2, 3, and all reporting are pure compute with no external API cost. The pipeline is designed so that AI spend is bounded by the number of requirements, not the frequency of CI runs."

**"Do I need a DevOps engineer to set this up?"**
> "Two GitHub secrets — `LT_USERNAME` and `LT_ACCESS_KEY`. One YAML workflow file. One Python requirements file. The rest is already in the open source repo at **github.com/lambdapro/agentic-stlc-kane-hyperexecute**. Fork it, set the secrets, push a requirements file. The first run takes care of itself. If you get stuck, connect with me on LinkedIn — **linkedin.com/in/mudassar-syed-19a87b239** — and we will sort it out."
