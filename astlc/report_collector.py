"""
ReportCollector — download and parse CI artifacts into a structured summary.

Downloads GitHub Actions artifacts (junit.xml, traceability_matrix.json,
quality_gates.json, report.html) and parses them into a dict suitable
for ChatReporter.execution_summary().
"""
from __future__ import annotations

import io
import json
import os
import sys
import zipfile
from pathlib import Path
from typing import Any, Callable

UpdateFn = Callable[[str], None]


class ReportCollector:
    """Downloads and parses CI artifacts from a GitHub Actions run."""

    _GITHUB_API = "https://api.github.com"

    def __init__(
        self,
        github_token: str = "",
        repo_slug: str = "",
        reports_dir: str | Path = "reports",
        on_update: UpdateFn | None = None,
    ) -> None:
        self._token      = github_token or os.environ.get("GITHUB_TOKEN", "")
        self._repo       = repo_slug
        self._reports    = Path(reports_dir)
        self._on_update  = on_update or (lambda _: None)

    # ── Public ────────────────────────────────────────────────────────────────

    def collect(self, run_id: str) -> dict:
        """
        Download all artifacts from a GitHub Actions run and parse them.

        Returns:
          {
            "execution":    { passed, failed, flaky, total },
            "coverage":     { coverage_pct, total_requirements, covered_full },
            "quality_gates": { gates_passed, critical_failures, warnings, gates },
            "rca":          { failures: [...] },
            "links":        { playwright_report, traceability_matrix },
            "artifacts_downloaded": int,
          }
        """
        if not run_id:
            return self._local_fallback()

        self._emit(f"Downloading artifacts from run #{run_id}...")
        self._reports.mkdir(parents=True, exist_ok=True)

        downloaded = self._download_artifacts(run_id)
        self._emit(f"Downloaded {downloaded} artifact(s).")

        return self._parse_local_reports()

    def collect_from_local(self) -> dict:
        """Parse whatever report files already exist locally (no download)."""
        return self._parse_local_reports()

    # ── Download ──────────────────────────────────────────────────────────────

    def _download_artifacts(self, run_id: str) -> int:
        try:
            import httpx
        except ImportError:
            self._emit("httpx not installed — cannot download artifacts")
            return 0

        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        artifacts_url = f"{self._GITHUB_API}/repos/{self._repo}/actions/runs/{run_id}/artifacts"
        downloaded = 0

        try:
            resp = httpx.get(artifacts_url, headers=headers, timeout=30)
            if resp.status_code != 200:
                self._emit(f"Could not list artifacts (HTTP {resp.status_code})")
                return 0

            for artifact in resp.json().get("artifacts", []):
                name     = artifact.get("name", "")
                dl_url   = artifact.get("archive_download_url", "")
                if not dl_url:
                    continue

                try:
                    dl_resp = httpx.get(dl_url, headers=headers, timeout=60, follow_redirects=True)
                    if dl_resp.status_code == 200:
                        dest = self._reports / name
                        dest.mkdir(parents=True, exist_ok=True)
                        with zipfile.ZipFile(io.BytesIO(dl_resp.content)) as zf:
                            zf.extractall(str(dest))
                        self._emit(f"  Extracted artifact '{name}' -> {dest}/")
                        downloaded += 1
                    else:
                        self._emit(f"  Failed to download artifact '{name}' (HTTP {dl_resp.status_code})")
                except Exception as exc:
                    self._emit(f"  Error downloading '{name}': {exc}")

        except Exception as exc:
            self._emit(f"Artifact download failed: {exc}")

        return downloaded

    # ── Parsing ───────────────────────────────────────────────────────────────

    def _parse_local_reports(self) -> dict:
        result: dict[str, Any] = {
            "execution":         {},
            "coverage":          {},
            "quality_gates":     {},
            "rca":               {"failures": []},
            "links":             {},
            "artifacts_downloaded": 0,
        }

        self._parse_junit(result)
        self._parse_traceability(result)
        self._parse_quality_gates(result)
        self._parse_rca(result)
        self._parse_confidence(result)
        self._build_links(result)

        return result

    def _parse_junit(self, result: dict) -> None:
        junit_candidates = list(self._reports.rglob("junit.xml"))
        if not junit_candidates:
            return
        junit = junit_candidates[0]
        try:
            import xml.etree.ElementTree as ET
            tree = ET.parse(str(junit))
            root = tree.getroot()
            ts   = root if root.tag == "testsuite" else root.find("testsuite")
            if ts is None:
                return
            total  = int(ts.get("tests", 0))
            failed = int(ts.get("failures", 0)) + int(ts.get("errors", 0))
            flaky  = 0
            # Count flaky: tests that have both a failure and a re-run pass
            for tc in ts.findall("testcase"):
                if tc.find("rerunFailure") is not None and tc.find("failure") is None:
                    flaky += 1
            result["execution"] = {
                "total":  total,
                "failed": failed,
                "flaky":  flaky,
                "passed": total - failed,
            }
        except Exception as exc:
            self._emit(f"Could not parse junit.xml: {exc}")

    def _parse_traceability(self, result: dict) -> None:
        candidates = list(self._reports.rglob("traceability_matrix.json"))
        if not candidates:
            return
        try:
            data    = json.loads(candidates[0].read_text(encoding="utf-8"))
            summary = data.get("summary", {})
            result["coverage"] = {
                "coverage_pct":         summary.get("coverage_pct", 0),
                "total_requirements":   summary.get("total_requirements", 0),
                "covered_full":         summary.get("fully_covered", summary.get("covered", 0)),
            }
        except Exception as exc:
            self._emit(f"Could not parse traceability_matrix.json: {exc}")

    def _parse_quality_gates(self, result: dict) -> None:
        candidates = list(self._reports.rglob("quality_gates.json"))
        if not candidates:
            return
        try:
            data = json.loads(candidates[0].read_text(encoding="utf-8"))
            result["quality_gates"] = {
                "gates_passed":      data.get("gates_passed", False),
                "critical_failures": data.get("critical_failures", 0),
                "warnings":          data.get("warnings", 0),
                "gates":             data.get("gates", []),
            }
        except Exception as exc:
            self._emit(f"Could not parse quality_gates.json: {exc}")

    def _parse_rca(self, result: dict) -> None:
        candidates = list(self._reports.rglob("rca_report.json"))
        if not candidates:
            return
        try:
            data = json.loads(candidates[0].read_text(encoding="utf-8"))
            result["rca"] = {
                "failures": data.get("failures", []),
            }
        except Exception as exc:
            self._emit(f"Could not parse rca_report.json: {exc}")

    def _parse_confidence(self, result: dict) -> None:
        candidates = list(self._reports.rglob("scenario-confidence-report.json"))
        if not candidates:
            return
        try:
            data = json.loads(candidates[0].read_text(encoding="utf-8"))
            result["confidence"] = {
                "summary": data.get("summary", {}),
            }
        except Exception as exc:
            self._emit(f"Could not parse scenario-confidence-report.json: {exc}")

    def _build_links(self, result: dict) -> None:
        links: dict[str, str] = {}
        html_candidates = list(self._reports.rglob("report.html"))
        if html_candidates:
            links["playwright_report"] = str(html_candidates[0])
        matrix_candidates = list(self._reports.rglob("traceability_matrix.md"))
        if matrix_candidates:
            links["traceability_matrix"] = str(matrix_candidates[0])
        result["links"] = links

    def _local_fallback(self) -> dict:
        self._emit("No run_id — parsing local reports only.")
        return self._parse_local_reports()

    def _emit(self, msg: str) -> None:
        self._on_update(f"> {msg}")
