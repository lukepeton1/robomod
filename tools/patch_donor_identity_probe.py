#!/usr/bin/env python3
"""Instrument BP_Interactive_Weapon with a narrow AWeaponAffix actor-enumeration probe.

This diagnostic answers one question needed by ground-donor GRAFT:

    Can Roboquest's live AWeaponAffix instances be enumerated through
    GameplayStatics.GetAllActorsOfClass(AWeaponAffix)?

When GetInteractSound executes for a dropped weapon, the patched function:
- gathers all live AWeaponAffix actors;
- prints a short diagnostic label;
- prints the resulting actor count;
- then continues through the original GetInteractSound bytecode unchanged.

This is diagnostic-only. It does not mutate weapon state or consume the donor.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

from kismet_layout import insert_top_level_statements, validate_asset


class PatchError(RuntimeError):
    pass


FUNCTION = "GetInteractSound"
LOCAL_ACTORS = "WF_AffixActors"
LOCAL_COUNT = "WF_AffixActorCount"
LOCAL_COUNT_TEXT = "WF_AffixActorCountText"
LABEL = "Weapon Foundry AWeaponAffix count:"


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


def find_function(asset: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    matches = [
        (i + 1, export)
        for i, export in enumerate(asset.get("Exports", []))
        if "FunctionExport" in str(export.get("$type", ""))
        and export.get("ObjectName") == FUNCTION
    ]
    if len(matches) != 1:
        raise PatchError(f"expected one {FUNCTION}, found {len(matches)}")
    owner, fn = matches[0]
    if not isinstance(fn.get("ScriptBytecode"), list) or fn.get("ScriptBytecodeRaw"):
        raise PatchError(f"{FUNCTION} bytecode is not fully decoded")
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


def add_probe_locals(
    fn: dict[str, Any],
    *,
    affix_class_index: int,
) -> None:
    loaded = fn.setdefault("LoadedProperties", [])
    existing = {prop.get("Name") for prop in loaded}
    required = {LOCAL_ACTORS, LOCAL_COUNT, LOCAL_COUNT_TEXT}
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
        {
            "$type": "UAssetAPI.FieldTypes.FGenericProperty, UAssetAPI",
            "ArrayDim": "TArray",
            "ElementSize": 16,
            "PropertyFlags": "CPF_None",
            "RepIndex": 0,
            "RepNotifyFunc": "None",
            "BlueprintReplicationCondition": "COND_None",
            "RawValue": None,
            "SerializedType": "StrProperty",
            "Name": LOCAL_COUNT_TEXT,
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


def linear_color(struct_index: int) -> dict[str, Any]:
    return {
        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_StructConst, UAssetAPI",
        "Struct": struct_index,
        "StructSize": 16,
        "Value": [
            {
                "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_FloatConst, UAssetAPI",
                "Value": 0.0,
            },
            {
                "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_FloatConst, UAssetAPI",
                "Value": 0.66,
            },
            {
                "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_FloatConst, UAssetAPI",
                "Value": 1.0,
            },
            {
                "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_FloatConst, UAssetAPI",
                "Value": 1.0,
            },
        ],
    }


def print_statement(
    *,
    print_index: int,
    linear_color_index: int,
    message: str | dict[str, Any],
) -> dict[str, Any]:
    text_expr = (
        {
            "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_StringConst, UAssetAPI",
            "Value": message,
        }
        if isinstance(message, str)
        else message
    )
    return {
        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_CallMath, UAssetAPI",
        "StackNode": print_index,
        "Parameters": [
            {"$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_Self, UAssetAPI"},
            text_expr,
            {"$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_True, UAssetAPI"},
            {"$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_True, UAssetAPI"},
            linear_color(linear_color_index),
            {
                "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_FloatConst, UAssetAPI",
                "Value": 4.0,
            },
        ],
    }


def patch(asset: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    patched = copy.deepcopy(asset)
    validate_asset(patched)

    owner, fn = find_function(patched)

    engine_package = require_import(patched, "/Script/Engine")
    roboquest_package = require_import(patched, "/Script/RoboQuest")
    core_package = require_import(patched, "/Script/CoreUObject")
    gameplay_statics = require_import(patched, "GameplayStatics")
    kismet_system = require_import(patched, "KismetSystemLibrary")

    kismet_array = add_import(
        patched,
        "KismetArrayLibrary",
        outer_index=engine_package,
        class_package="/Script/CoreUObject",
        class_name="Class",
    )
    kismet_string = add_import(
        patched,
        "KismetStringLibrary",
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
    linear_color_index = add_import(
        patched,
        "LinearColor",
        outer_index=core_package,
        class_package="/Script/CoreUObject",
        class_name="Object",
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
    int_to_string = add_import(
        patched,
        "Conv_IntToString",
        outer_index=kismet_string,
        class_package="/Script/CoreUObject",
        class_name="Object",
    )
    print_string = add_import(
        patched,
        "PrintString",
        outer_index=kismet_system,
        class_package="/Script/CoreUObject",
        class_name="Object",
    )

    name_map_added = ensure_names(
        patched,
        [LOCAL_ACTORS, LOCAL_COUNT, LOCAL_COUNT_TEXT],
    )
    add_probe_locals(fn, affix_class_index=affix_class)

    statements = [
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
            "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_Let, UAssetAPI",
            "Value": property_pointer(owner, LOCAL_COUNT_TEXT),
            "Variable": local_variable(owner, LOCAL_COUNT_TEXT),
            "Expression": {
                "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_CallMath, UAssetAPI",
                "StackNode": int_to_string,
                "Parameters": [local_variable(owner, LOCAL_COUNT)],
            },
        },
        print_statement(
            print_index=print_string,
            linear_color_index=linear_color_index,
            message=LABEL,
        ),
        print_statement(
            print_index=print_string,
            linear_color_index=linear_color_index,
            message=local_variable(owner, LOCAL_COUNT_TEXT),
        ),
    ]

    insertion = insert_top_level_statements(fn, 0, statements)
    validate_asset(patched)

    report = {
        "asset": "BP_Interactive_Weapon",
        "function": FUNCTION,
        "diagnostic_only": True,
        "probe": "global live AWeaponAffix actor enumeration",
        "label": LABEL,
        "name_map_added": name_map_added,
        "imports": {
            "AWeaponAffix": affix_class,
            "GetAllActorsOfClass": get_all,
            "Array_Length": array_length,
            "Conv_IntToString": int_to_string,
            "PrintString": print_string,
        },
        **insertion,
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
    owner, fn = find_function(asset)

    loaded = {prop.get("Name"): prop for prop in fn.get("LoadedProperties") or []}
    for name in (LOCAL_ACTORS, LOCAL_COUNT, LOCAL_COUNT_TEXT):
        if name not in loaded:
            raise PatchError(f"probe local missing: {name}")

    calls: list[str] = []
    affix_class_argument = False
    label_present = False
    count_text_used = False

    for expr in fn.get("ScriptBytecode") or []:
        if str(expr.get("$type", "")).endswith("EX_CallMath, UAssetAPI"):
            call = object_name(asset, expr.get("StackNode"))
            if call:
                calls.append(call)
            if call == "GetAllActorsOfClass":
                params = expr.get("Parameters") or []
                if len(params) >= 2 and params[1].get("Value"):
                    affix_class_argument = (
                        object_name(asset, params[1]["Value"]) == "AWeaponAffix"
                    )
            if call == "PrintString":
                params = expr.get("Parameters") or []
                if len(params) >= 2:
                    text = params[1]
                    if text.get("Value") == LABEL:
                        label_present = True
                    ptr = (text.get("Variable") or {}).get("New") or {}
                    if ptr.get("Path") == [LOCAL_COUNT_TEXT]:
                        count_text_used = True

    required_calls = {
        "GetAllActorsOfClass",
        "Array_Length",
        "Conv_IntToString",
        "PrintString",
    }
    missing = required_calls - set(calls)
    if missing:
        raise PatchError(f"probe calls missing: {sorted(missing)}")
    if not affix_class_argument:
        raise PatchError("GetAllActorsOfClass is not targeting AWeaponAffix")
    if not label_present or not count_text_used:
        raise PatchError("diagnostic PrintString statements are incomplete")

    return {
        "verified": True,
        "asset": "BP_Interactive_Weapon",
        "function": FUNCTION,
        "script_bytecode_size": fn.get("ScriptBytecodeSize"),
        "probe_locals": [LOCAL_ACTORS, LOCAL_COUNT, LOCAL_COUNT_TEXT],
        "required_calls": sorted(required_calls),
        "target_class": "AWeaponAffix",
        "label": LABEL,
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
