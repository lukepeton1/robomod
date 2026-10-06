#!/usr/bin/env python3
"""Generate target-aware Weapon Foundry graft compatibility data."""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATHS = {
    "affixes": ROOT / "research/generated/affixes.json",
    "mods": ROOT / "research/generated/weapon_mods.json",
    "weapons": ROOT / "research/generated/weapons.json",
    "core": ROOT / "Source/patches/weapon_foundry_core.json",
    "mod_patch": ROOT / "Source/patches/weapon_foundry_mods.json",
    "transfer": ROOT / "Source/grafting/transfer_policy.json",
    "merchant": ROOT / "Source/patches/foundry_merchant.json",
}
OUTPUT = ROOT / "Source/grafting/compatibility_matrix.json"

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

def main():
    affixes = load(PATHS["affixes"])
    mods = load(PATHS["mods"])
    weapons = load(PATHS["weapons"])
    core = load(PATHS["core"])
    mod_patch = load(PATHS["mod_patch"])
    transfer = load(PATHS["transfer"])
    merchant = load(PATHS["merchant"])

    known = {x["row"] for x in weapons}
    aff_by = {x["row"]: x for x in affixes}
    mod_by = {x["row"]: x for x in mods}
    generalized = {
        op["row"]: op["values"]
        for op in core["operations"]
        if op.get("op") == "replace_name_array"
    }
    mod_generalized = {
        op["row"]: op["values"]
        for op in mod_patch["operations"]
        if op.get("op") == "replace_name_array"
    }
    removed_unlocks = {}
    for op in core["operations"]:
        if op.get("op") == "remove_row_handles" and op.get("field") == "RemovedPool":
            removed_unlocks.setdefault(op["row"], set()).update(op["values"])

    merchant_rows = set(merchant["operations"][0]["values"])
    entries = []
    for item in transfer["transferable"]:
        source = aff_by[item["row"]] if item["kind"] == "affix" else mod_by[item["row"]]
        widened = (
            generalized.get(item["row"])
            if item["kind"] == "affix"
            else mod_generalized.get(item["row"])
        )
        raw_weapons = widened if widened is not None else source.get("weapons", [])
        production_weapons = list(dict.fromkeys(
            row for row in raw_weapons if row in known
        ))
        unlocked = removed_unlocks.get(item["row"], set())
        effective_removed = [
            row for row in source.get("removed_pool", [])
            if row not in unlocked
        ]
        entries.append({
            "row": item["row"],
            "kind": item["kind"],
            "display_name": item.get("name"),
            "rarity": item.get("rarity"),
            "global_merchant_eligible": item["row"] in merchant_rows,
            "production_weapon_count": len(production_weapons),
            "production_weapons": production_weapons,
            "widened_by_weapon_foundry": widened is not None,
            "effective_removed_pool": effective_removed,
            "dependent_upgrade_rows": source.get("additional_pool", []),
            "duplicate_status": (
                "requires_modifier_instance_provenance_or_native_duplicate_validation"
                if item.get("core_composition")
                else "native_duplicate_semantics_unverified"
            ),
            "secondary_skill_row": item.get("secondary_skill_row"),
        })

    for entry in entries:
        conflicts = set()
        for other in entries:
            if other["row"] == entry["row"]:
                continue
            if (
                other["row"] in entry["effective_removed_pool"]
                or entry["row"] in other["effective_removed_pool"]
            ):
                conflicts.add(other["row"])
        entry["transferable_conflicts"] = sorted(conflicts)

    entries.sort(key=lambda x: (x["kind"], x["row"]))
    weapon_capabilities = sorted(
        [
            {
                "row": w["row"],
                "name": w.get("name"),
                "category": w.get("category"),
                "lootable_shipping": w.get("lootable_shipping"),
                "cooling": w.get("cooling"),
                "warmup": w.get("warmup"),
                "scope": w.get("scope"),
                "temperature": w.get("temperature"),
                "primary_skill_row": next(
                    (
                        s.get("skill_row")
                        for s in (w.get("skills") or [])
                        if s.get("action") == "EAction::PrimaryFire"
                    ),
                    (w.get("skills") or [{}])[0].get("skill_row")
                    if (w.get("skills") or [])
                    else None,
                ),
            }
            for w in weapons
            if not w.get("separator")
        ],
        key=lambda x: x["row"],
    )

    payload = {
        "schema_version": 1,
        "name": "weapon-foundry-target-compatibility",
        "generated_from": [
            "research/generated/affixes.json",
            "research/generated/weapon_mods.json",
            "research/generated/weapons.json",
            "Source/patches/weapon_foundry_core.json",
            "Source/patches/weapon_foundry_mods.json",
            "Source/grafting/transfer_policy.json",
            "Source/patches/foundry_merchant.json",
        ],
        "policy": {
            "legality": "A target-aware GRAFT/Smith operation is legal only when the target weapon row is in production_weapons and no existing transferable row is in transferable_conflicts.",
            "global_merchant": "Only rows with global_merchant_eligible=true may be offered without inspecting target affix rows.",
            "duplicate_rows": "Do not deliberately add a duplicate row until its duplicate_status is promoted by runtime/provenance validation.",
            "legacy_weapon_names_filtered": True,
        },
        "summary": {
            "transferable_property_count": len(entries),
            "transferable_affix_count": sum(x["kind"] == "affix" for x in entries),
            "transferable_alt_fire_count": sum(x["kind"] == "weapon_mod" for x in entries),
            "global_merchant_affix_count": sum(x["global_merchant_eligible"] for x in entries),
            "known_weapon_row_count": len(weapon_capabilities),
            "rows_with_remaining_transferable_conflicts": sum(
                bool(x["transferable_conflicts"]) for x in entries
            ),
        },
        "properties": entries,
        "weapon_capabilities": weapon_capabilities,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"], indent=2))

if __name__ == "__main__":
    main()
