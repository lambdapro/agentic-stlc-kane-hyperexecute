"""
FileIngestor — parse uploaded requirement files in any format.

Supports: .txt, .md, .yaml/.yml, .json, Jira CSV, plain text.
Returns normalized (text, detected_format) tuples so downstream
RequirementParsingSkill can consume them without format guessing.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class FileIngestor:
    """Normalize any requirements file into (text, format) for parsing."""

    SUPPORTED_EXTENSIONS = {".txt", ".md", ".yaml", ".yml", ".json", ".csv"}

    @classmethod
    def ingest(
        cls,
        path: str | Path | None = None,
        content: str | bytes | None = None,
        filename: str | None = None,
    ) -> tuple[str, str]:
        """
        Returns (normalized_text, detected_format).

        detected_format is one of: acceptance_criteria | gherkin | plain | json | yaml
        """
        if path is not None:
            p = Path(path)
            if not p.exists():
                raise FileNotFoundError(f"Requirements file not found: {path}")
            raw = p.read_bytes()
            ext = p.suffix.lower()
            filename = filename or p.name
        elif content is not None:
            raw = content if isinstance(content, bytes) else content.encode("utf-8")
            ext = Path(filename).suffix.lower() if filename else ".txt"
        else:
            raise ValueError("Either path or content must be provided")

        text = cls._decode(raw)
        fmt  = cls._detect_format(text, ext)

        # Normalize JSON / YAML requirements into plain-text lines
        if fmt == "json":
            text = cls._normalize_json(text)
            fmt  = "plain"
        elif fmt == "yaml":
            text = cls._normalize_yaml(text)
            fmt  = "plain"
        elif ext == ".csv":
            text = cls._normalize_csv(text)
            fmt  = "plain"

        return text, fmt

    @staticmethod
    def supported_extensions() -> list[str]:
        return list(FileIngestor.SUPPORTED_EXTENSIONS)

    # ── Internal ──────────────────────────────────────────────────────────────

    @staticmethod
    def _decode(raw: bytes) -> str:
        for enc in ("utf-8-sig", "utf-8", "latin-1"):
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                continue
        return raw.decode("utf-8", errors="replace")

    @staticmethod
    def _detect_format(text: str, ext: str) -> str:
        if ext in (".yaml", ".yml"):
            return "yaml"
        if ext == ".json":
            return "json"
        if ext == ".csv":
            return "csv"
        # Heuristic: Gherkin keywords
        low = text[:2000].lower()
        if "feature:" in low and ("scenario:" in low or "given " in low):
            return "gherkin"
        # AC-NNN: explicit IDs
        import re
        if re.search(r"^ac-\d+[:\s]", text[:2000], re.MULTILINE | re.IGNORECASE):
            return "acceptance_criteria"
        # "Acceptance Criteria:" section
        if "acceptance criteria" in low:
            return "acceptance_criteria"
        return "plain"

    @staticmethod
    def _normalize_json(text: str) -> str:
        """Convert JSON requirements to plain-text lines."""
        try:
            data = json.loads(text)
        except Exception:
            return text

        lines: list[str] = []

        def _extract(obj: Any, depth: int = 0) -> None:
            if isinstance(obj, str) and obj.strip():
                lines.append(obj.strip())
            elif isinstance(obj, list):
                for item in obj:
                    _extract(item, depth + 1)
            elif isinstance(obj, dict):
                # Common Jira/ADO key names for requirement text
                for key in ("summary", "description", "title", "name", "text", "requirement", "criteria"):
                    if key in obj and isinstance(obj[key], str):
                        lines.append(obj[key].strip())
                        break
                else:
                    for v in obj.values():
                        _extract(v, depth + 1)

        _extract(data)
        return "\n".join(lines)

    @staticmethod
    def _normalize_yaml(text: str) -> str:
        """Convert YAML requirements to plain-text lines."""
        try:
            import yaml  # type: ignore
            data = yaml.safe_load(text)
        except Exception:
            return text

        lines: list[str] = []

        def _extract(obj: Any) -> None:
            if isinstance(obj, str) and obj.strip():
                lines.append(obj.strip())
            elif isinstance(obj, list):
                for item in obj:
                    _extract(item)
            elif isinstance(obj, dict):
                for key in ("description", "title", "summary", "criteria", "requirement", "name", "text"):
                    if key in obj and isinstance(obj[key], str):
                        lines.append(obj[key].strip())
                        break
                else:
                    for v in obj.values():
                        _extract(v)

        _extract(data)
        return "\n".join(lines)

    @staticmethod
    def _normalize_csv(text: str) -> str:
        """Extract requirement text from CSV (Jira export or similar)."""
        import csv
        import io
        reader = csv.DictReader(io.StringIO(text))
        lines: list[str] = []
        for row in reader:
            for key in ("Summary", "Description", "Title", "Requirement", "Acceptance Criteria", "Name"):
                val = row.get(key, "").strip()
                if val:
                    lines.append(val)
                    break
        return "\n".join(lines) if lines else text
