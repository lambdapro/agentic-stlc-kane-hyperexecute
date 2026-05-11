# KaneAI Test Intent — IssueReporting Power App
## Natural Language Test Goals Per Acceptance Criterion

---

> **How this file is used:**
> Each entry below documents the goal that KaneAI receives during Stage 1 (`ci/analyze_requirements.py`).
> KaneAI executes the goal autonomously against the live Power App — no selectors, no scripts.
> This file exists for demo narration, team review, and traceability auditing.
>
> KaneAI does NOT use element IDs, CSS selectors, or XPath.
> It navigates by observable behaviour: button labels, field contexts, visual roles,
> and canvas layout inference.

---

## TC-001 — Navigate to App and View Issues List

**KaneAI Goal (as passed to `kane-cli run`):**
```
"User can navigate to the IssueReporting app and see the main issues list with existing reports"
```

**KaneAI Autonomous Steps (from session recording):**
1. Navigate to Power Apps URL (`POWERAPPS_URL` env var)
2. Detect M365 authentication requirement
3. Complete auth flow: email → Next → password → Sign in → Stay signed in
4. Wait for canvas to fully render (networkidle)
5. Observe main screen — identify issues list component by context
6. Verify list is visible with column structure and at least one record
7. Return PASSED/FAILED with one-line observation

**Expected KaneAI Observation (PASSED):**
`"IssueReporting app loaded — main issues list visible with 12 records and column headers"`

**Self-healing scenario:** If the list layout changes in a solution update, KaneAI re-identifies it by its content role (displaying a tabular list of issue records) rather than its canvas control ID.

---

## TC-002 — Create New Issue Report

**KaneAI Goal:**
```
"User can create a new issue report by providing a title, description, and category"
```

**KaneAI Autonomous Steps:**
1. Authenticate and reach issues list (as TC-001)
2. Identify and activate the 'New Issue' creation action (button/link by label)
3. Observe form canvas — identify Title, Category, Description fields by label context
4. Fill Title: "KaneAI Test Issue - [timestamp]"
5. Select Category from dropdown by visible label (not option index)
6. Fill Description: "Automated test issue created by KaneAI"
7. Activate Submit/Save action
8. Observe canvas refresh — locate new record in issues list by title text
9. Verify record status shows "Pending"

**Expected KaneAI Observation (PASSED):**
`"New issue report created — record 'KaneAI Test Issue' appeared in list with status 'Pending'"`

**Self-healing scenario:** When solution publish regenerates `data-control-id` values for the form fields, KaneAI re-identifies them by their label proximity (`fill Title field` → field adjacent to 'Title' label). No selector update required.

---

## TC-003 — View Issue Details

**KaneAI Goal:**
```
"User can view issue details including status, priority, and full description"
```

**KaneAI Autonomous Steps:**
1. Authenticate and reach issues list
2. Select first visible issue record (by clicking the row)
3. Observe detail view canvas — identify Status, Priority, Description fields
4. Verify Status value is visible and non-empty
5. Verify Priority value is visible and non-empty
6. Verify Description is visible and not truncated

**Expected KaneAI Observation (PASSED):**
`"Detail view showed Status: 'Pending', Priority: 'Medium', Description: full text visible"`

---

## TC-004 — Filter Issues by Status

**KaneAI Goal:**
```
"User can filter the issues list by status to see only active or resolved items"
```

**KaneAI Autonomous Steps:**
1. Authenticate and reach issues list
2. Identify filter control by contextual cues (near 'Status' label or filter icon)
3. Select 'Active' status from filter options
4. Observe list refresh — count records visible
5. Verify all visible records show 'Active' status
6. Verify record count differs from unfiltered view

**Expected KaneAI Observation (PASSED):**
`"Filter applied — 4 of 12 items shown matching 'Active' status"`

---

## TC-005 — Navigate Back from Detail View

**KaneAI Goal:**
```
"User can navigate back from an issue detail view to the main issues list"
```

**KaneAI Autonomous Steps:**
1. Authenticate and reach issues list
2. Open any issue detail view (as TC-003)
3. Identify back navigation control (Back button, breadcrumb, back arrow)
4. Activate back navigation
5. Verify issues list is visible again with records

**Expected KaneAI Observation (PASSED):**
`"Back navigation returned to main issues list — 12 records visible"`

---

