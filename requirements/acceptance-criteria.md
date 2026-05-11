# Acceptance Criteria — IssueReporting Power App
## Enterprise QA Specification | All 10 User Stories

---

> **How this file flows into the pipeline:**
> Each acceptance criterion block maps directly to one row in `requirements/search.txt`.
> The pipeline parses `search.txt`, runs KaneAI against each criterion, and generates
> one Playwright regression test per criterion. This file is the authoritative
> human-readable expansion of those criteria.

---

## AC-001: Navigate to App and View Issues List (PP-101)

**Scenario ID:** SC-001

**Criteria:**
- AC1: The IssueReporting app loads within the Microsoft Teams tab without error.
- AC2: The M365 authentication flow completes successfully using the provided credentials.
- AC3: The main issues list screen is visible after authentication.
- AC4: The issues list displays column headers: Title, Status, Priority, Category, Submitted By, Date.
- AC5: At least one existing issue record is visible in the list.
- AC6: The list is scrollable when records exceed the visible area.

**KaneAI Goal:** "User can navigate to the IssueReporting app and see the main issues list with existing reports"

**Playwright Regression:** `test_sc_001_navigate_to_app_and_see_issues_list`

---

## AC-002: Create New Issue Report (PP-102)

**Scenario ID:** SC-002

**Criteria:**
- AC1: User can open the new issue creation form from the issues list screen.
- AC2: The form displays mandatory fields: Title, Category (dropdown), and Description.
- AC3: User can fill in all mandatory fields with valid values.
- AC4: User can submit the completed form without error.
- AC5: After submission, the new issue record appears in the issues list.
- AC6: The new record shows status "Pending" immediately after creation.
- AC7: The submission is reflected without a full page reload (canvas in-place update).

**KaneAI Goal:** "User can create a new issue report by providing a title, description, and category"

**Playwright Regression:** `test_sc_002_create_new_issue_report`

---

## AC-003: View Issue Details (PP-103)

**Scenario ID:** SC-003

**Criteria:**
- AC1: User can click or tap an issue row in the main list to open the detail view.
- AC2: The detail view displays the Issue Title prominently.
- AC3: The Status field is visible and shows the current status value.
- AC4: The Priority field is visible and shows the assigned priority.
- AC5: The full Description is visible (not truncated) in the detail view.
- AC6: Category and Submitted By fields are visible.
- AC7: The detail view does not lose context if the canvas re-renders.

**KaneAI Goal:** "User can view issue details including status, priority, and full description"

**Playwright Regression:** `test_sc_003_view_issue_details`

---

## AC-004: Filter Issues by Status (PP-104)

**Scenario ID:** SC-004

**Criteria:**
- AC1: A filter control is visible on the main issues list screen.
- AC2: The filter control offers Status values: Active, Pending, Resolved (at minimum).
- AC3: Selecting a status value refreshes the list to show only matching records.
- AC4: Records shown after filtering all have the selected status value.
- AC5: The filter label or control visually indicates which filter is active.
- AC6: Clearing the filter (selecting "All" or similar) restores the full list.

**KaneAI Goal:** "User can filter the issues list by status to see only active or resolved items"

**Playwright Regression:** `test_sc_004_filter_issues_by_status`

---

## AC-005: Navigate Back from Detail View (PP-105)

**Scenario ID:** SC-005

**Criteria:**
- AC1: A back navigation control is visible on the issue detail view screen.
- AC2: Activating the back control returns the user to the issues list screen.
- AC3: The issues list re-displays with the same records as before entering the detail view.
- AC4: The back navigation does not trigger a full app reload.
- AC5: The user can navigate to multiple detail views and back without the app entering an error state.

**KaneAI Goal:** "User can navigate back from an issue detail view to the main issues list"

**Playwright Regression:** `test_sc_005_navigate_back_from_detail_view`

---

## AC-006: Edit Submitted Issue Report (PP-106)

**Scenario ID:** SC-006

**Criteria:**
- AC1: An Edit action is accessible from the issue detail view for users with edit permissions.
- AC2: The edit form pre-populates with the current field values of the issue.
- AC3: User can modify the Title, Description, and/or Category fields.
- AC4: User can save the edited form without error.
- AC5: After saving, the detail view refreshes and shows the updated field values.
- AC6: The updated values are also reflected in the main issues list.
- AC7: The original creation date is preserved; the edit does not create a duplicate record.

**KaneAI Goal:** "User can edit a submitted issue report and see the updated details saved"

