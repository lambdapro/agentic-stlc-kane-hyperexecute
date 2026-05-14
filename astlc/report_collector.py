"""
ReportCollector — download and parse CI artifacts into a structured summary.

Downloads GitHub Actions artifacts (junit.xml, traceability_matrix.json,
quality_gates.json, report.html) and parses them into a dict suitable
for ChatReporter.execution_summary().

ArtifactCache integration: when a cache is supplied every report file is
read from disk exactly once per pipeline run.  Without a cache the
collector falls back to direct reads (backward-compatible).
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
        cache: Any | None = None,   # ArtifactCache — optional, avoids circular import
    ) -> None:
        self._token      = github_token or os.environ.get("GITHUB_TOKEN", "")
        self._repo       = repo_slug
        self._reports    = Path(reports_dir)
        self._on_update  = on_update or (lambda _: None)
        self._cache      = cache    # ArtifactCache | None

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
        """
        Single-pass parse of all local report files.

        Uses ArtifactCache when available so each file is read at most once
        across the entire pipeline run (even if multiple callers invoke this).
        Falls back to direct reads when no cache is provided.
        """
        result: dict[str, Any] = {
            "execution":            {},
            "coverage":             {},
            "quality_gates":        {},
            "rca":                  {"failures": []},
            "links":                {},
            "artifacts_downloaded": 0,
        }

        self._parse_junit(result)
        self._parse_traceability(result)
        self._parse_quality_gates(result)
        self._parse_rca(result)
        self._parse_confidence(result)
        self._parse_api_details(result)
        self._build_links(result)

        return result

    # ── Cached JSON helper ────────────────────────────────────────────────────

    def _read_json(self, path: Path) -> Any:
        """Read JSON via cache (one disk read) or direct (backward-compat)."""
        if self._cache is not None:
            return self._cache.get_json(path)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _find_first(self, filename: str) -> Path | None:
        """Return first match under reports dir; prefer cache-resident paths."""
        candidates = sorted(self._reports.rglob(filename))
        return candidates[0] if candidates else None

    # ── Individual parsers (each reads its file exactly once) ─────────────────

    def _parse_junit(self, result: dict) -> None:
        junit = self._find_first("junit.xml")
        if not junit:
            return
        try:
            import xml.etree.ElementTree as ET
            if self._cache is not None:
                root = self._cache.get_xml(junit)
            else:
                root = ET.parse(str(junit)).getroot()
            if root is None:
                return
            ts = root if root.tag == "testsuite" else root.find("testsuite")
            if ts is None:
                return
            total  = int(ts.get("tests", 0))
            failed = int(ts.get("failures", 0)) + int(ts.get("errors", 0))
            flaky  = sum(
                1 for tc in ts.findall("testcase")
                if tc.find("rerunFailure") is not None and tc.find("failure") is None
            )
            result["execution"] = {
                "total":  total,
                "failed": failed,
                "flaky":  flaky,
                "passed": total - failed,
            }
        except Exception as exc:
            self._emit(f"Could not parse junit.xml: {exc}")

    def _parse_traceability(self, result: dict) -> None:
        p = self._find_first("traceability_matrix.json")
        if not p:
            return
        data = self._read_json(p)
        if not data:
            return
        summary = data.get("summary", {})
        result["coverage"] = {
            "coverage_pct":       summary.get("coverage_pct", 0),
            "total_requirements": summary.get("total_requirements", 0),
            "covered_full":       summary.get("fully_covered", summary.get("covered", 0)),
        }

    def _parse_quality_gates(self, result: dict) -> None:
        p = self._find_first("quality_gates.json")
        if not p:
            return
        data = self._read_json(p)
        if not data:
            return
        result["quality_gates"] = {
            "gates_passed":      data.get("gates_passed", False),
            "critical_failures": data.get("critical_failures", 0),
            "warnings":          data.get("warnings", 0),
            "gates":             data.get("gates", []),
        }

    def _parse_rca(self, result: dict) -> None:
        p = self._find_first("rca_report.json")
        if not p:
            return
        data = self._read_json(p)
        if not data:
            return
        result["rca"] = {"failures": data.get("failures", [])}

    def _parse_confidence(self, result: dict) -> None:
        p = self._find_first("scenario-confidence-report.json")
        if not p:
            return
        data = self._read_json(p)
        if not data:
            return
        result["confidence"] = {"summary": data.get("summary", {})}

    def _parse_api_details(self, result: dict) -> None:
        """Extract HyperExecute summary written by ci/agent.py Stage 6."""
        p = self._find_first("api_details.json")
        if not p:
            return
        data = self._read_json(p)
        if not data:
            return
        he = data.get("he_summary", {})
        if he:
            result["hyperexecute"] = {
                "job_id":    he.get("job_id", ""),
                "status":    he.get("status", ""),
                "shards":    he.get("total_tasks", 0),
                "passed":    he.get("passed", 0),
                "failed":    he.get("failed", 0),
                "flaky":     he.get("flaky", 0),
                "duration_s": he.get("duration_s", 0),
                "dashboard": he.get("dashboard_url", ""),
            }

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
