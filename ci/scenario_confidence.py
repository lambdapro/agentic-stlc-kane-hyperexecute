"""
Scenario Confidence Analysis Engine — Stage 2b Intelligence Layer.

Evaluates how confident we are that generated scenarios are SUFFICIENT to
validate each requirement completely.  Reasons across:

  - Happy path coverage (scenario exists + Kane AI validated)
  - Negative testing presence (invalid inputs, error states)
  - Edge case coverage (boundaries, empty states, duplicates)
  - Recovery flow coverage (undo, retry, back navigation)
  - Execution readiness (Kane AI result + Playwright body quality)
  - Platform coverage (mobile / Android)
  - Regression risk (feature criticality + single-scenario dependency)

Confidence levels (deterministic, not percentage-based):
  VERY_HIGH | HIGH | MEDIUM | LOW | CRITICAL_GAP

Produces:
  reports/scenario-confidence-report.json
  reports/requirement-confidence-summary.md
  reports/coverage-gap-analysis.json
  reports/high-risk-requirements.json
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))
from stage_utils import print_stage_header, print_stage_result

# ── Feature taxonomy ──────────────────────────────────────────────────────────
FEATURE_KEYWORDS: dict[str, list[str]] = {
    "SEARCH":         ["search", "find product", "search bar", "search result", "search for"],
    "CART":           ["cart", "add to cart", "shopping cart", "remove from cart",
                       "update quantity", "cart item", "line total", "cart update"],
    "CATALOG":        ["catalog", "laptops", "product listing", "product catalog",
                       "browse", "category", "grid", "product grid"],
    "FILTER":         ["filter", "manufacturer", "brand filter", "narrow", "sidebar"],
    "PRODUCT_DETAIL": ["product detail", "detail page", "product name", "price",
                       "thumbnail", "product page", "open a product", "click a product"],
    "GUEST":          ["guest", "without logging in", "guest browsing"],
    "AUTH":           ["register", "log in", "login", "log out", "logout",
                       "account", "first name", "last name", "telephone",
                       "password", "dashboard", "registered"],
    "CHECKOUT":       ["checkout", "shipping", "flat rate", "shipping address",
                       "complete a guest checkout"],
    "WISHLIST":       ["wish list", "wishlist"],
    "SORT":           ["sort", "price low to high", "listing order"],
}

FEATURE_CRITICALITY: dict[str, str] = {
    "AUTH":           "HIGH",
    "CHECKOUT":       "HIGH",
    "CART":           "HIGH",
    "SEARCH":         "MEDIUM",
    "CATALOG":        "MEDIUM",
    "PRODUCT_DETAIL": "MEDIUM",
    "FILTER":         "LOW",
    "SORT":           "LOW",
    "WISHLIST":       "LOW",
    "GUEST":          "LOW",
    "GENERAL":        "LOW",
}

# ── Scenario-type detection keywords ─────────────────────────────────────────
_NEGATIVE_KW = frozenset([
    "invalid", "error", "fail", "reject", "empty", "negative", "incorrect",
    "wrong", "missing", "cannot", "unable", "remove", "delete", "out of stock",
    "unauthorized", "no results", "not found", "forbidden", "limit",
])
_EDGE_CASE_KW = frozenset([
    "empty cart", "zero", "minimum", "maximum", "boundary",
    "duplicate", "special character", "persistence", "concurrent", "timeout",
])
_RECOVERY_KW = frozenset(["retry", "recover", "back", "undo", "revert", "redirect"])
_MOBILE_BROWSERS = frozenset(["android", "ios", "safari_mobile", "mobile"])

# ── Fallback Playwright body signature (from agent.py _FALLBACK_BODY) ─────────
_FALLBACK_BODY_SIGNATURE = 'assert page.title().strip() != "", "Page failed to load"'

# ── Feature-specific expert gap knowledge ────────────────────────────────────
# These are what a Principal QA Architect would call out as EXPECTED coverage
# that is MISSING from a feature — not derived from the description text.
_EXPECTED_GAPS: dict[str, dict] = {
    "CART": {
        "negative":  "Add to cart with required product option unselected; empty cart state behavior",
        "edge_case": "Add same product twice; update quantity to 0; max quantity boundary; concurrent add",
        "recovery":  "Remove item from cart; clear cart and verify empty state",
        "mobile":    "Cart add / view / remove on mobile viewport (touch interactions)",
    },
    "CHECKOUT": {
        "negative":  "Invalid shipping address; missing required checkout field; declined payment",
        "edge_case": "Guest checkout flow when unauthenticated; session timeout during checkout",
        "recovery":  "Return to cart from checkout; edit shipping details and re-submit",
        "mobile":    "Complete guest checkout on mobile device (form input on small screen)",
    },
    "AUTH": {
        "negative":  "Login with wrong password; register with duplicate email; missing required field",
        "edge_case": "Password boundary (min/max length); special characters in username field",
        "recovery":  "Logout and re-login; session recovery after expiry",
        "mobile":    "Login and registration forms on mobile viewport",
    },
    "SEARCH": {
        "negative":  "Search query that returns zero results; submit empty search string",
        "edge_case": "Search with special characters (%, &, #); very long query (>100 chars)",
        "recovery":  "Clear search and return to full catalog; search from result page",
    },
    "CATALOG": {
        "negative":  "Navigate to empty/invalid category URL",
        "edge_case": "Pagination through multiple pages; category with large product set (scroll load)",
        "recovery":  "Navigate back from product detail to catalog with filters intact",
    },
    "PRODUCT_DETAIL": {
        "negative":  "Product with required option (size/color) not selected before Add to Cart",
        "edge_case": "Out-of-stock product detail page; product with multiple image variants",
        "recovery":  "Navigate back from detail page to product listing",
    },
    "FILTER": {
        "negative":  "Apply brand filter that returns zero results",
        "edge_case": "Remove applied filter and verify all products return; combine multiple filters",
        "recovery":  "Reset filters and verify full product list restored",
    },
    "WISHLIST": {
        "negative":  "Add already-wishlisted product (duplicate behavior check)",
        "edge_case": "Wishlist persistence after logout and re-login; empty wishlist state",
        "recovery":  "Remove item from wishlist; navigate back to product after wishlist add",
    },
    "SORT": {
        "negative":  "Sort applied on category with only one product",
        "edge_case": "Sort stability — products with identical price remain in consistent order",
    },
    "GUEST": {
        "negative":  "Access account/order-history page without login (redirect to login page)",
        "edge_case": "Browse as guest then proceed to checkout — guest-checkout vs login prompt",
        "recovery":  "Return to homepage after being redirected from protected page",
    },
}


# ── Feature classification ────────────────────────────────────────────────────
def _classify_feature(text: str) -> str:
    text_lower = text.lower()
    best, best_n = "GENERAL", 0
    for feat, kws in FEATURE_KEYWORDS.items():
        n = sum(1 for kw in kws if kw in text_lower)
        if n > best_n:
            best_n, best = n, feat
    return best


# ── Playwright body quality ───────────────────────────────────────────────────
def _body_is_substantive(sc_id: Optional[str], playwright_bodies: dict) -> bool:
    """Returns True when the scenario has a curated Playwright body, not just the fallback."""
    if not sc_id:
        return False
    body = playwright_bodies.get(sc_id, "")
    if not body:
        return False
    return _FALLBACK_BODY_SIGNATURE not in body


# ── Gap detection (expert QA reasoning) ──────────────────────────────────────
def _detect_coverage_gaps(
    feature: str,
    criticality: str,
    description: str,
    all_scenario_texts: list,
    kane_passed: bool,
    has_playwright_body: bool,
) -> tuple:
    """
    Returns (gaps: list[str], recommendations: list[str]).

    Gaps describe WHAT is missing.
    Recommendations describe WHAT to add.
    Reasoning: a QA architect would flag these regardless of whether the
    requirement description uses negative keywords — expert knowledge about
    each feature's required coverage scope drives the gaps.
    """
    gaps = []
    recs = []

    # Combined text includes description + all scenario descriptions for this req
    combined = " ".join(all_scenario_texts + [description]).lower()

    has_negative = any(kw in combined for kw in _NEGATIVE_KW)
    has_edge_case = any(kw in combined for kw in _EDGE_CASE_KW)
    has_recovery = any(kw in combined for kw in _RECOVERY_KW)

    fgaps = _EXPECTED_GAPS.get(feature, {})

    # ── Kane AI failure is always a gap ───────────────────────────────────────
    if not kane_passed:
        gaps.append(
            "Kane AI functional verification failed — happy path behavior not validated by live-site agent"
        )
        recs.append(
            "Investigate Kane AI failure; re-run after fixing site interaction or kane objective"
        )

    # ── Negative testing ──────────────────────────────────────────────────────
    if not has_negative:
        neg_desc = fgaps.get("negative", "No invalid-input or error-state scenarios present")
        if criticality == "HIGH":
            gaps.append(f"CRITICAL: No negative test coverage — {neg_desc}")
            recs.append(f"Add negative scenarios: {neg_desc}")
        elif criticality == "MEDIUM":
            gaps.append(f"Missing negative test coverage — {neg_desc}")
            recs.append(f"Add at least one negative scenario: {neg_desc}")
        else:
            gaps.append(f"No negative scenarios (acceptable for {criticality}-criticality feature, but consider: {neg_desc})")

    # ── Edge case coverage ────────────────────────────────────────────────────
    if not has_edge_case and criticality in ("HIGH", "MEDIUM"):
        edge_desc = fgaps.get("edge_case", "No boundary-condition or empty-state scenarios")
        gaps.append(f"Missing edge case coverage — {edge_desc}")
        recs.append(f"Add edge case scenarios: {edge_desc}")

    # ── Recovery flows (only block HIGH criticality) ──────────────────────────
    if not has_recovery and criticality == "HIGH":
        rec_desc = fgaps.get("recovery", "No recovery or state-reset flow covered")
        gaps.append(f"Missing recovery flow — {rec_desc}")
        recs.append(f"Add recovery scenarios: {rec_desc}")

    # ── Mobile coverage (flag for HIGH/MEDIUM) ────────────────────────────────
    mob_desc = fgaps.get("mobile", f"No mobile/Android coverage for {feature} feature")
    if criticality in ("HIGH", "MEDIUM"):
        gaps.append(f"No mobile/Android coverage — {mob_desc}")
        recs.append(f"Add a mobile browser run for {feature} scenarios via BROWSERS env var")

    # ── Playwright body quality ───────────────────────────────────────────────
    if not has_playwright_body:
        gaps.append(
            "Playwright test uses generic fallback body (page load assertion only) — "
            "assertions are insufficient for meaningful regression"
        )
        recs.append(
            "Implement a feature-specific Playwright body in PLAYWRIGHT_BODIES "
            "with meaningful UI interaction and state assertions"
        )

    return gaps, recs


# ── Confidence level determination ────────────────────────────────────────────
def _compute_confidence_level(
    criticality: str,
    kane_passed: bool,
    has_negative: bool,
    has_edge_case: bool,
    has_playwright_body: bool,
    scenario_exists: bool,
) -> str:
    """
    Deterministic confidence level from feature criticality + coverage dimensions.

    Rule table (first-match per criticality tier):

      HIGH criticality:
        Kane:pass + negative:yes              → HIGH
        Kane:pass + negative:no               → MEDIUM
        Kane:fail + negative:yes              → MEDIUM
        Kane:fail + negative:no               → LOW

      MEDIUM criticality:
        Kane:pass + negative:yes              → VERY_HIGH
        Kane:pass + negative:no               → HIGH
        Kane:fail + negative:yes              → MEDIUM
        Kane:fail + negative:no               → LOW

      LOW criticality:
        Kane:pass                             → VERY_HIGH
        Kane:fail + negative:yes              → HIGH
        Kane:fail + negative:no               → MEDIUM

      No scenario at all:                     → CRITICAL_GAP
    """
    if not scenario_exists:
        return "CRITICAL_GAP"

    if criticality == "HIGH":
        if kane_passed and has_negative:
            return "HIGH"
        if kane_passed and not has_negative:
            return "MEDIUM"
        if not kane_passed and has_negative:
            return "MEDIUM"
        return "LOW"  # Kane failed + no negative

    if criticality == "MEDIUM":
        if kane_passed and has_negative:
            return "VERY_HIGH"
        if kane_passed and not has_negative:
            return "HIGH"
        if not kane_passed and has_negative:
            return "MEDIUM"
        return "LOW"  # Kane failed + no negative

    # LOW criticality
    if kane_passed:
        return "VERY_HIGH"
    if has_negative:
        return "HIGH"
    return "MEDIUM"


# ── Risk assessment (LOW/CRITICAL_GAP only) ───────────────────────────────────
def _build_risk_assessment(
    confidence_level: str,
    feature: str,
    criticality: str,
    kane_passed: bool,
    gaps: list,
) -> Optional[dict]:
    if confidence_level not in ("LOW", "CRITICAL_GAP"):
        return None

    risk_areas = []
    probable_failures = []

    if not kane_passed:
        risk_areas.append(
            "Happy path not functionally validated — Kane AI could not complete the scenario flow"
        )
        probable_failures.append(
            f"{feature} core user journey may silently break in production without detection"
        )

    if any("negative" in g.lower() and "critical" in g.lower() for g in gaps):
        risk_areas.append("No invalid-input validation — error states untested")
        probable_failures.append(
            "Users submitting invalid data may encounter unhandled server errors or broken UI states"
        )

    if any("edge case" in g.lower() for g in gaps):
        risk_areas.append("Boundary conditions and concurrent-access states untested")
        probable_failures.append(
            "Edge inputs (zero quantity, max limit, duplicate submissions) may cause data corruption"
        )

    if any("mobile" in g.lower() for g in gaps) and criticality == "HIGH":
        risk_areas.append("No mobile/Android coverage on a HIGH-criticality feature")
        probable_failures.append(
            "Mobile users on touch devices may encounter broken interactions not caught by desktop tests"
        )

    if confidence_level == "LOW" and criticality == "HIGH":
        release_risk = (
            "HIGH — critical feature missing validation on happy path (Kane failed) "
            "or missing negative test coverage"
        )
        business_risk = (
            f"{feature} is core to the shopping experience; gaps increase probability "
            "of production incidents that affect revenue or user trust"
        )
    elif confidence_level == "CRITICAL_GAP":
        release_risk = "CRITICAL — no scenario maps to this requirement; zero automated coverage"
        business_risk = (
            f"{feature} feature has no automated validation; "
            "releasing without coverage violates QA governance"
        )
    else:
        release_risk = "MEDIUM — functional gaps present but not immediately blocking"
        business_risk = "Coverage gaps increase regression risk on non-critical paths"

    return {
        "business_risk":                business_risk,
        "release_risk":                 release_risk,
        "missing_validation_areas":     [g for g in gaps if "CRITICAL:" not in g],
        "probable_production_failures": probable_failures,
    }


# ── Per-requirement analysis ──────────────────────────────────────────────────
def analyze_scenario_confidence(
    requirement: dict,
    scenario: Optional[dict],
    all_scenarios: list,
    playwright_bodies: dict,
) -> dict:
    """
    Analyze confidence for a single requirement/scenario pair.

    Returns a structured confidence record.
    """
    req_id = requirement["id"]
    description = requirement.get("description", "")
    kane_status = requirement.get("kane_status", "unknown")
    kane_passed = kane_status == "passed"

    sc_id = scenario["id"] if scenario else None
    sc_status = scenario.get("status", "missing") if scenario else "missing"
    scenario_exists = scenario is not None and sc_status != "deprecated"

    feature = _classify_feature(description)
    criticality = FEATURE_CRITICALITY.get(feature, "LOW")

    # Gather all scenario source texts for this requirement
    req_scenario_texts = [
        sc.get("source_description", "") or sc.get("title", "")
        for sc in all_scenarios
        if sc.get("requirement_id") == req_id and sc.get("status") != "deprecated"
    ]
    combined_text = " ".join(req_scenario_texts + [description]).lower()

    # Coverage dimension detection
    has_negative = any(kw in combined_text for kw in _NEGATIVE_KW)
    has_edge_case = any(kw in combined_text for kw in _EDGE_CASE_KW)
    has_recovery = any(kw in combined_text for kw in _RECOVERY_KW)
    has_playwright_body = _body_is_substantive(sc_id, playwright_bodies)

    # Gap detection (expert QA reasoning)
    gaps, recommendations = _detect_coverage_gaps(
        feature=feature,
        criticality=criticality,
        description=description,
        all_scenario_texts=req_scenario_texts,
        kane_passed=kane_passed,
        has_playwright_body=has_playwright_body,
    )

    # Confidence level (deterministic rules)
    confidence_level = _compute_confidence_level(
        criticality=criticality,
        kane_passed=kane_passed,
        has_negative=has_negative,
        has_edge_case=has_edge_case,
        has_playwright_body=has_playwright_body,
        scenario_exists=scenario_exists,
    )

    # Risk assessment for problematic scenarios
    risk_assessment = _build_risk_assessment(
        confidence_level=confidence_level,
        feature=feature,
        criticality=criticality,
        kane_passed=kane_passed,
        gaps=gaps,
    )

    return {
        "requirement_id":      req_id,
        "scenario_id":         sc_id,
        "scenario_status":     sc_status,
        "acceptance_criterion": description,
        "feature":             feature,
        "criticality":         criticality,
        "kane_status":         kane_status,
        "confidence_level":    confidence_level,
        "coverage_dimensions": {
            "happy_path":      scenario_exists,
            "negative":        has_negative,
            "edge_case":       has_edge_case,
            "recovery":        has_recovery,
            "kane_verified":   kane_passed,
            "playwright_body": has_playwright_body,
            "mobile":          False,   # populated when mobile browsers are configured
            "android":         False,
        },
        "coverage_gaps":       gaps,
        "recommendations":     recommendations,
        "risk_assessment":     risk_assessment,
    }


# ── Full pipeline run ─────────────────────────────────────────────────────────
def run_confidence_analysis(
    requirements: list,
    scenarios: list,
    playwright_bodies: dict,
    output_dir: str = "reports",
) -> dict:
    """
    Run confidence analysis across all requirements and write all artifacts.

    Returns the full report dict (for callers that need it in-memory).
    """
    print_stage_header("2b", "SCENARIO_CONFIDENCE", "Intelligent scenario confidence analysis")
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    scenarios_by_req = {s["requirement_id"]: s for s in scenarios}

    records = []
    for req in requirements:
        scenario = scenarios_by_req.get(req["id"])
        record = analyze_scenario_confidence(
            requirement=req,
            scenario=scenario,
            all_scenarios=scenarios,
            playwright_bodies=playwright_bodies,
        )
        records.append(record)

    # ── Summary statistics ────────────────────────────────────────────────────
    total = len(records)
    by_level: dict = {}
    for r in records:
        lvl = r["confidence_level"]
        by_level[lvl] = by_level.get(lvl, 0) + 1

    high_confidence_count = sum(
        v for k, v in by_level.items() if k in ("VERY_HIGH", "HIGH")
    )
    critical_count = by_level.get("CRITICAL_GAP", 0) + by_level.get("LOW", 0)

    missing_negative = [r for r in records if not r["coverage_dimensions"]["negative"]]
    missing_edge = [
        r for r in records
        if not r["coverage_dimensions"]["edge_case"] and r["criticality"] in ("HIGH", "MEDIUM")
    ]
    kane_failed = [r for r in records if not r["coverage_dimensions"]["kane_verified"]]
    no_mobile = [
        r for r in records
        if not r["coverage_dimensions"]["mobile"] and r["criticality"] in ("HIGH", "MEDIUM")
    ]

    # Quality gate: HIGH criticality reqs must not be LOW/CRITICAL_GAP
    high_crit_low_confidence = [
        r for r in records
        if r["criticality"] == "HIGH"
        and r["confidence_level"] in ("LOW", "CRITICAL_GAP")
    ]
    confidence_gate_passed = len(high_crit_low_confidence) == 0

    quality_signals = {
        "critical_low_confidence_count":   critical_count,
        "high_criticality_low_confidence": [r["requirement_id"] for r in high_crit_low_confidence],
        "missing_negative_coverage_count": len(missing_negative),
        "missing_edge_case_count":         len(missing_edge),
        "kane_failures_count":             len(kane_failed),
        "no_mobile_coverage_count":        len(no_mobile),
        "high_confidence_count":           high_confidence_count,
        "confidence_gate_passed":          confidence_gate_passed,
    }

    summary = {
        "total_requirements":       total,
        "by_confidence_level":      by_level,
        "high_confidence_count":    high_confidence_count,
        "critical_gap_count":       critical_count,
        "missing_negative_coverage":  [r["requirement_id"] for r in missing_negative],
        "missing_edge_case_coverage": [r["requirement_id"] for r in missing_edge],
        "kane_failed_requirements":   [r["requirement_id"] for r in kane_failed],
        "no_mobile_coverage":         [r["requirement_id"] for r in no_mobile],
        "quality_signals":            quality_signals,
        "analyzed_at":                datetime.now(timezone.utc).isoformat(),
    }

    report = {"summary": summary, "records": records}

    # ── JSON artifacts ────────────────────────────────────────────────────────
    out = Path(output_dir)

    (out / "scenario-confidence-report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )

    (out / "coverage-gap-analysis.json").write_text(
        json.dumps({
            "missing_negative_coverage": [
                {
                    "requirement_id": r["requirement_id"],
                    "feature":        r["feature"],
                    "criticality":    r["criticality"],
                    "confidence":     r["confidence_level"],
                    "gaps": [g for g in r["coverage_gaps"] if "negative" in g.lower()],
                    "recommendation": next(
                        (rec for rec in r["recommendations"] if "negative" in rec.lower()),
                        ""
                    ),
                }
                for r in missing_negative
            ],
            "missing_edge_case_coverage": [
                {
                    "requirement_id": r["requirement_id"],
                    "feature":        r["feature"],
                    "criticality":    r["criticality"],
                    "confidence":     r["confidence_level"],
                    "gaps": [g for g in r["coverage_gaps"] if "edge" in g.lower()],
                    "recommendation": next(
                        (rec for rec in r["recommendations"] if "edge" in rec.lower()),
                        ""
                    ),
                }
                for r in missing_edge
            ],
            "kane_failures": [
                {
                    "requirement_id": r["requirement_id"],
                    "feature":        r["feature"],
                    "kane_status":    r["kane_status"],
                    "confidence":     r["confidence_level"],
                }
                for r in kane_failed
            ],
            "missing_mobile_coverage": [
                {
                    "requirement_id": r["requirement_id"],
                    "feature":        r["feature"],
                    "criticality":    r["criticality"],
                }
                for r in no_mobile
            ],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }, indent=2),
        encoding="utf-8",
    )

    high_risk = [r for r in records if r["confidence_level"] in ("LOW", "CRITICAL_GAP")]
    (out / "high-risk-requirements.json").write_text(
        json.dumps({
            "high_risk_count": len(high_risk),
            "requirements": [
                {
                    "requirement_id":  r["requirement_id"],
                    "confidence_level": r["confidence_level"],
                    "feature":         r["feature"],
                    "criticality":     r["criticality"],
                    "kane_status":     r["kane_status"],
                    "gaps":            r["coverage_gaps"],
                    "risk_assessment": r["risk_assessment"],
                }
                for r in high_risk
            ],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }, indent=2),
        encoding="utf-8",
    )

    # ── Markdown report ───────────────────────────────────────────────────────
    _write_markdown(records, summary, out / "requirement-confidence-summary.md")

    print_stage_result("2b", "SCENARIO_CONFIDENCE", {
        "Requirements analyzed": total,
        "VERY_HIGH":             by_level.get("VERY_HIGH", 0),
        "HIGH":                  by_level.get("HIGH", 0),
        "MEDIUM":                by_level.get("MEDIUM", 0),
        "LOW":                   by_level.get("LOW", 0),
        "CRITICAL_GAP":          by_level.get("CRITICAL_GAP", 0),
        "Confidence gate":       "PASSED" if confidence_gate_passed else "FAILED",
        "High-risk reqs":        len(high_risk),
        "Missing negative":      len(missing_negative),
    })

    return report


# ── Display helpers ───────────────────────────────────────────────────────────
def confidence_icon(level: str) -> str:
    return {
        "VERY_HIGH":    "🟢",
        "HIGH":         "🟡",
        "MEDIUM":       "🟠",
        "LOW":          "🔴",
        "CRITICAL_GAP": "🚨",
    }.get(level, "⚪")


# ── Markdown writer ───────────────────────────────────────────────────────────
def _write_markdown(records: list, summary: dict, path: Path) -> None:
    lines = [
        "# Scenario Confidence Analysis",
        "",
        "AI-driven quality/confidence assessment for each requirement → scenario mapping.",
        "Confidence is evaluated across: happy path, negative testing, edge cases,",
        "recovery flows, Kane AI execution, Playwright body quality, and platform coverage.",
        "",
        "## Summary",
        "",
        "| Level | Count | Meaning |",
        "|-------|-------|---------|",
        f"| 🟢 VERY_HIGH  | {summary['by_confidence_level'].get('VERY_HIGH', 0)} | All key dimensions covered; minor gaps acceptable |",
        f"| 🟡 HIGH       | {summary['by_confidence_level'].get('HIGH', 0)} | Core flow validated; some coverage classes missing |",
        f"| 🟠 MEDIUM     | {summary['by_confidence_level'].get('MEDIUM', 0)} | Happy path present but important gaps exist |",
        f"| 🔴 LOW        | {summary['by_confidence_level'].get('LOW', 0)} | Significant gaps; Kane failure or no negative tests |",
        f"| 🚨 CRITICAL_GAP | {summary['by_confidence_level'].get('CRITICAL_GAP', 0)} | No scenario mapped — zero automated coverage |",
        "",
        f"**High confidence:** {summary['high_confidence_count']}/{summary['total_requirements']} requirements",
        f"**Requiring attention (LOW + CRITICAL_GAP):** {summary['critical_gap_count']}",
        f"**Confidence gate:** {'✅ PASSED' if summary['quality_signals']['confidence_gate_passed'] else '❌ FAILED — HIGH criticality requirements have LOW/CRITICAL_GAP confidence'}",
        "",
        "## Requirement Confidence Table",
        "",
        "| Requirement | Scenario | Criticality | Confidence | Kane | Gaps | Recommendation |",
        "|-------------|----------|-------------|------------|------|------|----------------|",
    ]

    for r in records:
        icon = confidence_icon(r["confidence_level"])
        kane_icon = "✅" if r["coverage_dimensions"]["kane_verified"] else "❌"
        sc_id = r["scenario_id"] or "—"
        # Compact gaps for table: first gap only, truncated
        first_gap = r["coverage_gaps"][0][:75] + "…" if r["coverage_gaps"] else "No major gaps detected"
        first_rec = r["recommendations"][0][:65] + "…" if r["recommendations"] else "Ready for execution"
        lines.append(
            f"| `{r['requirement_id']}` | `{sc_id}` | {r['criticality']} "
            f"| {icon} {r['confidence_level']} | {kane_icon} {r['kane_status']} "
            f"| {first_gap} | {first_rec} |"
        )

    # HIGH-RISK section
    risky = [r for r in records if r["confidence_level"] in ("LOW", "CRITICAL_GAP")]
    if risky:
        lines.extend(["", "## High-Risk Requirement Analysis", ""])
        for r in risky:
            icon = confidence_icon(r["confidence_level"])
            lines.extend([
                f"### {icon} `{r['requirement_id']}` — {r['feature']} ({r['criticality']} criticality)",
                "",
                f"**Confidence:** {r['confidence_level']}  |  **Kane status:** {r['kane_status']}  |  "
                f"**Scenario:** {r['scenario_id'] or 'MISSING'}",
                "",
                "**Coverage Gaps:**",
            ])
            for gap in r["coverage_gaps"]:
                lines.append(f"- {gap}")
            lines.extend(["", "**Recommendations:**"])
            for rec in r["recommendations"]:
                lines.append(f"- {rec}")
            lines.append("")
            ra = r.get("risk_assessment")
            if ra:
                lines.extend([
                    "**Risk Assessment:**",
                    f"- **Business risk:** {ra['business_risk']}",
                    f"- **Release risk:** {ra['release_risk']}",
                ])
                if ra.get("probable_production_failures"):
                    lines.append("- **Probable production failures:**")
                    for pf in ra["probable_production_failures"]:
                        lines.append(f"  - {pf}")
                lines.append("")

    # Coverage gap summary
    missing_neg = [r for r in records if not r["coverage_dimensions"]["negative"]]
    missing_edge = [
        r for r in records
        if not r["coverage_dimensions"]["edge_case"] and r["criticality"] in ("HIGH", "MEDIUM")
    ]
    kane_failed = [r for r in records if not r["coverage_dimensions"]["kane_verified"]]

    lines.extend(["## Coverage Gap Summary", ""])

    if kane_failed:
        lines.extend(["### Kane AI Functional Verification Failures", ""])
        for r in kane_failed:
            lines.append(
                f"- 🔴 `{r['requirement_id']}` ({r['feature']}, {r['criticality']}) "
                "— core flow not validated by live-site agent"
            )
        lines.append("")

    if missing_neg:
        lines.extend(["### Missing Negative Test Coverage", ""])
        for r in missing_neg:
            fgap = _EXPECTED_GAPS.get(r["feature"], {}).get("negative", "Add invalid input scenarios")
            lines.append(f"- ❌ `{r['requirement_id']}` ({r['feature']}) — {fgap}")
        lines.append("")

    if missing_edge:
        lines.extend(["### Missing Edge Case Coverage", ""])
        for r in missing_edge:
            fgap = _EXPECTED_GAPS.get(r["feature"], {}).get("edge_case", "Add boundary and empty-state scenarios")
            lines.append(f"- 🟡 `{r['requirement_id']}` ({r['feature']}) — {fgap}")
        lines.append("")

    no_mobile = [
        r for r in records
        if not r["coverage_dimensions"]["mobile"] and r["criticality"] in ("HIGH", "MEDIUM")
    ]
    if no_mobile:
        lines.extend(["### Missing Mobile/Android Coverage", ""])
        for r in no_mobile:
            lines.append(
                f"- 📱 `{r['requirement_id']}` ({r['feature']}, {r['criticality']}) "
                "— no mobile browser in test matrix"
            )
        lines.append("")

    lines.extend([
        "## Scenario Expansion Recommendations",
        "",
        "To improve overall confidence, add these scenario types:",
        "",
    ])
    for r in records:
        if r["recommendations"]:
            lines.append(f"**`{r['requirement_id']}`** ({r['feature']}):")
            for rec in r["recommendations"][:3]:
                lines.append(f"  - {rec}")
    lines.append("")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ── Standalone entry point ────────────────────────────────────────────────────
def main() -> None:
    """
    Run confidence analysis as a standalone script.
    Reads from canonical pipeline artifact locations.
    """
    def load_json(p: str, default):
        fp = Path(p)
        if not fp.exists():
            return default
        try:
            return json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            return default

    requirements = load_json("requirements/analyzed_requirements.json", [])
    scenarios    = load_json("scenarios/scenarios.json", [])

    # When run standalone, playwright_bodies is unknown — use empty dict
    # (body-quality dimension will show False conservatively)
    run_confidence_analysis(
        requirements=requirements,
        scenarios=scenarios,
        playwright_bodies={},
    )


if __name__ == "__main__":
    main()
