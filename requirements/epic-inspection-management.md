# Epic: Issue and Inspection Management
## Microsoft Teams Power Apps — IssueReporting Template

---

## Epic Overview

| Field | Value |
|---|---|
| **Epic ID** | PP-EPIC-001 |
| **Epic Name** | Issue and Inspection Management |
| **Product** | IssueReporting Power App (Microsoft Teams) |
| **Owner** | Operations Team / QA Architect |
| **Priority** | P1 — Critical |
| **Business Value** | Improves operational visibility, reduces issue resolution time, enables audit compliance |
| **Risk Level** | HIGH — role-based access, M365 integration, dynamic canvas UI |
| **Sprint Target** | Sprint 1 (10 acceptance criteria, 10 automated test scenarios) |

---

## Business Objective

Enable operations teams to report, track, and resolve operational issues efficiently through a structured Power Apps workflow deployed in Microsoft Teams. The solution must support multi-role workflows (submitters, reviewers, approvers), enforce data validation, and provide full audit visibility across the issue lifecycle.

---

## Scope

This epic covers functional QA of the IssueReporting Power App across the following workflow areas:

1. **Issue Submission** — Creation, form validation, mandatory field enforcement
2. **Issue Tracking** — List view, search, filtering, status transitions
3. **Issue Detail Management** — Detail view, edit capability, history retention
4. **Navigation and UX** — Back navigation, grid interaction, responsive canvas behaviour
5. **Role-Based Workflows** — Approver view, pending approvals, approve/reject actions

---

## User Stories Contained

| Story ID | Title | Priority |
|---|---|---|
| PP-101 | Navigate to App and View Issues List | P1 |
| PP-102 | Create New Issue Report | P1 |
| PP-103 | View Issue Details | P1 |
| PP-104 | Filter Issues by Status | P2 |
| PP-105 | Navigate Back from Detail View | P2 |
| PP-106 | Edit Submitted Issue Report | P2 |
| PP-107 | Search Issues by Keyword | P2 |
| PP-108 | Form Validation Handling | P1 |
| PP-109 | Grid Interaction (Sort + Paginate) | P3 |
| PP-110 | Approver Workflow Navigation | P1 |

---

## Dependencies

- Microsoft 365 environment with Power Apps licence
- IssueReporting app template deployed from [github.com/microsoft/teams-powerapps-app-templates](https://github.com/microsoft/teams-powerapps-app-templates)
- LambdaTest account with KaneAI and HyperExecute access
- M365 test accounts: one submitter role, one approver role
- `POWERAPPS_URL` environment variable pointing to deployed app

---

## Acceptance Criteria Summary

All 10 acceptance criteria are defined in `requirements/acceptance-criteria.md`.
They are consumed directly by the Agentic STLC pipeline from `requirements/search.txt`.

---

## Technical Context: Why Power Apps QA Is Hard

Power Apps renders a canvas-based UI where:
- Element IDs (`data-control-id`) are **dynamically generated at runtime** and regenerate on every solution publish
- Layout shifts between **user roles** — approver UI differs completely from submitter UI
- M365 authentication must complete before the app canvas loads
- Canvas re-renders are async — no standard DOM ready events

**Traditional automation consequence:** Playwright Codegen captures runtime-generated element IDs that are invalid after the next Power Apps Studio publish. Tests require re-recording or manual locator updates every sprint.

**Agentic STLC approach:** KaneAI navigates by goal-directed intent (button labels, field context, observable behaviour) rather than element IDs. Generated Playwright regression tests use semantic locators (`get_by_role()`, `get_by_text()`, `get_by_label()`). Both layers survive solution publish cycles without manual intervention.

---

## Release Criteria

| Threshold | Verdict |
|---|---|
| ≥ 90% of acceptance criteria pass (both Kane + HyperExecute) | GREEN — Release approved |
| 75–89% pass rate | YELLOW — Review failures before release |
| < 75% pass rate | RED — Release blocked |

Pipeline time target: **under 5 minutes** from git push to release verdict.
