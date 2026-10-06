#!/usr/bin/env python3
"""Generate behavior/inheritance profiles for production native alt-fires."""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "Source/grafting/transfer_policy.json"
MODS = ROOT / "research/generated/weapon_mods.json"
SKILLS = ROOT / "research/generated/mod_skills.json"
OUTPUT = ROOT / "Source/composition/alt_fire_skill_profiles.json"

BEHAVIOR = {
    "Barrier": "utility_raycast",
    "Bayonet": "melee_raycast",
    "BlunderMine": "sticky_explosive_projectile",
    "ChargedOrb": "sticky_prefab_projectile",
    "CombiShotgun": "raycast_volley",
    "CombiSniper": "raycast_precision",
    "DoubleTap": "primary_retrigger",
    "Energize": "state_buff",
    "LaserShotgun": "projectile_volley",
    "LongSlash": "prefab_projectile",
    "MarkExplosion": "mark_projectile",
    "MarkRaycast": "mark_raycast",
    "MissileLauncher": "homing_explosive_projectile",
    "PlasmaGrenade": "sticky_explosive_projectile",
    "RocketJump": "self_explosion_utility"
}

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

def main():
    policy, mods, skills = load(POLICY), load(MODS), load(SKILLS)
    mod_by = {x["row"]: x for x in mods}
    skill_by = {x["row"]: x for x in skills}
    profiles = []

    for item in policy["transferable"]:
        if item["kind"] != "weapon_mod":
            continue
        mod = mod_by[item["row"]]
        skill = skill_by[mod["secondary_skill_row"]]
        hit = skill["target_detection"]
        profiles.append({
            "row": item["row"],
            "name": item.get("name"),
            "secondary_skill_row": mod["secondary_skill_row"],
            "behavior": BEHAVIOR[item["row"]],
            "target_detection": hit,
            "hit_amount": skill["hit_amount"],
            "damage": skill["damage"],
            "damage_types": skill["damage_types"],
            "area_radius": skill["area_radius"],
            "projectile_class": skill["projectile_class"],
            "prefab_projectile": skill["prefab_projectile"],
            "sticking": skill["sticking"],
            "intrinsic_homing": skill["homing"],
            "intrinsic_bounce": skill["bounce"],
            "cooldown": skill["cooldown"],
            "native_affix_inheritance": {
                "elements": "expected: Burn/Cryo/Shock subscribe to newly registered skills",
                "buckshot": "expected: AutoShotgun handles DelegateOnAddSkill",
                "seeker": "not automatic: Homing currently mutates the primary skill unless the secondary is intrinsically homing",
                "bounce": "not automatic: Bounce currently mutates the primary skill unless the secondary is intrinsically bouncing",
                "pierce": "not automatic: Pierce currently mutates the primary skill",
                "fragmentation": "binding-order dependent; explicit secondary-skill validation required",
                "freewheel": "primary-skill retrigger semantic; not treated as generic alt-fire duplication",
            },
            "validation_priority": (
                "high_projectile_inheritance" if hit == "EHitType::Projectile"
                else "high_raycast_inheritance" if hit == "EHitType::Raycast"
                else "state_or_utility"
            ),
        })

    payload = {
        "schema_version": 1,
        "name": "weapon-foundry-alt-fire-skill-profiles",
        "generated_from": [
            "Source/grafting/transfer_policy.json",
            "research/generated/weapon_mods.json",
            "research/generated/mod_skills.json",
        ],
        "production_alt_fire_count": len(profiles),
        "propagation_model": {
            "already_native_new_skill_observers": ["Burn","Cryo","Shock","AutoShotgun"],
            "primary_skill_only_or_unverified": ["Homing","Bounce","Pierce","Fragmentation","FreeShot"],
            "principle": "Do not blanket-copy every primary modifier to every secondary skill; use the profile and semantic compatibility.",
        },
        "profiles": profiles,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT}: {len(profiles)} production alt-fire profiles")

if __name__ == "__main__":
    main()
