#!/usr/bin/env python3
"""Patch the Foundry affix purchase interactive with a quality-scaled complexity gate.

This patch intentionally inserts a new top-level Kismet statement. Absolute flow
targets are rebased with tools/kismet_layout.py.

The inserted guard is equivalent to:

    color = PlayerCharacter.currentWeapon.CurrentAffixBundle.Color
    cap = int(color) + base_affixes

    if not (color > 0 and PlayerCharacter.currentWeapon.AffixAmount < cap):
        return false

For Roboquest's observed five color/quality bytes (0..4) and base_affixes=2:
- Common (0): Foundry ordinary-affix purchase disabled;
- tier 1: cap 3;
- tier 2: cap 4;
- tier 3: cap 5;
- top tier (4): cap 6.

The existing vanilla checks (valid current weapon and not buying the same current
enchanted row) remain untouched.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

from kismet_layout import (
    expression_size,
    insert_top_level_statements,
    validate_asset,
)


class PatchError(RuntimeError):
    pass


FUNCTION = "CanInteract"
CDO_ASSET = "BP_Interactive_Merchant_AddEnchantedAffix"


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def ensure_name(asset: dict[str, Any], value: str) -> None:
    name_map = asset.get("NameMap")
    if not isinstance(name_map, list):
        raise PatchError("asset has no NameMap")
    if value not in name_map:
        name_map.append(value)
        asset["NamesReferencedFromExportDataCount"] = len(name_map)


def import_index(asset: dict[str, Any], object_name: str) -> int | None:
    matches = [
        -i for i, entry in enumerate(asset.get("Imports", []), start=1)
        if entry.get("ObjectName") == object_name
    ]
    if len(matches) > 1:
        raise PatchError(f"multiple imports named {object_name!r}")
    return matches[0] if matches else None


def require_import(asset: dict[str, Any], object_name: str) -> int:
    index = import_index(asset, object_name)
    if index is None:
        raise PatchError(f"required import missing: {object_name}")
    return index


def add_math_import(asset: dict[str, Any], function_name: str) -> int:
    existing = import_index(asset, function_name)
    if existing is not None:
        return existing

    math = require_import(asset, "KismetMathLibrary")
    ensure_name(asset, function_name)
    entry = {
        "$type": "UAssetAPI.Import, UAssetAPI",
        "ObjectName": function_name,
        "OuterIndex": math,
        "ClassPackage": "/Script/CoreUObject",
        "ClassName": "Object",
        "PackageName": None,
        "bImportOptional": False,
    }
    asset.setdefault("Imports", []).append(entry)
    return -len(asset["Imports"])


def add_roboquest_object_import(asset: dict[str, Any], object_name: str) -> int:
    existing = import_index(asset, object_name)
    if existing is not None:
        return existing

    roboquest = require_import(asset, "/Script/RoboQuest")
    ensure_name(asset, object_name)
    entry = {
        "$type": "UAssetAPI.Import, UAssetAPI",
        "ObjectName": object_name,
        "OuterIndex": roboquest,
        "ClassPackage": "/Script/CoreUObject",
        "ClassName": "Object",
        "PackageName": None,
        "bImportOptional": False,
    }
    asset.setdefault("Imports", []).append(entry)
    return -len(asset["Imports"])


def find_function(asset: dict[str, Any], name: str) -> tuple[int, dict[str, Any]]:
    matches = [
        (i + 1, exp)
        for i, exp in enumerate(asset.get("Exports", []))
        if "FunctionExport" in str(exp.get("$type", ""))
        and exp.get("ObjectName") == name
    ]
    if len(matches) != 1:
        raise PatchError(f"expected exactly one function {name!r}, found {len(matches)}")
    return matches[0]


def property_pointer(owner: int, path: str) -> dict[str, Any]:
    return {
        "$type": "UAssetAPI.Kismet.Bytecode.KismetPropertyPointer, UAssetAPI",
        "New": {
            "$type": "UAssetAPI.UnrealTypes.FFieldPath, UAssetAPI",
            "Path": [path],
            "ResolvedOwner": owner,
        },
    }


def local_variable(owner: int, path: str) -> dict[str, Any]:
    return {
        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_LocalVariable, UAssetAPI",
        "Variable": property_pointer(owner, path),
    }


def instance_variable(owner: int, path: str) -> dict[str, Any]:
    return {
        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_InstanceVariable, UAssetAPI",
        "Variable": property_pointer(owner, path),
    }


def context(object_expression: dict[str, Any], owner: int, path: str) -> dict[str, Any]:
    return {
        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_Context, UAssetAPI",
        "ObjectExpression": object_expression,
        "Offset": 9,
        "PropertyType": 0,
        "RValuePointer": property_pointer(owner, path),
        "ContextExpression": instance_variable(owner, path),
    }


def struct_member(
    struct_expression: dict[str, Any],
    owner: int,
    path: str,
) -> dict[str, Any]:
    return {
        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_StructMemberContext, UAssetAPI",
        "StructMemberExpression": property_pointer(owner, path),
        "StructExpression": struct_expression,
    }


def int_const(value: int) -> dict[str, Any]:
    return {
        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_IntConst, UAssetAPI",
        "Value": int(value),
    }


def byte_const(value: int) -> dict[str, Any]:
    return {
        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_ByteConst, UAssetAPI",
        "Value": int(value),
    }


def math_call(stack_node: int, parameters: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_CallMath, UAssetAPI",
        "StackNode": stack_node,
        "Parameters": parameters,
    }


def build_quality_scaled_condition(
    asset: dict[str, Any],
    function_export_index: int,
    base_affixes: int,
    max_affixes: int,
) -> dict[str, Any]:
    if base_affixes < 0:
        raise PatchError("base_affixes must be >= 0")
    if base_affixes + 4 != max_affixes:
        raise PatchError(
            "quality-scaled gate currently assumes observed color bytes 0..4; "
            "max_affixes must equal base_affixes + 4"
        )

    less_int = add_math_import(asset, "Less_IntInt")
    greater_byte = add_math_import(asset, "Greater_ByteByte")
    byte_to_int = add_math_import(asset, "Conv_ByteToInt")
    add_int = add_math_import(asset, "Add_IntInt")
    boolean_and = add_math_import(asset, "BooleanAND")

    character_player = require_import(asset, "Character_Player")
    aweapon = require_import(asset, "AWeapon")
    weapon_affix_rarity = add_roboquest_object_import(asset, "WeaponAffixRarity")

    for name in ("CurrentAffixBundle", "Color", "AffixAmount"):
        ensure_name(asset, name)

    player = local_variable(function_export_index, "PlayerCharacter")
    current_weapon = context(player, character_player, "currentWeapon")
    affix_amount = context(copy.deepcopy(current_weapon), aweapon, "AffixAmount")

    bundle = context(copy.deepcopy(current_weapon), aweapon, "CurrentAffixBundle")
    color = struct_member(bundle, weapon_affix_rarity, "Color")

    non_common = math_call(
        greater_byte,
        [copy.deepcopy(color), byte_const(0)],
    )
    color_int = math_call(
        byte_to_int,
        [copy.deepcopy(color)],
    )
    quality_cap = math_call(
        add_int,
        [color_int, int_const(base_affixes)],
    )
    under_cap = math_call(
        less_int,
        [affix_amount, quality_cap],
    )

    return math_call(
        boolean_and,
        [non_common, under_cap],
    )


def patch(
    asset: dict[str, Any],
    max_affixes: int,
    base_affixes: int = 2,
) -> tuple[dict[str, Any], dict[str, Any]]:
    patched = copy.deepcopy(asset)
    validate_asset(patched)

    fn_index, fn = find_function(patched, FUNCTION)
    code = fn.get("ScriptBytecode")
    if not isinstance(code, list) or fn.get("ScriptBytecodeRaw"):
        raise PatchError("CanInteract bytecode is not fully decoded")

    vanilla_guard = next(
        (
            expr for expr in code
            if str(expr.get("$type", "")).endswith("EX_JumpIfNot, UAssetAPI")
            and isinstance(expr.get("CodeOffset"), int)
        ),
        None,
    )
    if vanilla_guard is None:
        raise PatchError("could not locate vanilla CanInteract false branch")
    old_false_target = vanilla_guard["CodeOffset"]

    condition = build_quality_scaled_condition(
        patched,
        fn_index,
        base_affixes,
        max_affixes,
    )
    guard = {
        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_JumpIfNot, UAssetAPI",
        "CodeOffset": 0,
        "BooleanExpression": condition,
    }
    delta = expression_size(guard)
    guard["CodeOffset"] = old_false_target + delta

    report = insert_top_level_statements(fn, 0, [guard])
    validate_asset(patched)

    report.update({
        "asset": CDO_ASSET,
        "function": FUNCTION,
        "guard": "quality_scaled_foundry_complexity",
        "base_affixes": base_affixes,
        "max_affixes": max_affixes,
        "quality_caps": {
            "0": 0,
            "1": base_affixes + 1,
            "2": base_affixes + 2,
            "3": base_affixes + 3,
            "4": base_affixes + 4,
        },
        "old_false_target": old_false_target,
        "new_false_target": guard["CodeOffset"],
        "imports": {
            name: import_index(patched, name)
            for name in (
                "Less_IntInt",
                "Greater_ByteByte",
                "Conv_ByteToInt",
                "Add_IntInt",
                "BooleanAND",
                "WeaponAffixRarity",
            )
        },
    })
    return patched, report


def verify(
    asset: dict[str, Any],
    max_affixes: int,
    base_affixes: int = 2,
) -> dict[str, Any]:
    validate_asset(asset)
    _, fn = find_function(asset, FUNCTION)
    code = fn.get("ScriptBytecode") or []
    if not code:
        raise PatchError("CanInteract has no bytecode")

    first = code[0]
    if "EX_JumpIfNot" not in str(first.get("$type", "")):
        raise PatchError("Foundry quality gate is not first statement")
    condition = first.get("BooleanExpression") or {}

    boolean_and = import_index(asset, "BooleanAND")
    if boolean_and is None or condition.get("StackNode") != boolean_and:
        raise PatchError("Foundry quality gate does not end in BooleanAND")

    params = condition.get("Parameters") or []
    if len(params) != 2:
        raise PatchError("Foundry quality gate BooleanAND shape changed")

    non_common, under_cap = params
    greater_byte = import_index(asset, "Greater_ByteByte")
    less_int = import_index(asset, "Less_IntInt")
    add_int = import_index(asset, "Add_IntInt")
    byte_to_int = import_index(asset, "Conv_ByteToInt")

    if non_common.get("StackNode") != greater_byte:
        raise PatchError("Foundry quality gate does not block common-quality weapons")
    nc_params = non_common.get("Parameters") or []
    if len(nc_params) != 2 or nc_params[1].get("Value") != 0:
        raise PatchError("Foundry common-quality guard changed")

    if under_cap.get("StackNode") != less_int:
        raise PatchError("Foundry quality gate missing AffixAmount < cap")
    cap_params = under_cap.get("Parameters") or []
    if len(cap_params) != 2:
        raise PatchError("Foundry cap comparison shape changed")

    cap_expr = cap_params[1]
    if cap_expr.get("StackNode") != add_int:
        raise PatchError("Foundry cap is not color + base")
    add_params = cap_expr.get("Parameters") or []
    if len(add_params) != 2 or add_params[1].get("Value") != base_affixes:
        raise PatchError("Foundry base affix allowance changed")
    if add_params[0].get("StackNode") != byte_to_int:
        raise PatchError("Foundry cap does not convert quality color to int")

    serialized = json.dumps(first, separators=(",", ":"))
    for token in (
        '"PlayerCharacter"',
        '"currentWeapon"',
        '"AffixAmount"',
        '"CurrentAffixBundle"',
        '"Color"',
    ):
        if token not in serialized:
            raise PatchError(f"Foundry quality gate missing path token {token}")

    if base_affixes + 4 != max_affixes:
        raise PatchError("Foundry max/base configuration inconsistent")

    return {
        "verified": True,
        "asset": CDO_ASSET,
        "function": FUNCTION,
        "guard": "quality_scaled_foundry_complexity",
        "base_affixes": base_affixes,
        "max_affixes": max_affixes,
        "quality_caps": {
            "common": 0,
            "tier_1": base_affixes + 1,
            "tier_2": base_affixes + 2,
            "tier_3": base_affixes + 3,
            "top_tier": base_affixes + 4,
        },
        "script_bytecode_size": fn.get("ScriptBytecodeSize"),
        "guard_size": expression_size(first),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("input_json", type=Path)
    ap.add_argument("output_json", type=Path, nargs="?")
    ap.add_argument("--max-affixes", type=int, default=6)
    ap.add_argument("--base-affixes", type=int, default=2)
    ap.add_argument("--report", type=Path)
    ap.add_argument("--verify-only", action="store_true")
    args = ap.parse_args()

    asset = load(args.input_json)
    if args.verify_only:
        print(json.dumps(
            verify(asset, args.max_affixes, args.base_affixes),
            indent=2,
        ))
        return 0
    if args.output_json is None:
        raise SystemExit("output_json required unless --verify-only")

    patched, report = patch(
        asset,
        args.max_affixes,
        args.base_affixes,
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(patched, indent=2) + "\n", encoding="utf-8")
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
