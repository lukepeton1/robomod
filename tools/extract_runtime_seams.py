#!/usr/bin/env python3
"""Extract compact signatures for the Roboquest runtime seams used by Weapon Foundry.

FModel/UAssetAPI JSON is extremely verbose. This script keeps only class ancestry,
Blueprint-visible class properties, function signatures, call/cast/struct hints, CDO
properties, and selected RPC metadata from the small group of assets relevant to
composition, grafting, save/load, multiplayer and weapon UI.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CONTENT = Path("vanilla-json/RoboQuest/Content")
OUT = Path("research/generated/runtime_seams.json")

ASSETS = [
    # Core weapon / affix behavior
    "Blueprint/Weapon/BP_AWeapon.json",
    "Blueprint/Weapon/Affixes/BP_AWeaponAffix.json",
    "Blueprint/Weapon/Affixes/BP_AWeaponAffix_AddSecondaryFire.json",
    "Blueprint/Weapon/Affixes/BP_AWeaponAffix_TriggerSkillCount.json",
    "Blueprint/Weapon/Affixes/BP_AWeaponAffix_TriggerSkillLuck.json",
    "Blueprint/Weapon/Affixes/BP_AWeaponAffix_OnDealDamage.json",
    "Blueprint/Weapon/Affixes/BP_AWeaponAffix_OnHitHitEffect.json",
    "Blueprint/Weapon/Affixes/BP_AWeaponAffix_OnHitHitEffect_LaunchSkill.json",
    "Blueprint/Weapon/Affixes/BP_WA_TriggerSkillCount_LaunchSkill.json",
    "Blueprint/Weapon/Affixes/Common/BP_WA_Fragmentation.json",
    "Blueprint/Weapon/Affixes/Common/BP_WA_Explosive.json",
    "Blueprint/Weapon/Affixes/Common/BP_WA_ExplosiveBlank.json",
    "Blueprint/Weapon/Affixes/Common/BP_WA_AddRicochet.json",
    "Blueprint/Weapon/Affixes/Prefab/BP_WA_AutoShotgun.json",
    "Blueprint/Weapon/Affixes/Prefab/BP_WA_AutoShotgun_Explosion.json",
    "Blueprint/Weapon/Affixes/Prefab/BP_WA_FreeShot.json",
    "Blueprint/Weapon/Affixes/Prefab/BP_WA_Bounce.json",
    "Blueprint/Weapon/Affixes/Prefab/BP_WA_Pierce.json",
    "Blueprint/Weapon/Affixes/Prefab/BP_WA_Ricochet.json",
    "Blueprint/Weapon/Affixes/Prefab/BP_WA_Homing.json",
    "Blueprint/Weapon/Affixes/Prefab/BP_WA_ProjectileRaycast.json",
    "Blueprint/Weapon/Affixes/Prefab/BP_WA_Burn.json",
    "Blueprint/Weapon/Affixes/Prefab/BP_WA_Ice.json",
    "Blueprint/Weapon/Affixes/Prefab/BP_WA_Shock.json",

    # Authoritative mutation / save paths
    "Blueprint/Player/BP_APlayer.json",
    "Blueprint/GameSystem/GameInstance/BP_AGameInstance.json",
    "Blueprint/GameSystem/SaveGame/BP_SaveGame_Profile.json",

    # Existing customization / merchant surfaces
    "Blueprint/Interactive/Merchant/BP_Interactive_Merchant_AddEnchantedAffix.json",
    "Blueprint/Interactive/Merchant/BP_Interactive_Merchant_RerollAffix.json",
    "Blueprint/Interactive/Merchant/BP_Interactive_Merchant_UpgradeWeaponQuality.json",
    "Blueprint/Interactive/Merchant/BP_Merchant_UpgradeAffix.json",
    "Blueprint/Interactive/Merchant/BP_Merchant_Weapon.json",
    "Blueprint/Interactive/Quest/BP_Quest_SmithingTed.json",
]

FUNCTION_FOCUS = {
    "AddEnchantedAffix",
    "OnServerAddEnchantedAffix",
    "OnMulticastAddEnchantedAffix",
    "OnServerRerollAffix",
    "MulticastRerollAffix",
    "OnServerMulticastUpgradeQuality",
    "OnMulticastUpgradeQuality",
    "SaveRun",
    "GeneratePlayerSaveRunData",
    "GetPlayerSavedRunData",
    "GetGeneratorSavedRunData",
    "GetFragNetworkInfo",
    "GetGameplayTags",
    "SpawnCustomProjectiles",
    "OnApply",
    "OnRemove",
    "OnSkillTrigger",
    "OnUsed",
    "OnUsedSkill",
    "OnDealDamage",
    "BindSkillEvent",
    "IsSkillConditionValid",
    "GetModifiedSpawnRotationOffset",
    "GetSpawnRotation",
    "InitSkillDamageModifier",
    "Interact",
    "OnInteract",
    "GetInteractionText",
    "GetCost",
    "CanInteract",
}


def ref_name(v: Any) -> Any:
    if isinstance(v, dict):
        return v.get("ObjectPath") or v.get("ObjectName") or v.get("AssetPathName")
    return v


def compact_value(v: Any, depth: int = 0) -> Any:
    if depth > 4:
        return "<truncated>" if isinstance(v, (dict, list)) else v
    if isinstance(v, dict):
        out = {}
        for k, x in v.items():
            if k in {"UberGraphFrame", "SimpleConstructionScript", "InheritableComponentHandler"}:
                continue
            out[k] = compact_value(x, depth + 1)
        return out
    if isinstance(v, list):
        cap = 80
        out = [compact_value(x, depth + 1) for x in v[:cap]]
        if len(v) > cap:
            out.append(f"<+{len(v)-cap} more>")
        return out
    return v


def property_record(cp: dict[str, Any]) -> dict[str, Any]:
    out = {
        "name": cp.get("Name"),
        "type": cp.get("Type"),
        "flags": cp.get("PropertyFlags"),
    }
    for key in ("PropertyClass", "Struct", "Enum", "InterfaceClass", "MetaClass"):
        if cp.get(key):
            out[key.lower()] = ref_name(cp[key])
    if cp.get("Inner"):
        out["inner"] = property_record(cp["Inner"])
    return out


def function_record(obj: dict[str, Any]) -> dict[str, Any]:
    cps = [x for x in (obj.get("ChildProperties") or []) if isinstance(x, dict)]
    names = [x.get("Name") for x in cps if x.get("Name")]
    params = [
        property_record(x)
        for x in cps
        if "Parm" in str(x.get("PropertyFlags", ""))
    ]
    calls = sorted({
        n[len("CallFunc_"):].rsplit("_ReturnValue", 1)[0]
        for n in names if n.startswith("CallFunc_")
    })
    casts = sorted({
        n[len("K2Node_DynamicCast_As"):]
        for n in names if n.startswith("K2Node_DynamicCast_As")
    })
    made_structs = sorted({
        ref_name(x.get("Struct"))
        for x in cps
        if x.get("Name", "").startswith("K2Node_MakeStruct_") and x.get("Struct")
    })
    struct_types = sorted({
        ref_name(x.get("Struct"))
        for x in cps if x.get("Struct")
    })
    object_types = sorted({
        ref_name(x.get("PropertyClass"))
        for x in cps if x.get("PropertyClass")
    })
    return {
        "name": obj.get("Name"),
        "flags": obj.get("FunctionFlags"),
        "override": ref_name(obj.get("SuperStruct")),
        "params": params,
        "call_hints": calls,
        "dynamic_cast_hints": casts,
        "made_structs": made_structs,
        "struct_types": struct_types,
        "object_types": object_types,
    }


def asset_record(rel: str) -> dict[str, Any]:
    path = CONTENT / rel
    if not path.exists():
        return {"path": rel, "missing": True}
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(doc, list):
        doc = [doc]
    gc = next((o for o in doc if isinstance(o, dict) and o.get("Type") == "BlueprintGeneratedClass"), None)
    cdo = next((
        o for o in doc if isinstance(o, dict)
        and ("RF_ClassDefaultObject" in str(o.get("Flags", "")) or str(o.get("Name", "")).startswith("Default__"))
    ), None)

    all_functions = [function_record(o) for o in doc if isinstance(o, dict) and o.get("Type") == "Function"]
    interesting = []
    for f in all_functions:
        if (
            f["name"] in FUNCTION_FOCUS
            or f["name"].startswith(("OnServer", "OnMulticast", "Multicast"))
            or any(token in f["name"] for token in ("Affix", "Weapon", "Skill", "Save"))
        ):
            interesting.append(f)

    return {
        "path": rel,
        "class": gc.get("Name") if gc else None,
        "parent": ref_name((gc or {}).get("Super") or (gc or {}).get("SuperStruct")),
        "class_flags": (gc or {}).get("ClassFlags"),
        "class_properties": [property_record(x) for x in ((gc or {}).get("ChildProperties") or []) if isinstance(x, dict)],
        "cdo_properties": compact_value((cdo or {}).get("Properties") or {}),
        "functions": interesting,
        "all_function_names": [f["name"] for f in all_functions],
    }


def main() -> int:
    records = [asset_record(rel) for rel in ASSETS]
    missing = [x["path"] for x in records if x.get("missing")]
    payload = {
        "schema_version": 1,
        "asset_count": len(records),
        "missing_assets": missing,
        "assets": records,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT}: {len(records)} assets, {len(missing)} missing")
    if missing:
        print("missing:")
        for x in missing:
            print(f"  {x}")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
