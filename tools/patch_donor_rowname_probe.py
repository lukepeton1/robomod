#!/usr/bin/env python3
"""Probe native AAWeapon.GetAffixRowNames() through BP_Interactive_Weapon.

Why this exists
---------------
The first donor probe proved that AWeaponAffix is *not* enumerable through the
world actor registry: GetAllActorsOfClass(AWeaponAffix) returned zero in a real
run with an affixed dropped weapon present.

Shipping-binary reflection metadata then exposed a much stronger native seam:

- AAWeapon has reflected fields named Affixes / TmpAffixPool / RandomAffixes;
- AAWeapon exposes reflected native functions GetAffixRow and GetAffixRowNames;
- GetAffixRowNames appears in the same callable-function block as
  GetCurrentEnchantedAffixRowName and GetDataRowName.

This diagnostic calls GetAffixRowNames() directly on the dropped weapon's
SpawnedWeapon object and displays whether the returned FName array is non-empty
through Roboquest's ordinary interaction-error UI.

The probe is read-only. It temporarily returns false from CanInteract so the
error text is visible after the normal interaction key is pressed.
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


ERROR_FUNCTION = "GetErrorText"
CAN_INTERACT_FUNCTION = "CanInteract"
LOCAL_ROWS = "WF_AffixRowNames"
LOCAL_COUNT = "WF_AffixRowCount"
POSITIVE_TEXT = "WF ROW PROBE: GetAffixRowNames returned rows"
ZERO_TEXT = "WF ROW PROBE: GetAffixRowNames returned 0 rows"


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def ensure_names(asset: dict[str, Any], names: list[str]) -> list[str]:
    name_map = asset.get("NameMap")
    if not isinstance(name_map, list):
        raise PatchError("asset has no NameMap")
    existing = set(map(str, name_map))
    added: list[str] = []
    for name in names:
        if name not in existing:
            name_map.append(name)
            existing.add(name)
            added.append(name)
    if added:
        asset["NamesReferencedFromExportDataCount"] = len(name_map)
    return added


def import_index(asset: dict[str, Any], object_name: str) -> int | None:
    matches = [
        -i
        for i, entry in enumerate(asset.get("Imports", []), start=1)
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


def add_import(
    asset: dict[str, Any],
    object_name: str,
    *,
    outer_index: int,
    class_package: str,
    class_name: str,
) -> int:
    existing = import_index(asset, object_name)
    if existing is not None:
        return existing
    ensure_names(asset, [object_name])
    asset.setdefault("Imports", []).append({
        "$type": "UAssetAPI.Import, UAssetAPI",
        "ObjectName": object_name,
        "OuterIndex": outer_index,
        "ClassPackage": class_package,
        "ClassName": class_name,
        "PackageName": None,
        "bImportOptional": False,
    })
    return -len(asset["Imports"])


def find_function(asset: dict[str, Any], name: str) -> tuple[int, dict[str, Any]]:
    matches = [
        (i + 1, export)
        for i, export in enumerate(asset.get("Exports", []))
        if "FunctionExport" in str(export.get("$type", ""))
        and export.get("ObjectName") == name
    ]
    if len(matches) != 1:
        raise PatchError(f"expected one {name}, found {len(matches)}")
    owner, fn = matches[0]
    if not isinstance(fn.get("ScriptBytecode"), list) or fn.get("ScriptBytecodeRaw"):
        raise PatchError(f"{name} bytecode is not fully decoded")
    return owner, fn


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


def local_out_variable(owner: int, path: str) -> dict[str, Any]:
    return {
        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_LocalOutVariable, UAssetAPI",
        "Variable": property_pointer(owner, path),
    }


def instance_variable(owner: int, path: str) -> dict[str, Any]:
    return {
        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_InstanceVariable, UAssetAPI",
        "Variable": property_pointer(owner, path),
    }


def add_probe_locals(fn: dict[str, Any]) -> None:
    loaded = fn.setdefault("LoadedProperties", [])
    existing = {prop.get("Name") for prop in loaded}
    required = {LOCAL_ROWS, LOCAL_COUNT}
    overlap = required & existing
    if overlap:
        raise PatchError(f"probe locals already exist: {sorted(overlap)}")

    loaded.extend([
        {
            "$type": "UAssetAPI.FieldTypes.FArrayProperty, UAssetAPI",
            "Inner": {
                "$type": "UAssetAPI.FieldTypes.FGenericProperty, UAssetAPI",
                "ArrayDim": "TArray",
                "ElementSize": 12,
                "PropertyFlags": "CPF_None",
                "RepIndex": 0,
                "RepNotifyFunc": "None",
                "BlueprintReplicationCondition": "COND_None",
                "RawValue": None,
                "SerializedType": "NameProperty",
                "Name": LOCAL_ROWS,
                "Flags": "RF_Public",
                "MetaDataMap": None,
            },
            "ArrayDim": "TArray",
            "ElementSize": 16,
            "PropertyFlags": "CPF_ReferenceParm",
            "RepIndex": 0,
            "RepNotifyFunc": "None",
            "BlueprintReplicationCondition": "COND_None",
            "RawValue": None,
            "SerializedType": "ArrayProperty",
            "Name": LOCAL_ROWS,
            "Flags": "RF_Public",
            "MetaDataMap": None,
        },
        {
            "$type": "UAssetAPI.FieldTypes.FGenericProperty, UAssetAPI",
            "ArrayDim": "TArray",
            "ElementSize": 4,
            "PropertyFlags": "CPF_None",
            "RepIndex": 0,
            "RepNotifyFunc": "None",
            "BlueprintReplicationCondition": "COND_None",
            "RawValue": None,
            "SerializedType": "IntProperty",
            "Name": LOCAL_COUNT,
            "Flags": "RF_Public",
            "MetaDataMap": None,
        },
    ])


def set_array(owner: int) -> dict[str, Any]:
    return {
        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_SetArray, UAssetAPI",
        "AssigningProperty": local_variable(owner, LOCAL_ROWS),
        "ArrayInnerProp": None,
        "Elements": [],
    }


def make_text(value: str, key: str) -> dict[str, Any]:
    return {
        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_TextConst, UAssetAPI",
        "Value": {
            "$type": "UAssetAPI.Kismet.Bytecode.FScriptText, UAssetAPI",
            "TextLiteralType": "LocalizedText",
            "LocalizedSource": {
                "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_StringConst, UAssetAPI",
                "Value": value,
            },
            "LocalizedKey": {
                "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_StringConst, UAssetAPI",
                "Value": key,
            },
            "LocalizedNamespace": {
                "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_StringConst, UAssetAPI",
                "Value": "WeaponFoundryProbe",
            },
            "InvariantLiteralString": None,
            "LiteralString": None,
            "StringTableAsset": None,
            "StringTableId": None,
            "StringTableKey": None,
        },
    }


def assign_text_return(owner: int, value: str, key: str) -> dict[str, Any]:
    return {
        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_Let, UAssetAPI",
        "Value": property_pointer(owner, "ReturnValue"),
        "Variable": local_out_variable(owner, "ReturnValue"),
        "Expression": make_text(value, key),
    }


def return_out(owner: int) -> dict[str, Any]:
    return {
        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_Return, UAssetAPI",
        "ReturnExpression": local_out_variable(owner, "ReturnValue"),
    }


def patch_error_text(
    asset: dict[str, Any],
    *,
    interactive_weapon_class: int,
    get_affix_row_names: int,
    default_array: int,
    array_length: int,
    greater_int: int,
) -> dict[str, Any]:
    owner, fn = find_function(asset, ERROR_FUNCTION)
    add_probe_locals(fn)

    statements: list[dict[str, Any]] = [
        set_array(owner),
        {
            "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_Let, UAssetAPI",
            "Value": property_pointer(owner, LOCAL_ROWS),
            "Variable": local_variable(owner, LOCAL_ROWS),
            "Expression": {
                "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_Context, UAssetAPI",
                "ObjectExpression": instance_variable(
                    interactive_weapon_class,
                    "SpawnedWeapon",
                ),
                # Matches compiled UE4.26 Blueprint calls returning an array,
                # e.g. GetGameplayTagList() in the collected affix bytecode.
                "Offset": 10,
                "PropertyType": 0,
                "RValuePointer": property_pointer(owner, LOCAL_ROWS),
                "ContextExpression": {
                    "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_FinalFunction, UAssetAPI",
                    "StackNode": get_affix_row_names,
                    "Parameters": [],
                },
            },
        },
        {
            "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_Let, UAssetAPI",
            "Value": property_pointer(owner, LOCAL_COUNT),
            "Variable": local_variable(owner, LOCAL_COUNT),
            "Expression": {
                "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_Context, UAssetAPI",
                "ObjectExpression": {
                    "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_ObjectConst, UAssetAPI",
                    "Value": default_array,
                },
                "Offset": 19,
                "PropertyType": 0,
                "RValuePointer": property_pointer(owner, LOCAL_COUNT),
                "ContextExpression": {
                    "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_FinalFunction, UAssetAPI",
                    "StackNode": array_length,
                    "Parameters": [local_variable(owner, LOCAL_ROWS)],
                },
            },
        },
        {
            "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_JumpIfNot, UAssetAPI",
            "CodeOffset": 0,
            "BooleanExpression": {
                "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_CallMath, UAssetAPI",
                "StackNode": greater_int,
                "Parameters": [
                    local_variable(owner, LOCAL_COUNT),
                    {
                        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_IntConst, UAssetAPI",
                        "Value": 0,
                    },
                ],
            },
        },
        assign_text_return(
            owner,
            POSITIVE_TEXT,
            "WeaponFoundryAffixRowNamesFound",
        ),
        return_out(owner),
        assign_text_return(
            owner,
            ZERO_TEXT,
            "WeaponFoundryAffixRowNamesZero",
        ),
        return_out(owner),
    ]

    # EX_JumpIfNot should land on the zero-result assignment.
    statements[3]["CodeOffset"] = sum(expression_size(x) for x in statements[:6])

    report = insert_top_level_statements(fn, 0, statements)
    report["function"] = ERROR_FUNCTION
    return report


def patch_can_interact(asset: dict[str, Any]) -> dict[str, Any]:
    owner, fn = find_function(asset, CAN_INTERACT_FUNCTION)
    statements = [
        {
            "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_LetBool, UAssetAPI",
            "VariableExpression": local_out_variable(owner, "ReturnValue"),
            "AssignmentExpression": {
                "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_False, UAssetAPI",
            },
        },
        return_out(owner),
    ]
    report = insert_top_level_statements(fn, 0, statements)
    report["function"] = CAN_INTERACT_FUNCTION
    return report


def patch(asset: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    patched = copy.deepcopy(asset)
    validate_asset(patched)

    engine_package = require_import(patched, "/Script/Engine")
    interactive_weapon_class = require_import(patched, "AInteractiveWeapon")
    weapon_class = require_import(patched, "AWeapon")
    kismet_math = require_import(patched, "KismetMathLibrary")

    kismet_array = add_import(
        patched,
        "KismetArrayLibrary",
        outer_index=engine_package,
        class_package="/Script/CoreUObject",
        class_name="Class",
    )
    default_array = add_import(
        patched,
        "Default__KismetArrayLibrary",
        outer_index=engine_package,
        class_package="/Script/Engine",
        class_name="KismetArrayLibrary",
    )
    get_affix_row_names = add_import(
        patched,
        "GetAffixRowNames",
        outer_index=weapon_class,
        class_package="/Script/CoreUObject",
        class_name="Object",
    )
    array_length = add_import(
        patched,
        "Array_Length",
        outer_index=kismet_array,
        class_package="/Script/CoreUObject",
        class_name="Object",
    )
    greater_int = add_import(
        patched,
        "Greater_IntInt",
        outer_index=kismet_math,
        class_package="/Script/CoreUObject",
        class_name="Object",
    )

    name_map_added = ensure_names(patched, [LOCAL_ROWS, LOCAL_COUNT])
    error_report = patch_error_text(
        patched,
        interactive_weapon_class=interactive_weapon_class,
        get_affix_row_names=get_affix_row_names,
        default_array=default_array,
        array_length=array_length,
        greater_int=greater_int,
    )
    interact_report = patch_can_interact(patched)

    validate_asset(patched)
    report = {
        "asset": "BP_Interactive_Weapon",
        "diagnostic_only": True,
        "probe": "native AAWeapon.GetAffixRowNames()",
        "presentation": "normal interaction error text",
        "positive_text": POSITIVE_TEXT,
        "zero_text": ZERO_TEXT,
        "interaction_temporarily_disabled": True,
        "name_map_added": name_map_added,
        "imports": {
            "AInteractiveWeapon": interactive_weapon_class,
            "AWeapon": weapon_class,
            "GetAffixRowNames": get_affix_row_names,
            "Array_Length": array_length,
            "Greater_IntInt": greater_int,
        },
        "functions": [error_report, interact_report],
    }
    return patched, report


def object_name(asset: dict[str, Any], index: int) -> str | None:
    if not isinstance(index, int) or index == 0:
        return None
    seq = asset.get("Exports", []) if index > 0 else asset.get("Imports", [])
    slot = index - 1 if index > 0 else -index - 1
    if 0 <= slot < len(seq):
        return str(seq[slot].get("ObjectName"))
    return None


def walk(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def verify(asset: dict[str, Any]) -> dict[str, Any]:
    validate_asset(asset)
    _, error_fn = find_function(asset, ERROR_FUNCTION)
    _, interact_fn = find_function(asset, CAN_INTERACT_FUNCTION)

    loaded = {prop.get("Name"): prop for prop in error_fn.get("LoadedProperties") or []}
    for name in (LOCAL_ROWS, LOCAL_COUNT):
        if name not in loaded:
            raise PatchError(f"probe local missing: {name}")

    rows = loaded[LOCAL_ROWS]
    if rows.get("SerializedType") != "ArrayProperty":
        raise PatchError("row-name probe local is not an array")
    if (rows.get("Inner") or {}).get("SerializedType") != "NameProperty":
        raise PatchError("row-name probe array does not contain NameProperty values")

    calls: list[str] = []
    text_values: set[str] = set()
    spawned_weapon_context = False

    for expr in walk(error_fn.get("ScriptBytecode") or []):
        expr_type = str(expr.get("$type", "")).split(",", 1)[0].rsplit(".", 1)[-1]
        if expr_type in {"EX_CallMath", "EX_FinalFunction"}:
            call = object_name(asset, expr.get("StackNode"))
            if call:
                calls.append(call)
        if expr_type == "EX_InstanceVariable":
            ptr = (expr.get("Variable") or {}).get("New") or {}
            if ptr.get("Path") == ["SpawnedWeapon"]:
                spawned_weapon_context = True
        if expr_type == "EX_StringConst":
            value = expr.get("Value")
            if isinstance(value, str):
                text_values.add(value)

    required_calls = {"GetAffixRowNames", "Array_Length", "Greater_IntInt"}
    missing = required_calls - set(calls)
    if missing:
        raise PatchError(f"probe calls missing: {sorted(missing)}")
    if not spawned_weapon_context:
        raise PatchError("GetAffixRowNames probe is not rooted in SpawnedWeapon")
    if POSITIVE_TEXT not in text_values or ZERO_TEXT not in text_values:
        raise PatchError("visible probe status text is incomplete")

    code = interact_fn.get("ScriptBytecode") or []
    if len(code) < 2:
        raise PatchError("CanInteract probe is incomplete")
    first_type = str(code[0].get("$type", "")).split(",", 1)[0].rsplit(".", 1)[-1]
    second_type = str(code[1].get("$type", "")).split(",", 1)[0].rsplit(".", 1)[-1]
    if first_type != "EX_LetBool" or second_type != "EX_Return":
        raise PatchError("CanInteract is not short-circuited by the row-name probe")
    assignment = code[0].get("AssignmentExpression") or {}
    if not str(assignment.get("$type", "")).endswith("EX_False, UAssetAPI"):
        raise PatchError("CanInteract probe does not return false")

    return {
        "verified": True,
        "asset": "BP_Interactive_Weapon",
        "functions": [ERROR_FUNCTION, CAN_INTERACT_FUNCTION],
        "required_calls": sorted(required_calls),
        "native_getter": "AAWeapon.GetAffixRowNames",
        "target_object": "SpawnedWeapon",
        "row_array_type": "TArray<FName>",
        "positive_text": POSITIVE_TEXT,
        "zero_text": ZERO_TEXT,
        "interaction_temporarily_disabled": True,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input_json", type=Path)
    ap.add_argument("output_json", type=Path, nargs="?")
    ap.add_argument("--report", type=Path)
    ap.add_argument("--verify-only", action="store_true")
    args = ap.parse_args()

    asset = load(args.input_json)
    if args.verify_only:
        print(json.dumps(verify(asset), indent=2))
        return 0

    if args.output_json is None:
        raise SystemExit("output_json required unless --verify-only")

    patched, report = patch(asset)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(patched, indent=2) + "\n", encoding="utf-8")
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
