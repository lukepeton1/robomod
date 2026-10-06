#!/usr/bin/env python3
"""Build compact catalogs from Roboquest FModel JSON property exports.

The generated files are research artifacts. They preserve installed-build identifiers and
references so implementation decisions can be made from game data instead of wiki lists.
Only Python's standard library is used so this can run in GitHub Actions or locally.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

NONE = {None, "", "None"}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_rows(path: Path) -> dict[str, Any]:
    doc = load_json(path)
    if not isinstance(doc, list) or not doc:
        raise ValueError(f"{path}: expected exported DataTable array")
    rows = doc[0].get("Rows")
    if not isinstance(rows, dict):
        raise ValueError(f"{path}: no Rows object")
    return rows


def asset_path(value: Any) -> str | None:
    if isinstance(value, dict):
        v = value.get("AssetPathName") or value.get("ObjectPath") or value.get("PathName")
        return None if v in NONE else v
    return None


def localized(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    for key in ("LocalizedString", "SourceString", "CultureInvariantString"):
        v = value.get(key)
        if isinstance(v, str) and v:
            return v
    return None


def handles(values: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for value in values or []:
        if not isinstance(value, dict):
            continue
        out.append({
            "table": asset_path(value.get("DataTable")),
            "row": value.get("RowName"),
        })
    return out


def custom_floats(values: Any) -> dict[str, float]:
    out: dict[str, float] = {}
    for entry in values or []:
        if not isinstance(entry, dict):
            continue
        key = entry.get("Key")
        if isinstance(key, str):
            out[key] = entry.get("Value")
    return out


def is_separator(name: str, cls: str | None, display: str | None) -> bool:
    return cls in NONE and display in NONE and ("====" in name or name.startswith("--"))


def blueprint_metadata(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        doc = load_json(path)
    except Exception:
        return {}
    if not isinstance(doc, list):
        return {}
    gc = next((o for o in doc if isinstance(o, dict) and o.get("Type") == "BlueprintGeneratedClass"), None)
    cdo = next((
        o for o in doc if isinstance(o, dict)
        and ("RF_ClassDefaultObject" in str(o.get("Flags", "")) or str(o.get("Name", "")).startswith("Default__"))
    ), None)
    functions = []
    for obj in doc:
        if not isinstance(obj, dict) or obj.get("Type") != "Function":
            continue
        locals_ = [cp.get("Name") for cp in (obj.get("ChildProperties") or []) if isinstance(cp, dict) and cp.get("Name")]
        call_hints = sorted({
            n[len("CallFunc_"):].rsplit("_ReturnValue", 1)[0]
            for n in locals_ if n.startswith("CallFunc_")
        })
        struct_hints = sorted({
            n[len("K2Node_MakeStruct_"):].rstrip("_0123456789")
            for n in locals_ if n.startswith("K2Node_MakeStruct_")
        })
        cast_hints = sorted({
            n[len("K2Node_DynamicCast_As"):]
            for n in locals_ if n.startswith("K2Node_DynamicCast_As")
        })
        params = []
        for cp in obj.get("ChildProperties") or []:
            if not isinstance(cp, dict) or "Parm" not in str(cp.get("PropertyFlags", "")):
                continue
            params.append({
                "name": cp.get("Name"),
                "type": cp.get("Type"),
                "struct": asset_path(cp.get("Struct")),
                "class": asset_path(cp.get("PropertyClass")),
            })
        functions.append({
            "name": obj.get("Name"),
            "flags": obj.get("FunctionFlags"),
            "override": (obj.get("SuperStruct") or {}).get("ObjectName") if isinstance(obj.get("SuperStruct"), dict) else None,
            "params": params,
            "call_hints": call_hints,
            "make_struct_hints": struct_hints,
            "dynamic_cast_hints": cast_hints,
        })
    props = cdo.get("Properties", {}) if isinstance(cdo, dict) else {}
    parent = None
    if isinstance(gc, dict):
        ss = gc.get("SuperStruct") or {}
        if isinstance(ss, dict):
            parent = ss.get("ObjectName") or ss.get("ObjectPath")
    return {
        "class": gc.get("Name") if isinstance(gc, dict) else None,
        "parent": parent,
        "cdo_properties": props,
        "functions": functions,
    }


def class_path_to_export(content_root: Path, class_path: str | None) -> Path | None:
    if not class_path or not class_path.startswith("/Game/"):
        return None
    pkg = class_path.split(".", 1)[0][len("/Game/"):]
    p = content_root / (pkg + ".json")
    return p if p.exists() else None


def skill_record(row_name: str, row: dict[str, Any]) -> dict[str, Any]:
    s = row.get("PlayerSkill", row)
    if not isinstance(s, dict):
        return {"row": row_name, "invalid": True}
    interesting_tags = {
        k: v for k, v in s.items()
        if "tag" in k.lower() and v not in (None, [], {}, "", "None")
    }
    return {
        "row": row_name,
        "skill_class": asset_path(s.get("SkillClass")),
        "damage": s.get("Damage"),
        "dps": s.get("DPS"),
        "critical_dps": s.get("CriticalDPS"),
        "damage_types": s.get("DamageTypes"),
        "firerate": s.get("Firerate"),
        "hit_amount": s.get("HitAmount"),
        "burst_amount": s.get("BurstAmount"),
        "burst_firerate": s.get("BurstFirerate"),
        "cost": s.get("Cost") or [],
        "applied_status": s.get("AppliedStatus") or [],
        "self_applied_status": s.get("SelfAppliedStatus") or [],
        "target_detection": s.get("TargetDetection"),
        "aoe_detection": s.get("AOEDetection"),
        "area_radius": s.get("AreaRadius"),
        "range": s.get("Range"),
        "max_targets": s.get("MaxTargets"),
        "ricochet_amount": s.get("RicochetAmount"),
        "ricochet_damage_ratio": s.get("RicochetDamageRatio"),
        "projectile_class": asset_path(s.get("ProjectileClass")),
        "projectile_pool": s.get("ProjectilePool"),
        "prefab_projectile": s.get("bPrefabProjectile"),
        "no_collision_projectile": s.get("bNoCollisionProjectile"),
        "collision_size": s.get("CollisionSize"),
        "projectile_speed": s.get("Speed"),
        "bounce": s.get("bBounce"),
        "bounce_amount": s.get("BounceAmount"),
        "bounciness": s.get("Bounciness"),
        "friction": s.get("Friction"),
        "trigger_area_on_bounce": s.get("bTriggerAreaOnBounce"),
        "sticking": s.get("bSticking"),
        "trigger_type": s.get("TriggerType"),
        "trigger_range": s.get("TriggerRange"),
        "trigger_time": s.get("TriggerTime"),
        "gravity_scale": s.get("GravityScale"),
        "homing": s.get("bHoming"),
        "homing_delay": s.get("HomingDelay"),
        "homing_acceleration": s.get("HomingAccelerationMagnitude"),
        "homing_range": s.get("HomingRange"),
        "homing_dot_tolerance": s.get("HomingDotTolerance"),
        "lifetime": s.get("Lifetime"),
        "max_projectile_init_per_frame": s.get("MaxProjectileInitPerFrame"),
        "summon_class": asset_path(s.get("SummonClass")),
        "cooldown": s.get("SkillCooldown"),
        "custom": custom_floats(s.get("CustomFloatProperties")),
        "tag_fields": interesting_tags,
    }


def affix_record(row_name: str, row: dict[str, Any], content_root: Path) -> dict[str, Any]:
    a = row.get("Affix", row)
    if not isinstance(a, dict):
        return {"row": row_name, "invalid": True}
    cls = asset_path(a.get("Affix"))
    bp_path = class_path_to_export(content_root, cls)
    bp = blueprint_metadata(bp_path) if bp_path else {}
    cdo_props = bp.get("cdo_properties") or {}
    return {
        "row": row_name,
        "name": localized(a.get("Name")),
        "description": localized(a.get("Description")),
        "class": cls,
        "parent": bp.get("parent"),
        "rarity": a.get("Rarity"),
        "enchanted": a.get("bEnchantedAffix"),
        "active": a.get("bActivate"),
        "perfumer_icon": a.get("PerfumerIcon"),
        "custom": custom_floats(a.get("CustomFloatProperties")),
        "additional_pool": [x.get("RowName") for x in a.get("AdditionalPool") or [] if isinstance(x, dict)],
        "removed_pool": [x.get("RowName") for x in a.get("RemovedPool") or [] if isinstance(x, dict)],
        "weapons": a.get("Weapons") or [],
        "separator": is_separator(row_name, cls, localized(a.get("Name"))),
        "blueprint": {
            "functions": bp.get("functions") or [],
            "cdo_in_class": asset_path(cdo_props.get("InClass")),
            "cdo_properties": {
                k: v for k, v in cdo_props.items()
                if k not in {"UberGraphFrame", "DefaultSceneRoot", "DefaultSceneRoot_GEN_VARIABLE"}
            },
        } if bp else None,
    }


def class_package(value: str | None) -> str | None:
    if not value:
        return None
    return value.split(".", 1)[0]


def class_row_hint(value: str | None) -> str | None:
    """Derive a likely DataTable row from a Blueprint package name.

    Roboquest sometimes uses a dedicated Blueprint class whose DT row points at another
    implementation class. The row name still commonly mirrors the weapon/action asset
    (BP_PF_Slingshot -> PF_SlingShot; BP_SF_SuperbotMod -> SF_SuperbotMod).
    """
    pkg = class_package(value)
    if not pkg:
        return None
    base = pkg.rsplit("/", 1)[-1]
    return base[3:] if base.startswith("BP_") else base


def ci_row_lookup(rows: dict[str, Any]) -> dict[str, str]:
    return {name.casefold(): name for name in rows}


def weapon_record(
    row_name: str,
    row: dict[str, Any],
    skill_by_class: dict[str, str],
    skill_rows_by_name: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    w = row.get("Weapon", row)
    if not isinstance(w, dict):
        return {"row": row_name, "invalid": True}
    skills = []
    for entry in w.get("Skills") or []:
        if not isinstance(entry, dict):
            continue
        cls = asset_path(entry.get("Value"))
        action = entry.get("Key")
        conventional = None
        if action == "EAction::PrimaryFire":
            conventional = f"PF_{row_name}"
        elif action == "EAction::SecondaryFire":
            conventional = f"SF_{row_name}"
        by_ci = ci_row_lookup(skill_rows_by_name)
        class_hint = class_row_hint(cls)
        resolved = conventional if conventional in skill_rows_by_name else None
        reason = "row_convention" if resolved else None
        if not resolved and conventional:
            resolved = by_ci.get(conventional.casefold())
            reason = "row_convention_ci" if resolved else None
        if not resolved and class_hint:
            resolved = by_ci.get(class_hint.casefold())
            reason = "class_name_row_hint" if resolved else None
        if not resolved:
            resolved = skill_by_class.get(cls)
            reason = "class" if resolved else None
        skills.append({
            "action": action,
            "class": cls,
            "skill_row": resolved,
            "resolved_by": reason,
        })
    return {
        "row": row_name,
        "name": localized(w.get("Name")),
        "category": w.get("LootCategory"),
        "weapon_class": asset_path(w.get("WeaponClass")),
        "skills": skills,
        "preset_affixes": [x.get("RowName") for x in w.get("Affixes") or [] if isinstance(x, dict)],
        "random_affix_bundles": handles(w.get("RandomAffixBundles")),
        "random_affixes": handles(w.get("RandomAffixes")),
        "ammo_in_clip": w.get("AmmoInClip"),
        "reload_duration": w.get("ReloadDuration"),
        "loot_level": w.get("LootLevel"),
        "custom": custom_floats(w.get("CustomFloatProperties")),
        "limited_clip": w.get("bLimitedClip"),
        "scope": w.get("bScope"),
        "warmup": w.get("bWarmup"),
        "cooling": w.get("bCooling"),
        "temperature": w.get("bTemperature"),
        "lootable": w.get("bLootable"),
        "lootable_shipping": w.get("bLootableInShippingBuild"),
        "in_compendium": w.get("bIsInCompendium"),
        "exclude_for_superbot": w.get("bExcludeForSuperbot"),
        "generation": w.get("Generation"),
        "mesh": asset_path(w.get("Mesh")),
        "icon": asset_path(w.get("Icon")),
        "separator": is_separator(row_name, asset_path(w.get("WeaponClass")), localized(w.get("Name"))),
    }


def item_record(row_name: str, row: dict[str, Any], content_root: Path) -> dict[str, Any]:
    cls = asset_path(row.get("Class"))
    bp_path = class_path_to_export(content_root, cls)
    bp = blueprint_metadata(bp_path) if bp_path else {}
    return {
        "row": row_name,
        "name": localized(row.get("Name")),
        "description": localized(row.get("Description")),
        "class": cls,
        "parent": bp.get("parent"),
        "rarity": row.get("Rarity"),
        "cost": row.get("Cost"),
        "lootable": row.get("bLootable"),
        "lootable_in_chest": row.get("bLootableInChest"),
        "multiplayer_only": row.get("bMultiplayerOnly"),
        "exclude_for_superbot": row.get("bExcludeForSuperbot"),
        "custom": custom_floats(row.get("CustomFloatProperties")),
        "linked_items": handles(row.get("LinkedItems")),
        "added_items": handles(row.get("AddedItems")),
        "blueprint_functions": bp.get("functions") or [],
        "separator": is_separator(row_name, cls, localized(row.get("Name"))),
    }


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--content-root", type=Path, default=Path("vanilla-json/RoboQuest/Content"))
    ap.add_argument("--out", type=Path, default=Path("research/generated"))
    args = ap.parse_args()

    content = args.content_root
    data = content / "Data"
    out = args.out

    skill_rows = load_rows(data / "DT_PlayerSkills.json")
    mod_skill_rows = load_rows(data / "DT_ModSkills.json")
    weapon_rows = load_rows(data / "DT_Weapons.json")
    affix_rows = load_rows(data / "DT_WeaponAffix.json")
    mod_rows = load_rows(data / "DT_WeaponMod.json")
    item_rows = load_rows(data / "DT_Items.json")

    skills = [skill_record(k, v) for k, v in skill_rows.items()]
    mod_skills = [skill_record(k, v) for k, v in mod_skill_rows.items()]
    skill_by_class = {
        s["skill_class"]: s["row"] for s in skills
        if s.get("skill_class")
    }
    mod_skill_by_package = {
        class_package(s["skill_class"]): s["row"] for s in mod_skills
        if s.get("skill_class")
    }
    mod_skill_rows_ci = ci_row_lookup(mod_skill_rows)

    weapons = [weapon_record(k, v, skill_by_class, skill_rows) for k, v in weapon_rows.items()]
    affixes = [affix_record(k, v, content) for k, v in affix_rows.items()]
    mods = [affix_record(k, v, content) for k, v in mod_rows.items()]
    items = [item_record(k, v, content) for k, v in item_rows.items()]

    for mod in mods:
        in_class = ((mod.get("blueprint") or {}).get("cdo_in_class"))
        mod["secondary_skill_class"] = in_class
        row_hint = class_row_hint(in_class)
        mod["secondary_skill_row"] = (
            mod_skill_by_package.get(class_package(in_class))
            or (mod_skill_rows_ci.get(row_hint.casefold()) if row_hint else None)
        )

    real_weapons = [w for w in weapons if not w.get("separator") and w.get("weapon_class")]
    active_affixes = [a for a in affixes if not a.get("separator") and a.get("active")]
    active_mods = [m for m in mods if not m.get("separator") and m.get("active")]

    # Invert compatibility for fast graft validation.
    weapon_eligibility: dict[str, dict[str, list[str]]] = {}
    for w in real_weapons:
        wid = w["row"]
        weapon_eligibility[wid] = {
            "common_rare_affixes": sorted([
                a["row"] for a in active_affixes if wid in (a.get("weapons") or [])
            ]),
            "weapon_mods": sorted([
                m["row"] for m in active_mods if wid in (m.get("weapons") or [])
            ]),
        }

    keywords = re.compile(
        r"bounce|pierce|homing|seeker|fragment|explos|ricochet|freewheel|buckshot|"
        r"burn|shock|cryo|ice|element|mark|secondary|loaded|projectile|raycast",
        re.I,
    )
    primitives = [
        {
            "row": a["row"],
            "name": a.get("name"),
            "description": a.get("description"),
            "class": a.get("class"),
            "parent": a.get("parent"),
            "rarity": a.get("rarity"),
            "custom": a.get("custom"),
            "additional_pool": a.get("additional_pool"),
            "removed_pool": a.get("removed_pool"),
            "compatible_weapon_count": len(a.get("weapons") or []),
            "blueprint": a.get("blueprint"),
        }
        for a in active_affixes
        if keywords.search(" ".join(str(x or "") for x in (
            a["row"], a.get("name"), a.get("description"), a.get("class")
        )))
    ]

    write_json(out / "player_skills.json", skills)
    write_json(out / "mod_skills.json", mod_skills)
    write_json(out / "weapons.json", weapons)
    write_json(out / "affixes.json", affixes)
    write_json(out / "weapon_mods.json", mods)
    write_json(out / "items.json", items)
    write_json(out / "weapon_eligibility.json", weapon_eligibility)
    write_json(out / "synergy_primitives.json", primitives)

    # Small summary intended for humans and CI logs.
    skill_hit_types = Counter(s.get("target_detection") for s in skills if s.get("skill_class"))
    affix_rarities = Counter(a.get("rarity") for a in active_affixes)
    category_counts = Counter(w.get("category") for w in real_weapons if w.get("lootable_shipping"))
    unresolved_weapon_skills = [
        {"weapon": w["row"], **s}
        for w in real_weapons for s in w.get("skills", [])
        if s.get("class") and not s.get("skill_row")
    ]
    unresolved_mod_skills = [
        {"mod": m["row"], "class": m.get("secondary_skill_class")}
        for m in active_mods
        if m.get("secondary_skill_class") and not m.get("secondary_skill_row")
    ]

    summary = {
        "counts": {
            "weapon_table_rows": len(weapons),
            "weapon_chassis_rows": len(real_weapons),
            "shipping_lootable_weapon_rows": sum(bool(w.get("lootable_shipping")) for w in real_weapons),
            "player_skill_rows": len(skills),
            "player_skill_classes": sum(bool(s.get("skill_class")) for s in skills),
            "affix_rows": len(affixes),
            "active_affixes": len(active_affixes),
            "weapon_mod_rows": len(mods),
            "active_weapon_mods": len(active_mods),
            "mod_skill_rows": len(mod_skills),
            "item_rows": len(items),
            "synergy_primitive_rows": len(primitives),
        },
        "shipping_weapon_categories": dict(sorted(category_counts.items())),
        "player_skill_hit_types": dict(sorted(skill_hit_types.items(), key=lambda x: str(x[0]))),
        "affix_rarities": dict(sorted(affix_rarities.items(), key=lambda x: str(x[0]))),
        "unresolved_weapon_skill_links": unresolved_weapon_skills,
        "unresolved_mod_skill_links": unresolved_mod_skills,
    }
    write_json(out / "summary.json", summary)

    lines = [
        "# Generated catalog summary",
        "",
        "Generated from the installed-build JSON property export. Do not hand-edit files in this directory.",
        "",
        "## Counts",
        "",
    ]
    for k, v in summary["counts"].items():
        lines.append(f"- **{k}**: {v}")
    lines += ["", "## Player skill hit modes", ""]
    for k, v in summary["player_skill_hit_types"].items():
        lines.append(f"- **{k}**: {v}")
    lines += ["", "## Affix rarities", ""]
    for k, v in summary["affix_rarities"].items():
        lines.append(f"- **{k}**: {v}")
    lines += ["", "## Link integrity", ""]
    lines.append(f"- Unresolved weapon skill class -> DT_PlayerSkills rows: **{len(unresolved_weapon_skills)}**")
    lines.append(f"- Unresolved mod skill class -> DT_ModSkills rows: **{len(unresolved_mod_skills)}**")
    (out / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
