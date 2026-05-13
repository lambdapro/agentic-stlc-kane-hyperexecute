"""
Skill 7: Artifact Collection

Collects, validates, and packages pipeline artifacts from various sources:
  - Local reports/ directory
  - GitHub Actions artifact downloads
  - HyperExecute session logs + videos
  - JUnit XML + HTML reports

Produces a unified artifact manifest for downstream analysis.
"""
from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .base import AgentSkill


class ArtifactCollectionSkill(AgentSkill):
    name = "artifact_collection"
    description = "Collect, validate, and manifest pipeline artifacts"
    version = "1.0.0"

    input_schema = {
        "sources":   {"type": list, "required": False, "description": "List of source paths/URLs to collect from"},
        "output_dir": {"type": str, "required": False, "description": "Destination directory"},
    }

    def run(self, **inputs: Any) -> dict:
        output_dir = Path(inputs.get("output_dir", self.reports_dir))
        output_dir.mkdir(parents=True, exist_ok=True)

        sources = inputs.get("sources") or self._default_sources()
        manifest = {
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "artifacts": [],
        }

        for source in sources:
            entry = self._collect(Path(source), output_dir)
            if entry:
                manifest["artifacts"].append(entry)

        manifest_path = output_dir / "artifact_manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

        return {
            "success": True,
            "manifest": str(manifest_path),
            "total_artifacts": len(manifest["artifacts"]),
            "output_dir": str(output_dir),
        }

    def _default_sources(self) -> list[str]:
        cfg_artifacts = []
        if self.config:
            cfg_arts = self.config.reporting.artifacts if self.config.reporting else None
            if cfg_arts:
                cfg_artifacts = cfg_arts if isinstance(cfg_arts, list) else []
        return cfg_artifacts or ["reports/", "scenarios/scenarios.json", "tests/playwright/test_powerapps.py"]

    def _collect(self, source: Path, output_dir: Path) -> dict | None:
        if not source.exists():
            return None
        if source.is_dir():
            dest = output_dir / source.name
            if source != output_dir:
                shutil.copytree(str(source), str(dest), dirs_exist_ok=True)
            files = list(source.rglob("*"))
            return {
                "type": "directory",
                "source": str(source),
                "files": len([f for f in files if f.is_file()]),
                "size_bytes": sum(f.stat().st_size for f in files if f.is_file()),
            }
        stat = source.stat()
        return {
            "type": "file",
            "name": source.name,
            "source": str(source),
            "size_bytes": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        }

    def validate_junit(self, junit_path: str = "reports/junit.xml") -> dict:
        """Parse JUnit XML and return pass/fail counts."""
        p = Path(junit_path)
        if not p.exists():
            return {"exists": False, "tests": 0, "failures": 0, "errors": 0}
        try:
            import xml.etree.ElementTree as ET
            tree = ET.parse(str(p))
            root = tree.getroot()
            suite = root if root.tag == "testsuite" else root.find("testsuite")
            if suite is None:
                return {"exists": True, "tests": 0, "failures": 0, "errors": 0}
            return {
                "exists": True,
                "tests":    int(suite.get("tests", 0)),
                "failures": int(suite.get("failures", 0)),
                "errors":   int(suite.get("errors", 0)),
                "skipped":  int(suite.get("skipped", 0)),
            }
        except Exception as exc:
            return {"exists": True, "parse_error": str(exc)}

    def download_he_artifacts(self, job_id: str, output_dir: str = "reports/he_artifacts") -> dict:
        """Download session videos/traces from HyperExecute (stub — implement via HE API)."""
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        return {"job_id": job_id, "output_dir": output_dir, "note": "HE artifact download requires LT credentials"}
