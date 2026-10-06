#!/usr/bin/env python3
"""Generate Weapon Foundry's graft-transfer catalog from extracted Roboquest tables."""
from __future__ import annotations
import json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AFFIXES = ROOT / "research/generated/affixes.json"
MODS = ROOT / "research/generated/weapon_mods.json"
OUTPUT = ROOT / "Source/grafting/transfer_policy.json"

CORE = {
    "Bounce","Pierce","Ricochet","FreeShot","AutoShotgun","Fragmentation",
    "ExplosiveBlank","Homing","Burn","Ice","Shock","ProjectileRaycast","LuckyExplosion"
}
LOCKED_PATTERN = re.compile(r"(Blank$|BuddyBot|Buddybot|Superbot|SuperBot|_Shovel|_Enchanted|Separator|={3,})", re.I)

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

def main():
    affixes, mods = load(AFFIXES), load(MODS)
    dependent = set()
    for row in affixes + mods:
        dependent.update(row.get("additional_pool") or [])

    transferable, locked = [], []
    for row in affixes:
        rid = row["row"]
        reason = None
        if row.get("separator") or not row.get("active"):
            reason = "inactive_or_separator"
        elif row.get("enchanted"):
            reason = "enchanted_slot_reserved"
        elif rid in dependent:
            reason = "dependent_upgrade_row"
        elif LOCKED_PATTERN.search(rid):
            reason = "chassis_or_internal_variant"
        elif not row.get("class"):
            reason = "no_runtime_affix_class"
        elif rid not in CORE and len(row.get("weapons") or []) < 10:
            reason = "narrow_chassis_specific_pool"

        if reason:
            locked.append({"row":rid,"kind":"affix","reason":reason})
        else:
            rarity = row.get("rarity") or ""
            transferable.append({
                "row": rid,
                "kind": "affix",
                "name": row.get("name"),
                "rarity": rarity,
                "vanilla_weapons": len(row.get("weapons") or []),
                "cell_cost_base": 4 if "Rare" in rarity else 2,
                "core_composition": rid in CORE,
            })

    for row in mods:
        rid = row["row"]
        reason = None
        if row.get("separator") or not row.get("active"):
            reason = "inactive_or_separator"
        elif not row.get("class") or not row.get("secondary_skill_row"):
            reason = "no_resolved_secondary_skill"
        elif len(row.get("weapons") or []) < 10:
            reason = "narrow_chassis_specific_alt_fire"

        if reason:
            locked.append({"row":rid,"kind":"weapon_mod","reason":reason})
        else:
            transferable.append({
                "row": rid,
                "kind": "weapon_mod",
                "name": row.get("name"),
                "rarity": row.get("rarity"),
                "secondary_skill_row": row.get("secondary_skill_row"),
                "vanilla_weapons": len(row.get("weapons") or []),
                "cell_cost_base": 7,
            })

    payload = {
        "schema_version": 1,
        "name": "weapon-foundry-transfer-policy",
        "currency": "Power Cells",
        "identity_rules": {
            "donor_weapon_is_consumed": True,
            "chassis_and_innate_identity_affixes_locked": True,
            "enchanted_slot_not_used_as_general_affix_storage": True,
            "dependent_upgrade_rows_transfer_directly": False,
            "duplicate_row_policy": "allow_only_when_runtime_semantics_and_provenance_are_verified",
        },
        "cost_model": {
            "common_affix": 2,
            "rare_affix": 4,
            "elite_alt_fire": 7,
            "target_complexity_surcharge": "max(0, transferable_affix_count - 2)",
            "duplicate_instance_surcharge": 2,
            "note": "All costs are Power Cells; values are starting tuning targets, not new currency.",
        },
        "quality_budget": {
            "preserve_vanilla_quality_progression": True,
            "observed_breakpoints": [2,4,6,10],
            "rule": "Grafting may exceed the current random-roll bundle only through explicit player spend; smith/editor UI must display projected complexity.",
        },
        "transferable": sorted(transferable, key=lambda x: (x["kind"], x["row"])),
        "locked": sorted(locked, key=lambda x: (x["kind"], x["row"])),
    }
    payload["summary"] = {
        "transferable_affixes": sum(x["kind"] == "affix" for x in transferable),
        "transferable_alt_fires": sum(x["kind"] == "weapon_mod" for x in transferable),
        "locked_affixes": sum(x["kind"] == "affix" for x in locked),
        "locked_alt_fires": sum(x["kind"] == "weapon_mod" for x in locked),
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"], indent=2))

if __name__ == "__main__":
    main()