**Playwright Regression:** `test_sc_006_edit_submitted_issue_report`

---

## AC-007: Search Issues by Keyword (PP-107)

**Scenario ID:** SC-007

**Criteria:**
- AC1: A search input field is accessible on the main issues list screen.
- AC2: Entering a keyword in the search field filters the list in real-time or on submit.
- AC3: Results displayed contain the search keyword in the Title or Description.
- AC4: Records not matching the keyword are hidden from the list.
- AC5: The search is case-insensitive (searching "issue" matches "Issue").
- AC6: Clearing the search field or entering an empty string restores the full issues list.

**KaneAI Goal:** "User can search for an existing issue by keyword and see matching results"

**Playwright Regression:** `test_sc_007_search_existing_issues`

---

## AC-008: Validation Handling (PP-108)

**Scenario ID:** SC-008

**Criteria:**
- AC1: User can open the issue creation form and attempt to submit without filling any fields.
- AC2: The form does not submit when mandatory fields are empty.
- AC3: A validation message appears adjacent to the Title field when it is empty on submit.
- AC4: A validation message appears adjacent to the Category field when it is unselected on submit.
- AC5: A validation message appears adjacent to the Description field when it is empty on submit.
- AC6: Validation messages are descriptive (e.g., "This field is required" or similar).
- AC7: After filling all mandatory fields, the form submits successfully with no validation errors.

**KaneAI Goal:** "User can see a validation message when submitting a form with empty mandatory fields"

**Playwright Regression:** `test_sc_008_validation_handling`

---

## AC-009: Grid Interaction — Sorting and Pagination (PP-109)

**Scenario ID:** SC-009

**Criteria:**
- AC1: Column headers in the issues grid are interactive (clickable for sorting).
- AC2: Clicking a column header sorts the grid rows by that column in ascending order.
- AC3: Clicking the same column header again sorts in descending order (or toggles).
- AC4: A pagination control is visible when the number of records exceeds the page size.
- AC5: Navigating to page 2 displays a different set of records than page 1.
- AC6: Navigating back to page 1 restores the first set of records.
- AC7: Sorting persists across pagination — the sort order is applied to all pages.

**KaneAI Goal:** "User can interact with the issues grid — sorting columns and navigating pages"

**Playwright Regression:** `test_sc_009_grid_interaction`

---

## AC-010: Approver Workflow Navigation (PP-110)

**Scenario ID:** SC-010

**Criteria:**
- AC1: The app correctly identifies and presents the approver-specific view for users with approver role.
- AC2: The approver view shows a list of issues with status "Pending Review" or "Pending Approval".
- AC3: Each pending issue shows: Title, Submitter, Description summary, and submission date.
- AC4: An Approve action is available and activatable for each pending issue.
- AC5: A Reject action is available and activatable for each pending issue.
- AC6: After Approve is activated, the issue status changes to "Active" (or equivalent).
- AC7: After Reject is activated, the issue status changes to "Rejected" (or equivalent).
- AC8: The approver list refreshes after an action — the acted-upon issue is removed or updated.

**KaneAI Goal:** "User can access the approver workflow view and see issues pending approval"

**Playwright Regression:** `test_sc_010_approver_workflow_navigation`

---

## Summary Table

| AC ID | Scenario | KaneAI Goal (Summary) | Playwright Test Function |
|---|---|---|---|
| AC-001 | SC-001 | Navigate to app — issues list visible | `test_sc_001_navigate_to_app_and_see_issues_list` |
| AC-002 | SC-002 | Create issue — record appears after submit | `test_sc_002_create_new_issue_report` |
| AC-003 | SC-003 | View details — status, priority, desc shown | `test_sc_003_view_issue_details` |
| AC-004 | SC-004 | Filter by status — matching items only | `test_sc_004_filter_issues_by_status` |
| AC-005 | SC-005 | Navigate back — issues list re-displays | `test_sc_005_navigate_back_from_detail_view` |
| AC-006 | SC-006 | Edit issue — updated details saved | `test_sc_006_edit_submitted_issue_report` |
| AC-007 | SC-007 | Search keyword — matching results shown | `test_sc_007_search_existing_issues` |
| AC-008 | SC-008 | Empty form submit — validation appears | `test_sc_008_validation_handling` |
| AC-009 | SC-009 | Grid sort + paginate — records respond | `test_sc_009_grid_interaction` |
| AC-010 | SC-010 | Approver view — pending + actions shown | `test_sc_010_approver_workflow_navigation` |