## TC-006 — Edit Submitted Issue Report

**KaneAI Goal:**
```
"User can edit a submitted issue report and see the updated details saved"
```

**KaneAI Autonomous Steps:**
1. Authenticate and reach issues list
2. Open any issue detail view
3. Identify Edit action (button or icon by label/role)
4. Activate edit mode
5. Locate Title field in edit form — clear and fill new value
6. Activate Save action
7. Verify detail view shows updated Title value

**Expected KaneAI Observation (PASSED):**
`"Edit saved — title updated to 'Edited by KaneAI - [timestamp]'"`

**Self-healing scenario:** Edit modal control IDs differ from create form control IDs and both regenerate on publish. KaneAI identifies the Title field by label context in both forms independently.

---

## TC-007 — Search Issues by Keyword

**KaneAI Goal:**
```
"User can search for an existing issue by keyword and see matching results"
```

**KaneAI Autonomous Steps:**
1. Authenticate and reach issues list
2. Identify search input field (by placeholder text, icon, or positional context)
3. Enter a keyword that exists in at least one issue title
4. Observe list refresh — verify only matching records are shown
5. Verify keyword is present in visible record titles/descriptions

**Expected KaneAI Observation (PASSED):**
`"Search returned 2 matching records containing keyword 'inspection'"`

---

## TC-008 — Validation Handling

**KaneAI Goal:**
```
"User can see a validation message when submitting a form with empty mandatory fields"
```

**KaneAI Autonomous Steps:**
1. Authenticate and reach issues list
2. Open the new issue creation form (as TC-002 step 2)
3. Attempt to submit the form without filling any fields
4. Observe form response — identify validation messages per field
5. Verify at least one validation message is visible
6. Verify the form has NOT submitted (still on the form canvas)

**Expected KaneAI Observation (PASSED):**
`"3 validation messages displayed for empty mandatory fields: Title, Category, Description"`

---

## TC-009 — Grid Interaction (Sort + Paginate)

**KaneAI Goal:**
```
"User can interact with the issues grid — sorting columns and navigating pages"
```

**KaneAI Autonomous Steps:**
1. Authenticate and reach issues list (with sufficient records for pagination)
2. Identify a sortable column header (e.g., 'Priority' or 'Date')
3. Click column header — observe row order changes
4. Identify pagination control (next page button or page number)
5. Navigate to next page — observe different records shown
6. Navigate back to page 1 — observe first set of records restored

**Expected KaneAI Observation (PASSED):**
`"Sort changed row order by Priority; page 2 showed 10 different records; page 1 restored"`

---

## TC-010 — Approver Workflow Navigation

**KaneAI Goal:**
```
"User can access the approver workflow view and see issues pending approval"
```

**KaneAI Autonomous Steps:**
1. Authenticate with approver-role M365 credentials
2. Navigate to IssueReporting app
3. Observe approver-specific UI (KaneAI identifies by role context, not control ID)
4. Locate pending approvals list — verify at least one issue is present
5. Identify Approve action for a pending issue
6. Verify Approve and Reject actions are both accessible

**Expected KaneAI Observation (PASSED):**
`"Approver view loaded — 2 pending approvals visible; Approve and Reject actions confirmed"`

**Self-healing scenario:** The approver view layout is entirely different from the submitter layout — different canvas controls, different navigation elements. KaneAI navigates both by goal-directed intent, not by layout-specific selectors. Both survive independent layout changes.

---

## Why KaneAI Outperforms Playwright Codegen for Power Apps

| Challenge | Playwright Codegen Response | KaneAI Response |
|---|---|---|
| Canvas element IDs change on publish | FAILS — recorded IDs invalid | ADAPTS — navigates by label/role |
| Approver layout differs from submitter layout | Separate test file needed | Single goal, autonomous role detection |
| M365 auth flow | Manual fixture code | Autonomous authentication |
| Form field order changes | Breaks positional locators | Fills by label context |
| Validation messages have dynamic IDs | Assertion fails | Verifies by observable text presence |
| Grid structure changes in Power Apps update | Row index selectors break | Identifies grid by functional role |
| New dropdown options added | May break option index selectors | Selects by visible label |

The fundamental difference: Playwright Codegen **records a path**. KaneAI **verifies a goal**.
When the Power App changes, the path breaks. The goal remains constant. KaneAI continues.
