"""
Skill 3: Scenario Generation

Deterministic diff-based sync between analyzed requirements and the
scenario pool. Assigns stable SC-NNN IDs. New requirements → new scenarios,
changed → updated, removed → deprecated, unchanged → active.

Scenario IDs are immutable once assigned. Deprecated scenarios are never
deleted — they remain as historical record with status="deprecated".
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .base import AgentSkill


class ScenarioGenerationSkill(AgentSkill):
    name = "scenario_generation"
    description = "Sync requirements → scenario pool with deterministic ID assignment"
    version = "1.0.0"

    def run(self, **inputs: Any) -> dict:
        req_path = Path(
            inputs.get("requirements_path")
            or (self.config.requirements_output if self.config else "requirements/analyzed_requirements.json")
        )
        sc_path = Path(
            inputs.get("scenarios_path")
            or (self.config.scenarios_path if self.config else "scenarios/scenarios.json")
        )

        requirements: list[dict] = []
        if req_path.exists():
            requirements = json.loads(req_path.read_text(encoding="utf-8"))

        scenarios: list[dict] = []
        if sc_path.exists():
            scenarios = json.loads(sc_path.read_text(encoding="utf-8"))

        updated, stats = self._sync(requirements, scenarios)

        sc_path.parent.mkdir(parents=True, exist_ok=True)
        sc_path.write_text(json.dumps(updated, indent=2) + "\n", encoding="utf-8")

        return {
            "success": True,
            "scenarios_path": str(sc_path),
            "total_scenarios": len(updated),
            "new": stats["new"],
            "updated": stats["updated"],
            "deprecated": stats["deprecated"],
            "active": stats["active"],
        }

    # ── Core sync logic ───────────────────────────────────────────────────────

    def _sync(self, requirements: list[dict], scenarios: list[dict]) -> tuple[list[dict], dict]:
        existing: dict[str, dict] = {s["requirement_id"]: s for s in scenarios if "requirement_id" in s}
        new_scenarios: list[dict] = list(scenarios)
        cfg_sc = self.config.scenarios if self.config else None
        prefix = (cfg_sc.id_prefix if cfg_sc else None) or "SC"
        id_start = int((cfg_sc.id_start if cfg_sc else None) or 1)

        stats = {"new": 0, "updated": 0, "deprecated": 0, "active": 0}
        current_req_ids = {r["id"] for r in requirements if r.get("id")}

        # Deprecate removed requirements
        for sc in new_scenarios:
            if sc.get("requirement_id") not in current_req_ids:
                if sc.get("status") != "deprecated":
                    sc["status"] = "deprecated"
                    sc["deprecated_at"] = datetime.now(timezone.utc).isoformat()
                    stats["deprecated"] += 1

        # Add or update
        for req in requirements:
            rid = req.get("id")
            if not rid:
                continue
            desc = req.get("description", "")
            if rid in existing:
                sc = existing[rid]
                changed = False
                # Backfill description from requirement if missing
                source_desc = sc.get("description") or sc.get("source_description", "")
                if source_desc != desc and desc:
                    sc["description"] = desc
                    changed = True
                elif not sc.get("description") and source_desc:
                    sc["description"] = source_desc
                # Backfill feature if missing or GENERAL
                if not sc.get("feature") or sc.get("feature") == "GENERAL":
                    sc["feature"] = self._infer_feature(sc.get("description", desc))
                # Backfill kane_objective if missing
                if not sc.get("kane_objective"):
                    sc["kane_objective"] = self._default_objective(
                        sc.get("description", desc),
                        req.get("target_url", ""),
                    )
                if changed:
                    sc["status"] = "updated"
                    sc["updated_at"] = datetime.now(timezone.utc).isoformat()
                    stats["updated"] += 1
                elif sc.get("status") != "deprecated":
                    sc["status"] = "active"
                    stats["active"] += 1
            else:
                sc_id = self._next_id(new_scenarios, prefix, id_start)
                feature = self._infer_feature(desc)
                new_sc = {
                    "id": sc_id,
                    "requirement_id": rid,
                    "description": desc,
                    "feature": feature,
                    "status": "new",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "kane_objective": self._default_objective(desc, req.get("target_url", "")),
                }
                new_scenarios.append(new_sc)
                stats["new"] += 1

        return new_scenarios, stats

    def _next_id(self, scenarios: list[dict], prefix: str, start: int) -> str:
        pattern = re.compile(rf"^{re.escape(prefix)}-(\d+)$")
        max_n = start - 1
        for sc in scenarios:
            m = pattern.match(sc.get("id", ""))
            if m:
                max_n = max(max_n, int(m.group(1)))
        return f"{prefix}-{max_n + 1:03d}"

    def _infer_feature(self, description: str) -> str:
        desc_lower = description.lower()
        keywords = {
            "CART": ["cart", "add to cart", "basket"],
            "CHECKOUT": ["checkout", "payment", "order", "purchase"],
            "AUTH": ["login", "sign in", "logout", "auth", "register"],
            "SEARCH": ["search", "find", "query"],
            "CATALOG": ["catalog", "category", "browse", "listing"],
            "PRODUCT_DETAIL": ["product detail", "product page", "pdp"],
            "FILTER": ["filter", "refine", "sort by brand"],
            "SORT": ["sort", "order by"],
            "WISHLIST": ["wishlist", "wish list", "save for later"],
            "GUEST": ["guest", "without login", "without account"],
        }
        for feature, kws in keywords.items():
            if any(kw in desc_lower for kw in kws):
                return feature
        return "GENERAL"

    def _default_objective(self, description: str, target_url: str = "") -> str:
        base = f"Verify: {description}"
        if target_url:
            base += f" on {target_url}"
        return base
