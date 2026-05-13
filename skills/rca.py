"""
Skill 10: Root Cause Analysis (RCA)

Collects test failures, screenshots, videos, console logs, and network
traces from executed test sessions. Identifies probable failure causes
using pattern-matching against known failure signatures, then writes a
structured RCA report suitable for feeding into Claude or other AI agents.

Data sources (in priority order):
  1. JUnit XML failure messages + stack traces
  2. HyperExecute session logs (via api_details.json)
  3. Playwright traces / screenshots (if captured)
  4. Kane AI failure one-liners

Output:
  - reports/rca_report.json
  - reports/rca_summary.md
"""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .base import AgentSkill

_FAILURE_PATTERNS: list[tuple[str, str, str]] = [
    (r"TimeoutError|waiting for.*timeout",  "TIMEOUT",    "Element/page did not load within timeout — check selector or network latency"),
    (r"No element found|strict mode violation", "SELECTOR", "CSS/XPath selector mismatch — element may have been renamed or moved"),
    (r"net::ERR_|Failed to navigate|ERR_CONNECTION", "NETWORK", "Network error reaching target URL — check environment connectivity"),
    (r"401|403|Unauthorized|Forbidden",     "AUTH",       "Authentication/authorization failure — check credentials or session handling"),
    (r"500|502|503|Internal Server Error",  "SERVER",     "Target application returned server error — backend issue"),
    (r"AssertionError",                     "ASSERTION",  "Test assertion failed — actual state differs from expected state"),
    (r"StaleElementReferenceException|detached", "STALE_DOM", "DOM changed between element lookup and interaction — add explicit wait"),
    (r"ClickIntercepted|obscured|covered",  "OVERLAY",    "Element click intercepted by overlay/modal — dismiss overlay first"),
]


def _classify(message: str) -> tuple[str, str]:
    for pattern, category, advice in _FAILURE_PATTERNS:
        if re.search(pattern, message, re.IGNORECASE):
            return category, advice
    return "UNKNOWN", "Review logs and screenshots for manual investigation"


class RCASkill(AgentSkill):
    name = "rca"
    description = "Collect failures and produce structured root cause analysis report"
    version = "1.0.0"

    def run(self, **inputs: Any) -> dict:
        reports_dir = Path(self.reports_dir)
        reports_dir.mkdir(parents=True, exist_ok=True)

        failures = self._collect_junit_failures(reports_dir / "junit.xml")
        failures += self._collect_kane_failures(reports_dir)
        failures = self._enrich_with_he_sessions(failures, reports_dir / "api_details.json")

        summary = self._build_summary(failures)
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_failures": len(failures),
            "summary": summary,
            "failures": failures,
        }

        (reports_dir / "rca_report.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
        self._write_markdown(report, reports_dir / "rca_summary.md")

        return {
            "success": True,
            "total_failures": len(failures),
            "categories": list(summary.get("by_category", {}).keys()),
            "rca_report": str(reports_dir / "rca_report.json"),
        }

    # ── Collectors ────────────────────────────────────────────────────────────

    def _collect_junit_failures(self, junit_path: Path) -> list[dict]:
        if not junit_path.exists():
            return []
        failures = []
        try:
            tree = ET.parse(str(junit_path))
            for tc in tree.iter("testcase"):
                for el in tc.findall("failure") + tc.findall("error"):
                    msg = el.get("message", "") + "\n" + (el.text or "")
                    category, advice = _classify(msg)
                    failures.append({
                        "source": "playwright",
                        "test":   tc.get("name", ""),
                        "classname": tc.get("classname", ""),
                        "message": msg[:500],
                        "category": category,
                        "advice": advice,
                        "session_url": "",
                    })
        except ET.ParseError:
            pass
        return failures

    def _collect_kane_failures(self, reports_dir: Path) -> list[dict]:
        req_path = Path("requirements/analyzed_requirements.json")
        if not req_path.exists():
            return []
        failures = []
        reqs = json.loads(req_path.read_text(encoding="utf-8"))
        for r in reqs:
            if r.get("kane_status") == "failed":
                one_liner = r.get("kane_one_liner", "Kane AI functional verification failed")
                category, advice = _classify(one_liner)
                failures.append({
                    "source": "kaneai",
                    "requirement_id": r.get("id", ""),
                    "message": one_liner,
                    "category": category,
                    "advice": advice,
                    "session_url": r.get("kane_session_url", ""),
                })
        return failures

    def _enrich_with_he_sessions(self, failures: list[dict], api_path: Path) -> list[dict]:
        if not api_path.exists():
            return failures
        api = json.loads(api_path.read_text(encoding="utf-8"))
        tasks = api.get("he_tasks", [])
        session_by_test: dict[str, str] = {}
        for t in tasks:
            name = t.get("testName", t.get("name", ""))
            url  = t.get("sessionUrl", t.get("session_url", ""))
            if name and url:
                session_by_test[name] = url
        for f in failures:
            if not f.get("session_url") and f.get("test"):
                f["session_url"] = session_by_test.get(f["test"], "")
        return failures

    # ── Report builders ───────────────────────────────────────────────────────

    def _build_summary(self, failures: list[dict]) -> dict:
        by_cat: dict[str, int] = {}
        by_src: dict[str, int] = {}
        for f in failures:
            by_cat[f.get("category", "UNKNOWN")] = by_cat.get(f.get("category", "UNKNOWN"), 0) + 1
            by_src[f.get("source", "unknown")]   = by_src.get(f.get("source", "unknown"), 0) + 1
        return {"by_category": by_cat, "by_source": by_src}

    def _write_markdown(self, report: dict, path: Path) -> None:
        lines = [
            "# Root Cause Analysis Report",
            "",
            f"**Generated:** {report['generated_at']}  ",
            f"**Total failures:** {report['total_failures']}",
            "",
            "## Failure Categories",
            "",
        ]
        by_cat = report["summary"].get("by_category", {})
        for cat, count in sorted(by_cat.items(), key=lambda x: -x[1]):
            lines.append(f"- **{cat}**: {count}")
        lines += ["", "## Failure Details", ""]
        for f in report["failures"]:
            src = f.get("source", "unknown")
            test = f.get("test") or f.get("requirement_id", "")
            cat = f.get("category", "UNKNOWN")
            advice = f.get("advice", "")
            url = f.get("session_url", "")
            lines.append(f"### [{src.upper()}] {test}")
            lines.append(f"**Category:** {cat}  ")
            lines.append(f"**Advice:** {advice}  ")
            if url:
                lines.append(f"**Session:** [{url}]({url})  ")
            lines.append(f"**Message:** `{f.get('message', '')[:200]}`")
            lines.append("")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
