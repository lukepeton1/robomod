#!/usr/bin/env python3
"""Patch the Foundry affix purchase interactive with a native AffixAmount cap.

This is the first Weapon Foundry patch that intentionally inserts a new top-level
Kismet statement. Absolute flow targets are rebased with tools/kismet_layout.py.

The inserted guard is equivalent to:

    if not (PlayerCharacter.currentWeapon.AffixAmount < max_affixes):
        return false

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
    KismetLayoutError,
    expression_size,
    insert_top_level_statements,
    script_size,
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
        "Offset": 9,  # one InstanceVariable expression
        "PropertyType": 0,
        "RValuePointer": property_pointer(owner, path),
        "ContextExpression": instance_variable(owner, path),
    }


def build_affix_count_condition(
    asset: dict[str, Any],
    function_export_index: int,
    max_affixes: int,
) -> dict[str, Any]:
    less_int = add_math_import(asset, "Less_IntInt")
    character_player = require_import(asset, "Character_Player")
    aweapon = require_import(asset, "AWeapon")

    player = local_variable(function_export_index, "PlayerCharacter")
    current_weapon = context(player, character_player, "currentWeapon")
    affix_amount = context(current_weapon, aweapon, "AffixAmount")

    return {
        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_CallMath, UAssetAPI",
        "StackNode": less_int,
        "Parameters": [
            affix_amount,
            {
                "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_IntConst, UAssetAPI",
                "Value": int(max_affixes),
            },
        ],
    }


def patch(asset: dict[str, Any], max_affixes: int) -> tuple[dict[str, Any], dict[str, Any]]:
    patched = copy.deepcopy(asset)
    validate_asset(patched)

    fn_index, fn = find_function(patched, FUNCTION)
    code = fn.get("ScriptBytecode")
    if not isinstance(code, list) or fn.get("ScriptBytecodeRaw"):
        raise PatchError("CanInteract bytecode is not fully decoded")

    # Vanilla's first JumpIfNot branches to the false-return statement. Preserve that
    # semantic target instead of hardcoding a package-specific offset.
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

    condition = build_affix_count_condition(patched, fn_index, max_affixes)
    guard = {
        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_JumpIfNot, UAssetAPI",
        "CodeOffset": 0,  # assigned after delta is known
        "BooleanExpression": condition,
    }
    delta = expression_size(guard)
    guard["CodeOffset"] = old_false_target + delta

    report = insert_top_level_statements(fn, 0, [guard])
    validate_asset(patched)

    report.update({
        "asset": CDO_ASSET,
        "function": FUNCTION,
        "max_affixes": max_affixes,
        "old_false_target": old_false_target,
        "new_false_target": guard["CodeOffset"],
        "less_int_import": import_index(patched, "Less_IntInt"),
    })
    return patched, report


def verify(asset: dict[str, Any], max_affixes: int) -> dict[str, Any]:
    validate_asset(asset)
    fn_index, fn = find_function(asset, FUNCTION)
    code = fn.get("ScriptBytecode") or []
    if not code:
        raise PatchError("CanInteract has no bytecode")

    first = code[0]
    if "EX_JumpIfNot" not in str(first.get("$type", "")):
        raise PatchError("Foundry affix-count guard is not first statement")
    condition = first.get("BooleanExpression") or {}
    if "EX_CallMath" not in str(condition.get("$type", "")):
        raise PatchError("Foundry affix-count guard is not a math call")

    less_idx = import_index(asset, "Less_IntInt")
    if less_idx is None or condition.get("StackNode") != less_idx:
        raise PatchError("Foundry affix-count guard does not call Less_IntInt")

    params = condition.get("Parameters") or []
    if len(params) != 2 or params[1].get("Value") != max_affixes:
        raise PatchError("Foundry affix-count guard has unexpected max-affix value")

    # Fail closed if the nested path stops being PlayerCharacter.currentWeapon.AffixAmount.
    p0 = json.dumps(params[0], separators=(",", ":"))
    for token in ('"PlayerCharacter"', '"currentWeapon"', '"AffixAmount"'):
        if token not in p0:
            raise PatchError(f"Foundry guard missing path token {token}")

    return {
        "verified": True,
        "asset": CDO_ASSET,
        "function": FUNCTION,
        "max_affixes": max_affixes,
        "script_bytecode_size": fn.get("ScriptBytecodeSize"),
        "guard_size": expression_size(first),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("input_json", type=Path)
    ap.add_argument("output_json", type=Path, nargs="?")
    ap.add_argument("--max-affixes", type=int, default=6)
    ap.add_argument("--report", type=Path)
    ap.add_argument("--verify-only", action="store_true")
    args = ap.parse_args()

    asset = load(args.input_json)
    if args.verify_only:
        print(json.dumps(verify(asset, args.max_affixes), indent=2))
        return 0
    if args.output_json is None:
        raise SystemExit("output_json required unless --verify-only")

    patched, report = patch(asset, args.max_affixes)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(patched, indent=2) + "\n", encoding="utf-8")
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
