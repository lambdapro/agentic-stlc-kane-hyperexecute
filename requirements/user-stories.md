# User Stories — IssueReporting Power App
## Microsoft Teams Power Apps Template | Enterprise QA Requirements

---

## PP-101: Navigate to App and View Issues List

**Epic:** PP-EPIC-001 — Issue and Inspection Management
**Priority:** P1 — Critical
**Business Value:** Users must be able to reach the app and immediately see existing issues to assess team workload and outstanding items.
**Risk Level:** MEDIUM — M365 authentication and canvas load timing

**User Story:**
As a team member,
I want to navigate to the IssueReporting app in Microsoft Teams and see the issues list,
so that I can get an immediate view of open and resolved issues.

**Workflow Description:**
User opens Microsoft Teams, navigates to the IssueReporting tab, completes M365 authentication if required, and sees the main issues list populated with existing records including column headers (Title, Status, Priority, Category, Submitted By, Date).

**Dependencies:** M365 authentication, app deployment, existing data in Dataverse

---

## PP-102: Create New Issue Report

**Epic:** PP-EPIC-001 — Issue and Inspection Management
**Priority:** P1 — Critical
**Business Value:** Core value proposition of the app — enables team members to report operational issues without manual email or spreadsheet workflows.
**Risk Level:** HIGH — multi-step canvas form, dynamic field rendering, Dataverse write operation

**User Story:**
As a team member,
I want to create a new issue report by filling in a title, description, and category,
so that the issue is formally tracked and visible to the team and management.

**Workflow Description:**
User clicks 'New Issue' action on the main list screen. A creation form appears with mandatory fields: Title, Category (dropdown), Description (multiline text). User fills all fields and submits. The form closes and the new issue record appears in the list with status "Pending" and the current timestamp.

**Dependencies:** PP-101 (navigation), Dataverse write permissions, form validation (PP-108)

---

## PP-103: View Issue Details

**Epic:** PP-EPIC-001 — Issue and Inspection Management
**Priority:** P1 — Critical
**Business Value:** Users need to see full context of an issue — status, priority, description, submitter — to make decisions and take action.
**Risk Level:** MEDIUM — canvas navigation, detail view layout differs from list view

**User Story:**
As a team member,
I want to click on an issue in the list and see its full details including status, priority, and description,
so that I can understand the issue context before taking action.

**Workflow Description:**
User taps or clicks on any issue row in the main list. The detail view screen loads showing: Issue Title, Status badge, Priority level, Full Description, Category, Submitted By, and Creation Date. All fields are read-only unless the user has edit permissions.

**Dependencies:** PP-101 (navigation), PP-102 (issue exists), PP-105 (back navigation)

---

## PP-104: Filter Issues by Status

**Epic:** PP-EPIC-001 — Issue and Inspection Management
**Priority:** P2 — High
**Business Value:** Managers and team leads need to view specific subsets of issues — only active, only resolved — without scrolling through unrelated records.
**Risk Level:** MEDIUM — canvas filter component, dynamic list refresh

**User Story:**
As a team lead,
I want to filter the issues list by status (Active, Pending, Resolved),
so that I can focus on the subset of issues relevant to my current workflow.

**Workflow Description:**
User selects a Status value from the filter control on the main list screen. The issues grid refreshes to show only records matching the selected status. The filter label updates to indicate active filter. Record count reflects the filtered subset.

**Dependencies:** PP-101 (navigation), existing records with varied statuses

---

## PP-105: Navigate Back from Detail View

**Epic:** PP-EPIC-001 — Issue and Inspection Management
**Priority:** P2 — High
**Business Value:** Standard navigation pattern — users must be able to return to the issues list from any detail view without losing their filter state.
**Risk Level:** MEDIUM — canvas back navigation differs from browser back; iframe context

**User Story:**
As a team member,
I want to navigate back from an issue detail view to the main issues list,
so that I can continue reviewing other issues without reloading the app.

**Workflow Description:**
User viewing an issue detail screen activates the back navigation control (Back button, breadcrumb, or swipe gesture). The issues list re-displays with all previously visible records. Previously applied filters are preserved where the app supports it.

**Dependencies:** PP-101 (navigation), PP-103 (detail view loaded)

---

