#!/usr/bin/env python3
"""Instrument BP_Interactive_Weapon with a visible AWeaponAffix enumeration probe.

The previous diagnostic used KismetSystemLibrary.PrintString from GetInteractSound.
Roboquest retail builds may suppress on-screen/log debug output, so this version
uses the game's normal interaction error-text surface instead.

Probe behavior:
- CanInteract is temporarily forced false for dropped weapons;
- GetErrorText enumerates live AWeaponAffix actors;
- the normal interaction UI displays one of:
    WF PROBE: AWeaponAffix actors found
    WF PROBE: AWeaponAffix count = 0

This answers the only question needed at this stage: whether live AWeaponAffix
actors are enumerable at all. It does not mutate weapon state or consume a donor.
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
LOCAL_ACTORS = "WF_AffixActors"
LOCAL_COUNT = "WF_AffixActorCount"
POSITIVE_TEXT = "WF PROBE: AWeaponAffix actors found"
ZERO_TEXT = "WF PROBE: AWeaponAffix count = 0"


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


def add_probe_locals(
    fn: dict[str, Any],
    *,
    affix_class_index: int,
) -> None:
    loaded = fn.setdefault("LoadedProperties", [])
    existing = {prop.get("Name") for prop in loaded}
    required = {LOCAL_ACTORS, LOCAL_COUNT}
    overlap = required & existing
    if overlap:
        raise PatchError(f"probe locals already exist: {sorted(overlap)}")

    loaded.extend([
        {
            "$type": "UAssetAPI.FieldTypes.FArrayProperty, UAssetAPI",
            "Inner": {
                "$type": "UAssetAPI.FieldTypes.FObjectProperty, UAssetAPI",
                "PropertyClass": affix_class_index,
                "ArrayDim": "TArray",
                "ElementSize": 8,
                "PropertyFlags": "CPF_None",
                "RepIndex": 0,
                "RepNotifyFunc": "None",
                "BlueprintReplicationCondition": "COND_None",
                "RawValue": None,
                "SerializedType": "ObjectProperty",
                "Name": LOCAL_ACTORS,
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
            "Name": LOCAL_ACTORS,
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
        "AssigningProperty": local_variable(owner, LOCAL_ACTORS),
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
    affix_class: int,
    get_all: int,
    default_array: int,
    array_length: int,
    greater_int: int,
) -> dict[str, Any]:
    owner, fn = find_function(asset, ERROR_FUNCTION)
    add_probe_locals(fn, affix_class_index=affix_class)

    statements: list[dict[str, Any]] = [
        set_array(owner),
        {
            "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_CallMath, UAssetAPI",
            "StackNode": get_all,
            "Parameters": [
                {"$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_Self, UAssetAPI"},
                {
                    "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_ObjectConst, UAssetAPI",
                    "Value": affix_class,
                },
                local_variable(owner, LOCAL_ACTORS),
            ],
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
                    "Parameters": [local_variable(owner, LOCAL_ACTORS)],
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
            "WeaponFoundryAffixActorsFound",
        ),
        return_out(owner),
        assign_text_return(
            owner,
            ZERO_TEXT,
            "WeaponFoundryAffixActorsZero",
        ),
        return_out(owner),
    ]

    # EX_JumpIfNot targets the first zero-result statement. Since insertion is
    # at byte offset zero, this is simply the size of all prior probe statements.
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
    roboquest_package = require_import(patched, "/Script/RoboQuest")
    gameplay_statics = require_import(patched, "GameplayStatics")
    kismet_math = require_import(patched, "KismetMathLibrary")

    kismet_array = add_import(
        patched,
        "KismetArrayLibrary",
        outer_index=engine_package,
        class_package="/Script/CoreUObject",
        class_name="Class",
    )
    affix_class = add_import(
        patched,
        "AWeaponAffix",
        outer_index=roboquest_package,
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
    get_all = add_import(
        patched,
        "GetAllActorsOfClass",
        outer_index=gameplay_statics,
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

    name_map_added = ensure_names(patched, [LOCAL_ACTORS, LOCAL_COUNT])
    error_report = patch_error_text(
        patched,
        affix_class=affix_class,
        get_all=get_all,
        default_array=default_array,
        array_length=array_length,
        greater_int=greater_int,
    )
    interact_report = patch_can_interact(patched)

    validate_asset(patched)
    report = {
        "asset": "BP_Interactive_Weapon",
        "diagnostic_only": True,
        "probe": "visible live AWeaponAffix actor enumeration",
        "presentation": "normal interaction error text",
        "positive_text": POSITIVE_TEXT,
        "zero_text": ZERO_TEXT,
        "interaction_temporarily_disabled": True,
        "name_map_added": name_map_added,
        "imports": {
            "AWeaponAffix": affix_class,
            "GetAllActorsOfClass": get_all,
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
    for name in (LOCAL_ACTORS, LOCAL_COUNT):
        if name not in loaded:
            raise PatchError(f"probe local missing: {name}")

    calls: list[str] = []
    affix_class_argument = False
    text_values: set[str] = set()
    for expr in walk(error_fn.get("ScriptBytecode") or []):
        expr_type = str(expr.get("$type", "")).split(",", 1)[0].rsplit(".", 1)[-1]
        if expr_type in {"EX_CallMath", "EX_FinalFunction"}:
            call = object_name(asset, expr.get("StackNode"))
            if call:
                calls.append(call)
            if call == "GetAllActorsOfClass":
                params = expr.get("Parameters") or []
                if len(params) >= 2 and isinstance(params[1].get("Value"), int):
                    affix_class_argument = (
                        object_name(asset, params[1]["Value"]) == "AWeaponAffix"
                    )
        if expr_type == "EX_StringConst":
            value = expr.get("Value")
            if isinstance(value, str):
                text_values.add(value)

    required_calls = {"GetAllActorsOfClass", "Array_Length", "Greater_IntInt"}
    missing = required_calls - set(calls)
    if missing:
        raise PatchError(f"probe calls missing: {sorted(missing)}")
    if not affix_class_argument:
        raise PatchError("GetAllActorsOfClass is not targeting AWeaponAffix")
    if POSITIVE_TEXT not in text_values or ZERO_TEXT not in text_values:
        raise PatchError("visible probe status text is incomplete")

    code = interact_fn.get("ScriptBytecode") or []
    if len(code) < 2:
        raise PatchError("CanInteract probe is incomplete")
    first_type = str(code[0].get("$type", "")).split(",", 1)[0].rsplit(".", 1)[-1]
    second_type = str(code[1].get("$type", "")).split(",", 1)[0].rsplit(".", 1)[-1]
    if first_type != "EX_LetBool" or second_type != "EX_Return":
        raise PatchError("CanInteract is not short-circuited by the visible probe")
    assignment = code[0].get("AssignmentExpression") or {}
    if not str(assignment.get("$type", "")).endswith("EX_False, UAssetAPI"):
        raise PatchError("CanInteract probe does not return false")

    return {
        "verified": True,
        "asset": "BP_Interactive_Weapon",
        "functions": [ERROR_FUNCTION, CAN_INTERACT_FUNCTION],
        "required_calls": sorted(required_calls),
        "target_class": "AWeaponAffix",
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
