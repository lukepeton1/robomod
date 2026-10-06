#!/usr/bin/env python3
"""Generate the production DT_WeaponMod eligibility patch."""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "Source/patches/weapon_foundry_core.json"
TRANSFER = ROOT / "Source/grafting/transfer_policy.json"
OUTPUT = ROOT / "Source/patches/weapon_foundry_mods.json"

def main():
    core = json.loads(CORE.read_text(encoding="utf-8"))
    transfer = json.loads(TRANSFER.read_text(encoding="utf-8"))
    standard = next(
        op["values"] for op in core["operations"]
        if op["op"] == "replace_name_array" and op["row"] == "Fragmentation"
    )
    mods = [
        item["row"] for item in transfer["transferable"]
        if item["kind"] == "weapon_mod"
    ]
    payload = {
        "schema_version": 1,
        "name": "weapon-foundry-weapon-mods",
        "target": "Data/DT_WeaponMod",
        "status": "production_core_v0",
        "policy": {
            "source": "Source/grafting/transfer_policy.json",
            "compatible_weapon_count": len(standard),
            "resolved_alt_fire_count": len(mods),
            "note": "Only resolved broad native AddSecondaryFire-style rows marked transferable are widened.",
        },
        "operations": [
            {
                "op": "replace_name_array",
                "row": row,
                "field": "Weapons",
                "values": standard,
                "reason": "Broaden resolved transferable native secondary-fire affix across standard Projectile/Raycast weapon chassis.",
            }
            for row in mods
        ],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT}: {len(mods)} mod rows x {len(standard)} weapons")

if __name__ == "__main__":
    main()
