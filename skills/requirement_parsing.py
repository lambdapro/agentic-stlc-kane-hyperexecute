"""
Skill 2: Requirement Parsing

Parses plain-text acceptance criteria files into structured requirement
objects. Supports multiple formats: acceptance_criteria, gherkin, plain.

Input formats:
  acceptance_criteria — "AC-001: user can ..." per line, or plain lines
                        under an "Acceptance Criteria:" section header
  gherkin             — Given/When/Then blocks
  plain               — one requirement per non-empty line

Produces analyzed_requirements.json-compatible output that KaneAI and
subsequent stages can consume.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .base import AgentSkill


class RequirementParsingSkill(AgentSkill):
    name = "requirement_parsing"
    description = "Parse requirements files into structured requirement objects"
    version = "1.0.0"

    input_schema = {
        "paths": {"type": list, "required": False, "description": "Requirement file paths to parse"},
        "format": {"type": str, "required": False, "description": "Format: acceptance_criteria|gherkin|plain"},
    }

    output_schema = {
        "requirements": {"type": list, "description": "List of parsed requirement dicts"},
        "total": {"type": int, "description": "Total requirement count"},
        "success": {"type": bool},
    }

    def run(self, **inputs: Any) -> dict:
        cfg_req = self.config.requirements if self.config else None
        paths = inputs.get("paths") or (cfg_req.paths if cfg_req else ["requirements/search.txt"])
        fmt = inputs.get("format") or (cfg_req.format if cfg_req else "acceptance_criteria")
        encoding = (cfg_req.encoding if cfg_req else None) or "utf-8"

        requirements: list[dict] = []
        for path_str in (paths if isinstance(paths, list) else [paths]):
            p = Path(path_str)
            if not p.exists():
                continue
            text = p.read_text(encoding=encoding)
            reqs = self._parse(text, fmt, source_file=str(path_str))
            requirements.extend(reqs)

        # Assign IDs if missing
        for i, req in enumerate(requirements, start=1):
            if not req.get("id"):
                req["id"] = f"AC-{i:03d}"

        output_path = Path(self.config.requirements_output if self.config else "requirements/analyzed_requirements.json")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        existing: list[dict] = []
        if output_path.exists():
            try:
                existing = json.loads(output_path.read_text(encoding="utf-8"))
            except Exception:
                existing = []
            requirements = self._merge_with_existing(requirements, existing)

        # Bug 7 guard: never overwrite existing Kane results with an empty parse.
        # This happens when the requirements file uses plain-text format but the
        # parser finds zero AC-NNN: patterns. Preserve existing data instead.
        if not requirements and existing:
            return {
                "success": True,
                "requirements": existing,
                "total": len(existing),
                "output": str(output_path),
                "note": "parse returned 0 results; existing data preserved",
            }

        output_path.write_text(json.dumps(requirements, indent=2) + "\n", encoding="utf-8")
        return {"success": True, "requirements": requirements, "total": len(requirements), "output": str(output_path)}

    # ── Parsers ───────────────────────────────────────────────────────────────

    def _parse(self, text: str, fmt: str, source_file: str = "") -> list[dict]:
        if fmt == "acceptance_criteria":
            return self._parse_ac(text, source_file)
        if fmt == "gherkin":
            return self._parse_gherkin(text, source_file)
        return self._parse_plain(text, source_file)

    def _parse_ac(self, text: str, source_file: str) -> list[dict]:
        """Parse 'AC-NNN: description' lines.

        Falls back to parsing plain lines under an 'Acceptance Criteria:' section
        header when no AC-NNN patterns are present (e.g. requirements/search.txt).
        """
        reqs = []
        ac_pattern = re.compile(r"^(AC-\d+)[:\s]+(.+)$", re.MULTILINE | re.IGNORECASE)
        current_feature = ""
        current_user_story = ""

        for line in text.splitlines():
            stripped = line.strip()
            if stripped.lower().startswith("feature:") or stripped.lower().startswith("user story:"):
                current_feature = stripped.split(":", 1)[-1].strip()
            if stripped.lower().startswith("as a "):
                current_user_story = stripped

        for m in ac_pattern.finditer(text):
            reqs.append({
                "id": m.group(1).upper(),
                "description": m.group(2).strip(),
                "feature": current_feature,
                "user_story": current_user_story,
                "source_file": source_file,
                "kane_status": "not_run",
                "kane_session_url": "",
                "kane_one_liner": "",
                "kane_steps": [],
                "kane_duration_ms": 0,
            })

        # No AC-NNN lines found — fall back to parsing the "Acceptance Criteria:" section
        if not reqs:
            reqs = self._parse_ac_section(text, source_file, current_feature, current_user_story)

        return reqs

    def _parse_ac_section(self, text: str, source_file: str,
                          feature: str = "", user_story: str = "") -> list[dict]:
        """Parse plain lines that appear under an 'Acceptance Criteria:' section header."""
        reqs = []
        in_ac_section = False
        idx = 0
        # Headers that signal the end of the AC block
        stop_prefixes = (
            "title:", "as a ", "i want", "so that",
            "feature:", "user story:", "acceptance criteria:",
        )

        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            low = stripped.lower()
            if low.startswith("acceptance criteria"):
                in_ac_section = True
                continue
            if in_ac_section:
                if any(low.startswith(p) for p in stop_prefixes):
                    in_ac_section = False
                    continue
                idx += 1
                reqs.append({
                    "id": f"AC-{idx:03d}",
                    "description": stripped,
                    "feature": feature,
                    "user_story": user_story,
                    "source_file": source_file,
                    "kane_status": "not_run",
                    "kane_session_url": "",
                    "kane_one_liner": "",
                    "kane_steps": [],
                    "kane_duration_ms": 0,
                })
        return reqs

    def _parse_gherkin(self, text: str, source_file: str) -> list[dict]:
        """Parse Gherkin Scenario/Scenario Outline blocks."""
        reqs = []
        scenario_pattern = re.compile(r"Scenario(?:\s+Outline)?:\s*(.+)", re.IGNORECASE)
        feature_pattern = re.compile(r"Feature:\s*(.+)", re.IGNORECASE)
        feature = ""
        idx = 0

        for m in feature_pattern.finditer(text):
            feature = m.group(1).strip()
            break

        for m in scenario_pattern.finditer(text):
            idx += 1
            reqs.append({
                "id": f"AC-{idx:03d}",
                "description": m.group(1).strip(),
                "feature": feature,
                "source_file": source_file,
                "kane_status": "not_run",
                "kane_session_url": "",
                "kane_one_liner": "",
                "kane_steps": [],
                "kane_duration_ms": 0,
            })
        return reqs

    def _parse_plain(self, text: str, source_file: str) -> list[dict]:
        """One non-empty, non-comment line = one requirement."""
        reqs = []
        idx = 0
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            idx += 1
            reqs.append({
                "id": f"AC-{idx:03d}",
                "description": stripped,
                "feature": "",
                "source_file": source_file,
                "kane_status": "not_run",
                "kane_session_url": "",
                "kane_one_liner": "",
                "kane_steps": [],
                "kane_duration_ms": 0,
            })
        return reqs

    def _merge_with_existing(self, parsed: list[dict], existing: list[dict]) -> list[dict]:
        """Preserve existing Kane results when re-parsing unchanged requirements."""
        existing_by_id = {r.get("id"): r for r in existing if r.get("id")}
        for req in parsed:
            rid = req.get("id")
            if rid in existing_by_id:
                ex = existing_by_id[rid]
                req.setdefault("kane_status", ex.get("kane_status", "not_run"))
                req.setdefault("kane_session_url", ex.get("kane_session_url", ""))
                req.setdefault("kane_one_liner", ex.get("kane_one_liner", ""))
        return parsed
