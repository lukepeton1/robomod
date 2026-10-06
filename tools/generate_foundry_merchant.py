#!/usr/bin/env python3
"""Generate the production Foundry merchant pool.

The random merchant cannot inspect the target's existing affix row IDs, so it may only
offer rows that are:

1. transferable ordinary affixes;
2. safe/generalized across the standard Weapon Foundry chassis set; and
3. pairwise conflict-free with every other globally offered ordinary affix.

Target-specific or mutually exclusive rows remain available to the deterministic
GRAFT/Smith rule engine, which can inspect the actual target before mutation.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "Source/grafting/transfer_policy.json"
CORE = ROOT / "Source/patches/weapon_foundry_core.json"
AFFIXES = ROOT / "research/generated/affixes.json"
OUTPUT = ROOT / "Source/patches/foundry_merchant.json"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    policy = load(POLICY)
    core = load(CORE)
    affixes = load(AFFIXES)
    aff_by = {row["row"]: row for row in affixes}

    generalized = {
        op["row"]
        for op in core["operations"]
        if op.get("op") == "replace_name_array"
    }
    removed_unlocks: dict[str, set[str]] = {}
    for op in core["operations"]:
        if op.get("op") == "remove_row_handles" and op.get("field") == "RemovedPool":
            removed_unlocks.setdefault(op["row"], set()).update(op.get("values") or [])

    standard_count = int(core["policy"]["standard_weapon_count"])
    ordinary = [
        item
        for item in policy["transferable"]
        if item["kind"] == "affix"
    ]

    candidates = [
        item["row"]
        for item in ordinary
        if (
            int(item.get("vanilla_weapons", 0)) >= standard_count
            or item["row"] in generalized
        )
    ]
    candidate_set = set(candidates)

    effective_removed: dict[str, set[str]] = {}
    for row_id in candidates:
        source = aff_by[row_id]
        effective_removed[row_id] = {
            row
            for row in (source.get("removed_pool") or [])
            if row not in removed_unlocks.get(row_id, set())
        }

    conflicted: set[str] = set()
    conflict_pairs: set[tuple[str, str]] = set()
    for row in candidates:
        for other in candidates:
            if row == other:
                continue
            if (
                other in effective_removed[row]
                or row in effective_removed[other]
            ):
                pair = tuple(sorted((row, other)))
                conflict_pairs.add(pair)
                conflicted.update(pair)

    rows = [
        row
        for row in candidates
        if row not in conflicted
    ]

    payload = {
        "schema_version": 1,
        "name": "weapon-foundry-merchant",
        "target": "Blueprint/Interactive/Merchant/BP_Merchant_UpgradeAffix",
        "status": "production",
        "purpose": (
            "Seed the vanilla Perfumer/affix merchant with only globally safe, "
            "pairwise conflict-free ordinary Foundry affixes. Target-specific or "
            "mutually exclusive transferable rows remain reserved for deterministic "
            "GRAFT/Smith, which validates the actual target weapon before mutation."
        ),
        "policy": {
            "full_transferable_affix_count": len(ordinary),
            "chassis_safe_candidate_count": len(candidates),
            "global_merchant_affix_count": len(rows),
            "minimum_vanilla_weapon_coverage": standard_count,
            "explicit_generalized_rows_allowed": sorted(generalized),
            "excluded_global_conflict_rows": sorted(conflicted),
            "excluded_global_conflict_pairs": [
                list(pair) for pair in sorted(conflict_pairs)
            ],
        },
        "operations": [{
            "op": "set_name_array",
            "cdo": "Default__BP_Merchant_UpgradeAffix_C",
            "field": "AffixRows",
            "values": rows,
        }],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        f"wrote {OUTPUT}: {len(rows)} globally safe conflict-free ordinary affixes "
        f"({len(conflicted)} target-aware rows withheld for mutual conflicts)"
    )


if __name__ == "__main__":
    main()
