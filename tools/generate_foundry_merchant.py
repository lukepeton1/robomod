#!/usr/bin/env python3
"""Generate the production Foundry merchant pool.

The global random merchant must only offer rows that are safe on every standard
Weapon Foundry chassis. The larger transfer catalog remains target-aware for the
future donor GRAFT flow.
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "Source/grafting/transfer_policy.json"
CORE = ROOT / "Source/patches/weapon_foundry_core.json"
OUTPUT = ROOT / "Source/patches/foundry_merchant.json"

def main():
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    core = json.loads(CORE.read_text(encoding="utf-8"))
    generalized = {
        op["row"]
        for op in core["operations"]
        if op.get("op") == "replace_name_array"
    }

    rows = [
        item["row"]
        for item in policy["transferable"]
        if item["kind"] == "affix"
        and (
            item.get("vanilla_weapons", 0) >= core["policy"]["standard_weapon_count"]
            or item["row"] in generalized
        )
    ]

    payload = {
        "schema_version": 1,
        "name": "weapon-foundry-merchant",
        "target": "Blueprint/Interactive/Merchant/BP_Merchant_UpgradeAffix",
        "status": "production",
        "purpose": (
            "Seed the vanilla Perfumer/affix merchant with only globally safe ordinary "
            "Foundry affixes. Target-specific transferable rows remain reserved for the "
            "future donor GRAFT flow, which can validate the target weapon before mutation."
        ),
        "policy": {
            "full_transferable_affix_count": sum(
                item["kind"] == "affix" for item in policy["transferable"]
            ),
            "global_merchant_affix_count": len(rows),
            "minimum_vanilla_weapon_coverage": core["policy"]["standard_weapon_count"],
            "explicit_generalized_rows_allowed": sorted(generalized),
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
    print(f"wrote {OUTPUT}: {len(rows)} globally safe ordinary affixes")

if __name__ == "__main__":
    main()
