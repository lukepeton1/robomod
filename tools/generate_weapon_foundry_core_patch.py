#!/usr/bin/env python3
"""Generate the production Weapon Foundry DT_WeaponAffix patch from research catalogs."""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AFFIXES = ROOT / "research/generated/affixes.json"
WEAPONS = ROOT / "research/generated/weapons.json"
SKILLS = ROOT / "research/generated/player_skills.json"
OUTPUT = ROOT / "Source/patches/weapon_foundry_core.json"

BROAD_ROWS = ["Bounce", "Pierce", "Ricochet", "FreeShot", "AutoShotgun", "Fragmentation", "ExplosiveBlank"]

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

def main():
    affixes, weapons, skills = load(AFFIXES), load(WEAPONS), load(SKILLS)
    skill_by_row = {x["row"]: x for x in skills}
    burn = next(x for x in affixes if x["row"] == "Burn")["weapons"]

    hit_by_weapon = {}
    for weapon in weapons:
        skill_links = weapon.get("skills") or []
        primary = next((s for s in skill_links if s.get("action") == "EAction::PrimaryFire"), None)
        primary = primary or (skill_links[0] if skill_links else None)
        skill = skill_by_row.get((primary or {}).get("skill_row"))
        hit_by_weapon[weapon["row"]] = (skill or {}).get("target_detection")

    standard = [
        row for row in burn
        if hit_by_weapon.get(row) in {"EHitType::Projectile", "EHitType::Raycast"}
    ]
    projectile = [row for row in burn if hit_by_weapon.get(row) == "EHitType::Projectile"]

    operations = [
        {"op":"remove_row_handles","row":"Burn","field":"RemovedPool","values":["Ice","Shock"],"reason":"Verified independent native elemental tags."},
        {"op":"remove_row_handles","row":"Ice","field":"RemovedPool","values":["Burn","Shock"],"reason":"Verified independent native elemental tags."},
        {"op":"remove_row_handles","row":"Shock","field":"RemovedPool","values":["Burn","Ice"],"reason":"Verified independent native elemental tags."},
        {"op":"remove_row_handles","row":"Bounce","field":"RemovedPool","values":["Ricochet"],"reason":"Native traversal states are independent."},
        {"op":"remove_row_handles","row":"Ricochet","field":"RemovedPool","values":["Bounce"],"reason":"Native traversal states are independent."},
        {"op":"remove_row_handles","row":"Pierce","field":"RemovedPool","values":["Explosive2","Explosive3","Explosive4","Explosive5"],"reason":"Native pierce and explosive proc states are independent."},
    ]
    for row in ["Explosive2","Explosive3","Explosive4","Explosive5","ExplosiveBlank"]:
        operations.append({"op":"remove_row_handles","row":row,"field":"RemovedPool","values":["Pierce","Bounce"],"reason":"Verified/decoded native explosive state can coexist with traversal."})
    operations.extend([
        {"op":"remove_row_handles","row":"Homing","field":"RemovedPool","values":["AutoShotgun"],"reason":"Phase 3 in-game test confirmed Seeker + Buckshot on a projectile skill."},
        {"op":"remove_row_handles","row":"AutoShotgun","field":"RemovedPool","values":["Homing"],"reason":"Phase 3 in-game test confirmed Seeker + Buckshot on a projectile skill."},
    ])
    for row in BROAD_ROWS:
        operations.append({
            "op":"replace_name_array","row":row,"field":"Weapons","values":standard,
            "reason":"Broaden verified standard hit-model composition primitives across projectile/raycast weapon chassis while excluding None/AIM/unknown edge cases."
        })
    operations.append({
        "op":"replace_name_array","row":"Homing","field":"Weapons","values":projectile,
        "reason":"Broaden Seeker only across already-projectile primary skills until the raycast-to-projectile resolver is implemented."
    })

    payload = {
        "schema_version": 1,
        "name": "weapon-foundry-core",
        "target": "Data/DT_WeaponAffix",
        "status": "production_core_v0",
        "generated_from": "research/generated/{weapons,player_skills,affixes}.json",
        "policy": {
            "standard_hit_types": ["EHitType::Projectile","EHitType::Raycast"],
            "standard_weapon_count": len(standard),
            "projectile_weapon_count": len(projectile),
            "unresolved_edge_cases": [
                {"weapon": row, "hit_type": hit_by_weapon.get(row)}
                for row in burn if row not in standard
            ],
        },
        "operations": operations,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT}: {len(operations)} operations, {len(standard)} standard, {len(projectile)} projectile")

if __name__ == "__main__":
    main()
