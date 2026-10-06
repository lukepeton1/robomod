#!/usr/bin/env python3
"""Generate per-weapon Weapon Foundry build-space coverage from the graft rule engine."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from evaluate_graft import GraftRules


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "research/generated/build_space_summary.json"


def main() -> int:
    rules = GraftRules.from_repo()
    capabilities = rules.matrix.get("weapon_capabilities", [])
    matrix_by_row = {row["row"]: row for row in rules.matrix.get("properties", [])}

    weapons = []
    for weapon in capabilities:
        row = weapon["row"]
        plan = rules.plan_smith(
            target_weapon=row,
            existing_affix_rows=[],
            existing_weapon_mod_rows=[],
            current_affix_count=0,
            quality_color=4,
            available_power_cells=None,
        )
        allowed = [choice for choice in plan["choices"] if choice["allowed"]]
        affixes = sorted(choice["row_id"] for choice in allowed if choice["kind"] == "affix")
        mods = sorted(choice["row_id"] for choice in allowed if choice["kind"] == "weapon_mod")
        global_rows = sorted(
            row_id
            for row_id in affixes
            if matrix_by_row[row_id].get("global_merchant_eligible")
        )
        blocked_reasons = Counter(
            reason["code"]
            for choice in plan["choices"]
            if not choice["allowed"]
            for reason in choice["reasons"]
        )
        weapons.append({
            "row": row,
            "name": weapon.get("name"),
            "category": weapon.get("category"),
            "lootable_shipping": weapon.get("lootable_shipping"),
            "capabilities": {
                "cooling": weapon.get("cooling"),
                "warmup": weapon.get("warmup"),
                "scope": weapon.get("scope"),
                "temperature": weapon.get("temperature"),
                "primary_skill_row": weapon.get("primary_skill_row"),
            },
            "top_quality_build_space": {
                "affix_count": len(affixes),
                "alt_fire_count": len(mods),
                "total_property_count": len(allowed),
                "global_merchant_affix_count": len(global_rows),
                "affixes": affixes,
                "alt_fires": mods,
                "global_merchant_affixes": global_rows,
            },
            "blocked_reason_counts": dict(sorted(blocked_reasons.items())),
        })

    weapons.sort(
        key=lambda x: (
            x["top_quality_build_space"]["total_property_count"],
            x["row"],
        )
    )

    totals = [w["top_quality_build_space"]["total_property_count"] for w in weapons]
    affix_totals = [w["top_quality_build_space"]["affix_count"] for w in weapons]
    mod_totals = [w["top_quality_build_space"]["alt_fire_count"] for w in weapons]

    payload = {
        "schema_version": 1,
        "name": "weapon-foundry-build-space-summary",
        "policy": {
            "quality_color": 4,
            "existing_affix_rows": [],
            "existing_weapon_mod_rows": [],
            "power_cells": "unbounded",
            "meaning": "Theoretical target-compatible choices for an empty top-quality weapon before conflicts/duplicates from existing rows are introduced.",
        },
        "summary": {
            "weapon_count": len(weapons),
            "min_total_properties": min(totals) if totals else 0,
            "max_total_properties": max(totals) if totals else 0,
            "min_affixes": min(affix_totals) if affix_totals else 0,
            "max_affixes": max(affix_totals) if affix_totals else 0,
            "min_alt_fires": min(mod_totals) if mod_totals else 0,
            "max_alt_fires": max(mod_totals) if mod_totals else 0,
            "weapons_with_zero_properties": sum(value == 0 for value in totals),
            "weapons_with_zero_alt_fires": sum(value == 0 for value in mod_totals),
        },
        "weapons": weapons,
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
