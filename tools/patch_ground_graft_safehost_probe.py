#!/usr/bin/env python3
"""Patch BP_Interactive_Weapon.GetInteractSound with a safe-host GRAFT mutation probe.

BP_APlayer is intentionally NOT modified. A real runtime test proved that a
UAssetAPI-reserialized BP_APlayer package crashes during BP_APlayer_C class
construction before any injected transaction bytecode can execute.

This diagnostic therefore uses BP_Interactive_Weapon, a package already proven
to survive cooked UAssetAPI round-trips in Roboquest:

- actual E interaction enters GetInteractSound(PlayerCharacter);
- donor SpawnedWeapon.GetAffixRowNames() supplies authoritative native row IDs;
- the first probe-approved donor row is selected deterministically;
- PlayerCharacter.AddEnchantedAffix(RowName) is invoked virtually;
- that existing BP_APlayer wrapper retains Roboquest's native server/multicast
  mutation chain;
- original GetInteractSound bytecode then runs unchanged, so normal weapon swap
  behavior remains intact.

The probe does NOT debit Power Cells or consume the donor. Its only purpose is
to prove cross-object replicated mutation while leaving BP_APlayer vanilla.
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
    top_level_offsets,
    validate_asset,
)


class PatchError(RuntimeError):
    pass


FUNCTION = "GetInteractSound"
LOCAL_DONOR_ROWS = "WF_DonorRows"
LOCAL_CONTAINS = "WF_Contains"
LOCAL_SELECTED_ROW = "WF_SelectedRow"
LOCAL_TARGET_WEAPON = "WF_TargetWeapon"
VIRTUAL_MUTATION = "OnServerAddEnchantedAffix"


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def type_name(expr: Any) -> str:
    if not isinstance(expr, dict):
        return type(expr).__name__
    return str(expr.get("$type", "")).split(",", 1)[0].rsplit(".", 1)[-1]


def ensure_name(asset: dict[str, Any], value: str) -> None:
    names = asset.get("NameMap")
    if not isinstance(names, list):
        raise PatchError("asset has no NameMap")
    if value not in names:
        names.append(value)
        asset["NamesReferencedFromExportDataCount"] = len(names)


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
    class_package: str = "/Script/CoreUObject",
    class_name: str = "Object",
) -> int:
    existing = import_index(asset, object_name)
    if existing is not None:
        return existing
    ensure_name(asset, object_name)
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


def pointer(owner: int, path: str | list[str]) -> dict[str, Any]:
    if isinstance(path, str):
        path = [path]
    return {
        "$type": "UAssetAPI.Kismet.Bytecode.KismetPropertyPointer, UAssetAPI",
        "New": {
            "$type": "UAssetAPI.UnrealTypes.FFieldPath, UAssetAPI",
            "Path": path,
            "ResolvedOwner": owner,
        },
    }


def local(owner: int, name: str) -> dict[str, Any]:
    return {
        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_LocalVariable, UAssetAPI",
        "Variable": pointer(owner, name),
    }


def instance(owner: int, name: str) -> dict[str, Any]:
    return {
        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_InstanceVariable, UAssetAPI",
        "Variable": pointer(owner, name),
    }


def object_const(index: int) -> dict[str, Any]:
    return {
        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_ObjectConst, UAssetAPI",
        "Value": index,
    }


def name_const(asset: dict[str, Any], value: str) -> dict[str, Any]:
    ensure_name(asset, value)
    return {
        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_NameConst, UAssetAPI",
        "Value": value,
    }


def final_call(stack_node: int, parameters: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_FinalFunction, UAssetAPI",
        "StackNode": stack_node,
        "Parameters": parameters,
    }


def virtual_call(name: str, parameters: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_VirtualFunction, UAssetAPI",
        "VirtualFunctionName": name,
        "Parameters": parameters,
    }


def context(
    obj: dict[str, Any],
    rvalue: dict[str, Any],
    expression: dict[str, Any],
) -> dict[str, Any]:
    return {
        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_Context, UAssetAPI",
        "ObjectExpression": obj,
        "Offset": expression_size(expression),
        "PropertyType": 0,
        "RValuePointer": rvalue,
        "ContextExpression": expression,
    }


def let(owner: int, name: str, expr: dict[str, Any]) -> dict[str, Any]:
    return {
        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_Let, UAssetAPI",
        "Value": pointer(owner, name),
        "Variable": local(owner, name),
        "Expression": expr,
    }


def let_bool(owner: int, name: str, expr: dict[str, Any]) -> dict[str, Any]:
    return {
        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_LetBool, UAssetAPI",
        "VariableExpression": local(owner, name),
        "AssignmentExpression": expr,
    }


def jump_if_not(condition: dict[str, Any]) -> dict[str, Any]:
    return {
        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_JumpIfNot, UAssetAPI",
        "CodeOffset": 0,
        "BooleanExpression": condition,
    }


def jump() -> dict[str, Any]:
    return {
        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_Jump, UAssetAPI",
        "CodeOffset": 0,
    }


def generic_property(name: str, serialized_type: str, element_size: int) -> dict[str, Any]:
    return {
        "$type": "UAssetAPI.FieldTypes.FGenericProperty, UAssetAPI",
        "ArrayDim": "TArray",
        "ElementSize": element_size,
        "PropertyFlags": "CPF_None",
        "RepIndex": 0,
        "RepNotifyFunc": "None",
        "BlueprintReplicationCondition": "COND_None",
        "RawValue": None,
        "SerializedType": serialized_type,
        "Name": name,
        "Flags": "RF_Public",
        "MetaDataMap": None,
    }


def bool_property(name: str) -> dict[str, Any]:
    return {
        "$type": "UAssetAPI.FieldTypes.FBoolProperty, UAssetAPI",
        "FieldSize": 1,
        "ByteOffset": 0,
        "ByteMask": 1,
        "FieldMask": 255,
        "NativeBool": True,
        "Value": True,
        "ArrayDim": "TArray",
        "ElementSize": 1,
        "PropertyFlags": "CPF_None",
        "RepIndex": 0,
        "RepNotifyFunc": "None",
        "BlueprintReplicationCondition": "COND_None",
        "RawValue": None,
        "SerializedType": "BoolProperty",
        "Name": name,
        "Flags": "RF_Public",
        "MetaDataMap": None,
    }


def object_property(name: str, property_class: int) -> dict[str, Any]:
    return {
        "$type": "UAssetAPI.FieldTypes.FObjectProperty, UAssetAPI",
        "PropertyClass": property_class,
        "ArrayDim": "TArray",
        "ElementSize": 8,
        "PropertyFlags": "CPF_None",
        "RepIndex": 0,
        "RepNotifyFunc": "None",
        "BlueprintReplicationCondition": "COND_None",
        "RawValue": None,
        "SerializedType": "ObjectProperty",
        "Name": name,
        "Flags": "RF_Public",
        "MetaDataMap": None,
    }


def name_array_property(name: str) -> dict[str, Any]:
    return {
        "$type": "UAssetAPI.FieldTypes.FArrayProperty, UAssetAPI",
        "Inner": generic_property(name, "NameProperty", 12),
        "ArrayDim": "TArray",
        "ElementSize": 16,
        "PropertyFlags": "CPF_ReferenceParm",
        "RepIndex": 0,
        "RepNotifyFunc": "None",
        "BlueprintReplicationCondition": "COND_None",
        "RawValue": None,
        "SerializedType": "ArrayProperty",
        "Name": name,
        "Flags": "RF_Public",
        "MetaDataMap": None,
    }


def add_locals(asset: dict[str, Any], fn: dict[str, Any], aweapon: int) -> None:
    loaded = fn.setdefault("LoadedProperties", [])
    definitions = [
        name_array_property(LOCAL_DONOR_ROWS),
        bool_property(LOCAL_CONTAINS),
        generic_property(LOCAL_SELECTED_ROW, "NameProperty", 12),
        object_property(LOCAL_TARGET_WEAPON, aweapon),
    ]
    existing = {p.get("Name") for p in loaded}
    overlap = existing & {p["Name"] for p in definitions}
    if overlap:
        raise PatchError(f"safe-host probe locals already exist: {sorted(overlap)}")
    for prop in definitions:
        ensure_name(asset, prop["Name"])
        loaded.append(prop)


def compile_block(
    asset: dict[str, Any],
    fn_index: int,
    fn: dict[str, Any],
    spec: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    ainteractive_weapon = require_import(asset, "AInteractiveWeapon")
    aweapon = require_import(asset, "AWeapon")
    character_player = require_import(asset, "Character_Player")
    engine_package = require_import(asset, "/Script/Engine")
    kismet_array = add_import(
        asset,
        "KismetArrayLibrary",
        outer_index=engine_package,
        class_package="/Script/CoreUObject",
        class_name="Class",
    )
    default_array = add_import(
        asset,
        "Default__KismetArrayLibrary",
        outer_index=engine_package,
        class_package="/Script/Engine",
        class_name="KismetArrayLibrary",
    )
    get_rows = add_import(asset, "GetAffixRowNames", outer_index=aweapon)
    array_contains = add_import(
        asset,
        "Array_Contains",
        outer_index=kismet_array,
    )

    add_locals(asset, fn, aweapon)
    for name in ("SpawnedWeapon", "PlayerCharacter", "currentWeapon", VIRTUAL_MUTATION):
        ensure_name(asset, name)

    candidates = list(spec.get("selection", {}).get("candidates") or [])
    if not candidates:
        raise PatchError("safe-host probe spec has no candidate rows")

    statements: list[dict[str, Any]] = []
    labels: dict[str, int] = {}
    targets: list[tuple[dict[str, Any], str]] = []

    def label(name: str) -> None:
        labels[name] = len(statements)

    def emit(expr: dict[str, Any], target: str | None = None) -> None:
        statements.append(expr)
        if target:
            targets.append((expr, target))

    # Capture the target weapon before the native E interaction swaps weapons.
    emit(let(
        fn_index,
        LOCAL_TARGET_WEAPON,
        context(
            local(fn_index, "PlayerCharacter"),
            pointer(fn_index, LOCAL_TARGET_WEAPON),
            instance(character_player, "currentWeapon"),
        ),
    ))

    # Reset donor row array, then read authoritative native donor rows.
    emit({
        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_SetArray, UAssetAPI",
        "AssigningProperty": local(fn_index, LOCAL_DONOR_ROWS),
        "ArrayInnerProp": None,
        "Elements": [],
    })
    getter_expr = final_call(get_rows, [])
    emit(let(
        fn_index,
        LOCAL_DONOR_ROWS,
        context(
            instance(ainteractive_weapon, "SpawnedWeapon"),
            pointer(fn_index, LOCAL_DONOR_ROWS),
            getter_expr,
        ),
    ))

    for i, candidate in enumerate(candidates):
        row = str(candidate["row"])
        next_label = f"candidate_{i + 1}" if i + 1 < len(candidates) else "fallthrough"
        contains_expr = final_call(
            array_contains,
            [
                local(fn_index, LOCAL_DONOR_ROWS),
                name_const(asset, row),
            ],
        )
        emit(let_bool(
            fn_index,
            LOCAL_CONTAINS,
            context(
                object_const(default_array),
                pointer(fn_index, LOCAL_CONTAINS),
                contains_expr,
            ),
        ))
        emit(jump_if_not(local(fn_index, LOCAL_CONTAINS)), next_label)
        emit(let(fn_index, LOCAL_SELECTED_ROW, name_const(asset, row)))
        emit(jump(), "mutate")
        if i + 1 < len(candidates):
            label(next_label)

    label("mutate")
    mutation = virtual_call(
        VIRTUAL_MUTATION,
        [
            local(fn_index, LOCAL_SELECTED_ROW),
            local(fn_index, LOCAL_TARGET_WEAPON),
        ],
    )
    emit(context(
        local(fn_index, "PlayerCharacter"),
        pointer(0, []),
        mutation,
    ))
    emit(jump(), "fallthrough")

    label("fallthrough")

    original_offsets, _ = top_level_offsets(fn["ScriptBytecode"])
    insertion_index = 0
    insertion_offset = original_offsets[insertion_index] if original_offsets else 0

    rel_offsets: list[int] = []
    cursor = 0
    for statement in statements:
        rel_offsets.append(cursor)
        cursor += expression_size(statement)
    block_size = cursor

    for statement, target_name in targets:
        if target_name not in labels:
            raise PatchError(f"unknown safe-host label {target_name}")
        target_index = labels[target_name]
        target_offset = insertion_offset + (
            rel_offsets[target_index] if target_index < len(rel_offsets) else block_size
        )
        statement["CodeOffset"] = target_offset

    return statements, {
        "function": FUNCTION,
        "insertion_index": insertion_index,
        "insertion_offset": insertion_offset,
        "block_size": block_size,
        "candidate_rows": [str(x["row"]) for x in candidates],
        "mutation": "PlayerCharacter.OnServerAddEnchantedAffix(RowName, captured currentWeapon)",
        "normal_interaction": "original GetInteractSound and weapon swap remain intact",
    }


def patch(asset: dict[str, Any], spec: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    patched = copy.deepcopy(asset)
    validate_asset(patched)
    fn_index, fn = find_function(patched)
    statements, report = compile_block(patched, fn_index, fn, spec)
    insertion = insert_top_level_statements(
        fn,
        report["insertion_index"],
        statements,
    )
    validate_asset(patched)
    return patched, {
        **report,
        **insertion,
        "asset": "BP_Interactive_Weapon",
        "diagnostic_only": True,
        "safe_host": True,
        "bp_aplayer_modified": False,
        "authoritative_donor_rows": "AAWeapon.GetAffixRowNames()",
    }


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


def verify(asset: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    validate_asset(asset)
    _, fn = find_function(asset)
    expected_rows = [str(x["row"]) for x in spec.get("selection", {}).get("candidates") or []]

    loaded = {p.get("Name"): p for p in fn.get("LoadedProperties") or []}
    for name in (LOCAL_DONOR_ROWS, LOCAL_CONTAINS, LOCAL_SELECTED_ROW, LOCAL_TARGET_WEAPON):
        if name not in loaded:
            raise PatchError(f"safe-host local missing: {name}")
    if (loaded[LOCAL_DONOR_ROWS].get("Inner") or {}).get("SerializedType") != "NameProperty":
        raise PatchError("safe-host donor rows are not TArray<FName>")

    calls: list[str] = []
    virtuals: list[str] = []
    constants: list[str] = []
    for expr in walk(fn.get("ScriptBytecode") or []):
        t = type_name(expr)
        if t in {"EX_FinalFunction", "EX_CallMath"}:
            name = object_name(asset, expr.get("StackNode"))
            if name:
                calls.append(name)
        elif t in {"EX_VirtualFunction", "EX_LocalVirtualFunction"}:
            value = expr.get("VirtualFunctionName")
            if value:
                virtuals.append(str(value))
        elif t == "EX_NameConst":
            value = expr.get("Value")
            if isinstance(value, str):
                constants.append(value)

    for required in ("GetAffixRowNames", "Array_Contains"):
        if required not in calls:
            raise PatchError(f"safe-host call missing: {required}")
    if VIRTUAL_MUTATION not in virtuals:
        raise PatchError("safe-host probe does not call OnServerAddEnchantedAffix")
    for row in expected_rows:
        if row not in constants:
            raise PatchError(f"safe-host candidate missing: {row}")

    # Serialization contract: every reflected FFieldPath segment must be in NameMap.
    names = set(asset.get("NameMap") or [])
    paths: set[str] = set()
    for expr in walk(fn.get("ScriptBytecode") or []):
        if str(expr.get("$type", "")).endswith("FFieldPath, UAssetAPI"):
            for segment in expr.get("Path") or []:
                if isinstance(segment, str):
                    paths.add(segment)
    missing_paths = paths - names
    if missing_paths:
        raise PatchError(f"unregistered safe-host FFieldPath names: {sorted(missing_paths)}")

    return {
        "verified": True,
        "asset": "BP_Interactive_Weapon",
        "function": FUNCTION,
        "safe_host": True,
        "bp_aplayer_modified": False,
        "candidate_count": len(expected_rows),
        "candidate_rows": expected_rows,
        "authoritative_donor_rows": "AAWeapon.GetAffixRowNames()",
        "mutation": "PlayerCharacter.AddEnchantedAffix(RowName)",
        "script_bytecode_size": fn.get("ScriptBytecodeSize"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input_json", type=Path)
    ap.add_argument("spec_json", type=Path)
    ap.add_argument("output_json", type=Path, nargs="?")
    ap.add_argument("--report", type=Path)
    ap.add_argument("--verify-only", action="store_true")
    args = ap.parse_args()

    asset = load(args.input_json)
    spec = load(args.spec_json)

    if args.verify_only:
        print(json.dumps(verify(asset, spec), indent=2))
        return 0
    if args.output_json is None:
        raise SystemExit("output_json required unless --verify-only")

    patched, report = patch(asset, spec)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(patched, indent=2) + "\n", encoding="utf-8")
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