## PP-106: Edit Submitted Issue Report

**Epic:** PP-EPIC-001 — Issue and Inspection Management
**Priority:** P2 — High
**Business Value:** Issues evolve — status changes, descriptions are clarified, categories are reassigned. Users need to update records without creating duplicates.
**Risk Level:** HIGH — edit modal differs from create form; write-back to Dataverse; optimistic lock conflicts

**User Story:**
As a team member with edit permissions,
I want to edit an existing issue report,
so that I can update the status, correct the description, or change the category after initial submission.

**Workflow Description:**
User opens an issue detail view and activates the Edit action. The edit form pre-populates with existing field values. User modifies one or more fields and saves. The detail view refreshes showing the updated values. The change is reflected in the issues list.

**Dependencies:** PP-101, PP-103 (detail view), Dataverse update permissions

---

## PP-107: Search Issues by Keyword

**Epic:** PP-EPIC-001 — Issue and Inspection Management
**Priority:** P2 — High
**Business Value:** Users managing large volumes of issues need to find specific records quickly without manual scrolling or filtering.
**Risk Level:** MEDIUM — search control availability varies by Power App version; canvas search behaviour

**User Story:**
As a team member,
I want to search the issues list by keyword,
so that I can quickly find a specific issue without scrolling through all records.

**Workflow Description:**
User enters a keyword in the search field on the main issues list. The list filters in real-time (or on submit) to show only records where the Title or Description contains the search term. The search is case-insensitive. Clearing the search field restores the full list.

**Dependencies:** PP-101 (navigation), existing records with searchable content

---

## PP-108: Form Validation Handling

**Epic:** PP-EPIC-001 — Issue and Inspection Management
**Priority:** P1 — Critical
**Business Value:** Data quality requirement — mandatory fields must be enforced at the UI layer to prevent incomplete records from entering Dataverse.
**Risk Level:** HIGH — validation message element IDs are dynamic; validation timing varies with canvas re-render

**User Story:**
As the system,
I want to display clear validation messages when a user attempts to submit a form with empty mandatory fields,
so that data quality is enforced and users understand what is required before submission.

**Workflow Description:**
User opens the issue creation form and attempts to submit without filling mandatory fields (Title, Category, Description). For each empty mandatory field, a validation message appears adjacent to the field. The form does not submit. User fills the required fields and resubmits successfully.

**Dependencies:** PP-102 (create form), form rendering and validation framework

---

## PP-109: Grid Interaction — Sorting and Pagination

**Epic:** PP-EPIC-001 — Issue and Inspection Management
**Priority:** P3 — Medium
**Business Value:** Power users and managers working with large issue volumes need to sort by priority, date, or status and navigate across pages.
**Risk Level:** HIGH — grid component structure changes with Power Apps updates; row index selectors are fragile

**User Story:**
As a team lead,
I want to sort the issues grid by column headers and navigate between pages,
so that I can efficiently review and prioritise large volumes of issues.

**Workflow Description:**
User clicks a column header (e.g., Priority, Date Created) to sort the grid. Row order changes to reflect the sort. User navigates to page 2 using the pagination control. A different set of records is displayed. Navigating back to page 1 restores the original records.

**Dependencies:** PP-101 (navigation), sufficient records to trigger pagination (>10)

---

## PP-110: Approver Workflow Navigation

**Epic:** PP-EPIC-001 — Issue and Inspection Management
**Priority:** P1 — Critical
**Business Value:** Approval workflows are core to enterprise issue management — managers must be able to review, approve, or reject submitted issues.
**Risk Level:** CRITICAL — role-based UI layout differs entirely from submitter view; requires approver-role M365 account

**User Story:**
As an approver,
I want to access the approver workflow view and see issues pending my approval,
so that I can approve or reject submitted issues and progress them through the resolution workflow.

**Workflow Description:**
User with approver role navigates to the IssueReporting app. The app detects the approver role and presents the approver-specific view, which shows issues in "Pending Review" status. Each issue shows the submitter, description summary, and available actions: Approve (moves to Active) and Reject (moves to Rejected). The approver selects an action and the issue status updates immediately.

**Dependencies:** PP-101 (navigation), M365 approver-role account, existing issues in "Pending" status, role-based app configuration in Power Apps
