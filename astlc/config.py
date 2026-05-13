"""
Platform configuration loader.

Reads agentic-stlc.config.yaml (or AGENTIC_STLC_CONFIG env var override)
and provides typed attribute-style access to all platform settings.

Deep env-var override: any leaf key can be overridden using the pattern
  ASTLC_<SECTION>_<KEY>=value
  e.g.  ASTLC_EXECUTION_CONCURRENCY=10   sets execution.concurrency = 10

Config file is optional — all defaults are baked in so the platform runs
without any config file in the common case.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

try:
    import yaml as _yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

_DEFAULT_CONFIG_PATH = "agentic-stlc.config.yaml"
_ENV_PREFIX = "ASTLC_"

_DEFAULTS: dict = {
    "version": "1.0",
    "project": {
        "name": "agentic-stlc",
        "repository": "",
        "branch": "main",
        "description": "",
    },
    "requirements": {
        "format": "acceptance_criteria",
        "paths": ["requirements/search.txt"],
        "output_path": "requirements/analyzed_requirements.json",
        "encoding": "utf-8",
    },
    "scenarios": {
        "path": "scenarios/scenarios.json",
        "id_prefix": "SC",
        "id_start": 1,
    },
    "framework": {
        "type": "playwright",
        "language": "python",
        "test_dir": "tests/playwright",
        "test_file": "tests/playwright/test_powerapps.py",
    },
    "target": {
        "url": "",
        "environment": "staging",
    },
    "execution": {
        "provider": "hyperexecute",
        "mode": "incremental",
        "concurrency": 5,
        "timeout_seconds": 90,
        "retries": 1,
        "browsers": ["chrome"],
        "platforms": ["windows10"],
    },
    "hyperexecute": {
        "config_file": "hyperexecute.yaml",
        "cli_path": "./hyperexecute",
        "project": "agentic-stlc",
        "region": "us",
    },
    "kaneai": {
        "enabled": True,
        "parallel_workers": 5,
        "timeout_seconds": 120,
        "project_id": "",
        "folder_id": "",
    },
    "reporting": {
        "output_dir": "reports",
        "formats": ["json", "markdown"],
        "github_summary": True,
        "artifacts": ["reports/", "scenarios/scenarios.json"],
    },
    "quality_gates": {
        "min_coverage_pct": 50,
        "min_pass_rate": 75,
        "max_flaky": 5,
        "require_critical_coverage": True,
        "max_high_risk_uncovered": 999,
        "min_he_pct": 0,
        "confidence": {
            "enabled": True,
            "gate_severity": "WARNING",
        },
    },
    "adapters": {
        "git": "github",
        "ci": "github_actions",
        "execution": "hyperexecute",
        "functional_testing": "kaneai",
        "test_framework": "playwright",
    },
    "pipeline": {
        "stages": [],
    },
    "plugins": [],
    "notifications": {
        "slack": {"enabled": False, "webhook_url": ""},
        "email": {"enabled": False, "recipients": []},
    },
}


class ConfigNode:
    """Attribute-style access wrapper over a config dict."""

    def __init__(self, data: dict) -> None:
        object.__setattr__(self, "_data", data)

    def __getattr__(self, key: str) -> Any:
        data = object.__getattribute__(self, "_data")
        if key not in data:
            return None
        val = data[key]
        return ConfigNode(val) if isinstance(val, dict) else val

    def __getitem__(self, key: str) -> Any:
        return object.__getattribute__(self, "_data")[key]

    def __contains__(self, key: str) -> bool:
        return key in object.__getattribute__(self, "_data")

    def get(self, key: str, default: Any = None) -> Any:
        data = object.__getattribute__(self, "_data")
        val = data.get(key, default)
        return ConfigNode(val) if isinstance(val, dict) else val

    def as_dict(self) -> dict:
        return object.__getattribute__(self, "_data")

    def __repr__(self) -> str:
        return f"ConfigNode({object.__getattribute__(self, '_data')})"


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def _coerce(val: str, reference: Any) -> Any:
    if isinstance(reference, bool):
        return val.lower() in ("true", "1", "yes")
    if isinstance(reference, int):
        try:
            return int(val)
        except ValueError:
            return val
    if isinstance(reference, float):
        try:
            return float(val)
        except ValueError:
            return val
    if isinstance(reference, list):
        return [v.strip() for v in val.split(",")]
    return val


def _apply_env_overrides(cfg: dict) -> dict:
    for key, raw_val in os.environ.items():
        if not key.startswith(_ENV_PREFIX):
            continue
        tail = key[len(_ENV_PREFIX):].lower()
        parts = tail.split("_", 1)
        if len(parts) == 2:
            section, subkey = parts
            if section in cfg and isinstance(cfg[section], dict) and subkey in cfg[section]:
                cfg[section][subkey] = _coerce(raw_val, cfg[section][subkey])
    return cfg


class PlatformConfig:
    """
    Central configuration object for the Agentic STLC platform.

    Usage::

        cfg = PlatformConfig.load()
        url  = cfg.target.url
        out  = cfg.reporting.output_dir
        conc = cfg.execution.concurrency
    """

    def __init__(self, data: dict) -> None:
        object.__setattr__(self, "_data", data)

    def __getattr__(self, key: str) -> Any:
        data = object.__getattribute__(self, "_data")
        if key not in data:
            return None
        val = data[key]
        return ConfigNode(val) if isinstance(val, dict) else val

    def get(self, key: str, default: Any = None) -> Any:
        data = object.__getattribute__(self, "_data")
        val = data.get(key, default)
        return ConfigNode(val) if isinstance(val, dict) else val

    def as_dict(self) -> dict:
        return object.__getattribute__(self, "_data")

    # ── Loaders ──────────────────────────────────────────────────────────────

    @classmethod
    def load(cls, path: str | None = None) -> "PlatformConfig":
        """Load config from YAML file, apply env overrides, merge with defaults."""
        config_path = path or os.environ.get("AGENTIC_STLC_CONFIG", _DEFAULT_CONFIG_PATH)
        raw: dict = {}
        p = Path(config_path)
        if p.exists():
            content = p.read_text(encoding="utf-8")
            if _HAS_YAML:
                raw = _yaml.safe_load(content) or {}
            else:
                try:
                    raw = json.loads(content)
                except json.JSONDecodeError:
                    raw = {}
        merged = _deep_merge(_DEFAULTS, raw)
        merged = _apply_env_overrides(merged)
        return cls(merged)

    @classmethod
    def from_dict(cls, data: dict) -> "PlatformConfig":
        merged = _deep_merge(_DEFAULTS, data)
        return cls(merged)

    # ── Validation ───────────────────────────────────────────────────────────

    def validate(self) -> list[str]:
        """Return list of validation errors; empty list means config is valid."""
        errors: list[str] = []
        data = object.__getattribute__(self, "_data")
        if not data.get("project", {}).get("name"):
            errors.append("project.name is required")
        req_paths = data.get("requirements", {}).get("paths", [])
        if not req_paths:
            errors.append("requirements.paths must contain at least one path")
        return errors

    # ── Convenience accessors ─────────────────────────────────────────────────

    @property
    def reports_dir(self) -> Path:
        data = object.__getattribute__(self, "_data")
        return Path(data.get("reporting", {}).get("output_dir", "reports"))

    @property
    def requirements_output(self) -> Path:
        data = object.__getattribute__(self, "_data")
        return Path(data.get("requirements", {}).get("output_path", "requirements/analyzed_requirements.json"))

    @property
    def scenarios_path(self) -> Path:
        data = object.__getattribute__(self, "_data")
        return Path(data.get("scenarios", {}).get("path", "scenarios/scenarios.json"))
