#!/usr/bin/env python3
"""Read-only, visible GRAFT eligibility gate for BP_Interactive_Weapon.

The earlier GetInteractSound mutation probes did not report whether their
11-row donor filter matched, whether the target was present, or whether the
target already held the row. Normal E swapping without mutation cannot tell
us which one of those gates failed, or whether GetInteractSound ran at all.

This probe uses the already runtime-confirmed diagnostic surface:
- BP_Interactive_Weapon.CanInteract temporarily returns false;
- BP_Interactive_Weapon.GetErrorText runs when the player tries E;
- the resulting native interaction-error text reports the first supported
  row, duplicate status, or an explicit failure stage.

This probe never calls AddEnchantedAffix, never sends network RPCs, never
charges Power Cells, and never consumes a donor. Restore the normal production
build after recording the status.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

from kismet_layout import expression_size, insert_top_level_statements, validate_asset
from patch_donor_rowname_probe import (
    PatchError,
    ERROR_FUNCTION,
    CAN_INTERACT_FUNCTION,
    ensure_names,
    add_import,
    require_import,
    find_function,
    property_pointer,
    local_variable,
    instance_variable,
    assign_text_return,
    return_out,
    patch_can_interact,
    object_name,
    walk,
)

DONOR_ROWS = "WF_GateDonorRows"
TARGET_WEAPON = "WF_GateTargetWeapon"
TARGET_ROWS = "WF_GateTargetRows"
TARGET_VALID = "WF_GateTargetValid"
HAS_ROW = "WF_GateHasRow"
DUPLICATE = "WF_GateDuplicate"

MISSING_TARGET = "WF GATE: current target missing"
NO_SUPPORTED_ROW = "WF GATE: donor has no supported affix"
READY_PREFIX = "WF READY: "
DUPLICATE_PREFIX = "WF BLOCKED: target already has "


def type_name(expr: Any) -> str:
    if not isinstance(expr, dict):
        return type(expr).__name__
    return str(expr.get("$type", "")).split(",", 1)[0].rsplit(".", 1)[-1]


def name_array_property(name: str) -> dict[str, Any]:
    inner = {
        "$type": "UAssetAPI.FieldTypes.FGenericProperty, UAssetAPI",
        "ArrayDim": "TArray", "ElementSize": 12, "PropertyFlags": "CPF_None",
        "RepIndex": 0, "RepNotifyFunc": "None",
        "BlueprintReplicationCondition": "COND_None", "RawValue": None,
        "SerializedType": "NameProperty", "Name": name,
        "Flags": "RF_Public", "MetaDataMap": None,
    }
    return {
        "$type": "UAssetAPI.FieldTypes.FArrayProperty, UAssetAPI",
        "Inner": inner, "ArrayDim": "TArray", "ElementSize": 16,
        "PropertyFlags": "CPF_ReferenceParm", "RepIndex": 0,
        "RepNotifyFunc": "None", "BlueprintReplicationCondition": "COND_None",
        "RawValue": None, "SerializedType": "ArrayProperty",
        "Name": name, "Flags": "RF_Public", "MetaDataMap": None,
    }


def object_property(name: str, class_index: int) -> dict[str, Any]:
    return {
        "$type": "UAssetAPI.FieldTypes.FObjectProperty, UAssetAPI",
        "PropertyClass": class_index, "ArrayDim": "TArray", "ElementSize": 8,
        "PropertyFlags": "CPF_None", "RepIndex": 0,
        "RepNotifyFunc": "None", "BlueprintReplicationCondition": "COND_None",
        "RawValue": None, "SerializedType": "ObjectProperty",
        "Name": name, "Flags": "RF_Public", "MetaDataMap": None,
    }


def bool_property(name: str) -> dict[str, Any]:
    return {
        "$type": "UAssetAPI.FieldTypes.FBoolProperty, UAssetAPI",
        "FieldSize": 1, "ByteOffset": 0, "ByteMask": 1,
        "FieldMask": 255, "NativeBool": True, "Value": True,
        "ArrayDim": "TArray", "ElementSize": 1, "PropertyFlags": "CPF_None",
        "RepIndex": 0, "RepNotifyFunc": "None",
        "BlueprintReplicationCondition": "COND_None", "RawValue": None,
        "SerializedType": "BoolProperty", "Name": name,
        "Flags": "RF_Public", "MetaDataMap": None,
    }


def local_set(owner: int, name: str, expr: dict[str, Any]) -> dict[str, Any]:
    return {
        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_Let, UAssetAPI",
        "Value": property_pointer(owner, name),
        "Variable": local_variable(owner, name),
        "Expression": expr,
    }


def bool_set(owner: int, name: str, expr: dict[str, Any]) -> dict[str, Any]:
    return {
        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_LetBool, UAssetAPI",
        "VariableExpression": local_variable(owner, name),
        "AssignmentExpression": expr,
    }


def final_call(import_index: int, params: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_FinalFunction, UAssetAPI",
        "StackNode": import_index,
        "Parameters": params,
    }


def context(obj: dict[str, Any], dest: dict[str, Any], expr: dict[str, Any]) -> dict[str, Any]:
    return {
        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_Context, UAssetAPI",
        "ObjectExpression": obj,
        "Offset": expression_size(expr),
        "PropertyType": 0,
        "RValuePointer": dest,
        "ContextExpression": expr,
    }


def name_const(row: str) -> dict[str, Any]:
    return {"$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_NameConst, UAssetAPI", "Value": row}


def jump_if_not(expr: dict[str, Any]) -> dict[str, Any]:
    return {
        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_JumpIfNot, UAssetAPI",
        "CodeOffset": 0,
        "BooleanExpression": expr,
    }


def set_array(owner: int, name: str) -> dict[str, Any]:
    return {
        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_SetArray, UAssetAPI",
        "AssigningProperty": local_variable(owner, name),
        "ArrayInnerProp": None,
        "Elements": [],
    }


def array_contains(
    owner: int,
    local_array: str,
    row_expr: dict[str, Any],
    result_bool: str,
    array_default: int,
    contains_function: int,
) -> dict[str, Any]:
    return context(
        {"$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_ObjectConst, UAssetAPI", "Value": array_default},
        property_pointer(owner, result_bool),
        final_call(contains_function, [local_variable(owner, local_array), row_expr]),
    )


def build_error_probe(asset: dict[str, Any], candidates: list[str]) -> dict[str, Any]:
    owner, fn = find_function(asset, ERROR_FUNCTION)
    engine = require_import(asset, "/Script/Engine")
    weapon_cls = require_import(asset, "AWeapon")
    interactive_cls = require_import(asset, "AInteractiveWeapon")
    player_cls = require_import(asset, "Character_Player")

    array_cls = add_import(asset, "KismetArrayLibrary", outer_index=engine, class_name="Class")
    default_array = add_import(
        asset, "Default__KismetArrayLibrary",
        outer_index=engine, class_package="/Script/Engine",
        class_name="KismetArrayLibrary",
    )
    get_rows = add_import(asset, "GetAffixRowNames", outer_index=weapon_cls)
    contains = add_import(asset, "Array_Contains", outer_index=array_cls)

    definitions = [
        name_array_property(DONOR_ROWS),
        object_property(TARGET_WEAPON, weapon_cls),
        name_array_property(TARGET_ROWS),
        bool_property(TARGET_VALID),
        bool_property(HAS_ROW),
        bool_property(DUPLICATE),
    ]
    present = {p.get("Name") for p in fn.get("LoadedProperties") or []}
    if present.intersection({p["Name"] for p in definitions}):
        raise PatchError("GRAFT gate diagnostics are already present; start from vanilla cooked asset")
    fn.setdefault("LoadedProperties", []).extend(definitions)
    ensure_names(
        asset,
        [*(p["Name"] for p in definitions), "currentWeapon", "SpawnedWeapon",
         "PlayerCharacter", *candidates],
    )

    code: list[dict[str, Any]] = []
    labels: dict[str, int] = {}
    unresolved: list[tuple[dict[str, Any], str]] = []

    def emit(expr: dict[str, Any], jump_to: str | None = None) -> None:
        code.append(expr)
        if jump_to:
            unresolved.append((expr, jump_to))

    def label(name: str) -> None:
        if name in labels:
            raise PatchError(f"duplicate label {name}")
        labels[name] = len(code)

    # Target is captured from the real PlayerCharacter argument. Unlike prior
    # mutation probes, this is read-only and reports a missing target explicitly.
    emit(local_set(
        owner, TARGET_WEAPON,
        context(
            local_variable(owner, "PlayerCharacter"),
            property_pointer(owner, TARGET_WEAPON),
            instance_variable(player_cls, "currentWeapon"),
        ),
    ))
    emit(bool_set(
        owner, TARGET_VALID,
        {
            "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_PrimitiveCast, UAssetAPI",
            "ConversionType": "ObjectToBool",
            "Target": local_variable(owner, TARGET_WEAPON),
        },
    ))
    emit(jump_if_not(local_variable(owner, TARGET_VALID)), "missing_target")

    # Both exact row arrays use the same reflected AAWeapon getter that already
    # returned rows during the successful in-game donor-row diagnostic.
    emit(set_array(owner, DONOR_ROWS))
    emit(local_set(
        owner, DONOR_ROWS,
        context(
            instance_variable(interactive_cls, "SpawnedWeapon"),
            property_pointer(owner, DONOR_ROWS),
            final_call(get_rows, []),
        ),
    ))
    emit(set_array(owner, TARGET_ROWS))
    emit(local_set(
        owner, TARGET_ROWS,
        context(
            local_variable(owner, TARGET_WEAPON),
            property_pointer(owner, TARGET_ROWS),
            final_call(get_rows, []),
        ),
    ))

    for i, row in enumerate(candidates):
        next_label = f"next_{i}"
        emit(bool_set(
            owner, HAS_ROW,
            array_contains(owner, DONOR_ROWS, name_const(row), HAS_ROW, default_array, contains),
        ))
        emit(jump_if_not(local_variable(owner, HAS_ROW)), next_label)
        emit(bool_set(
            owner, DUPLICATE,
            array_contains(owner, TARGET_ROWS, name_const(row), DUPLICATE, default_array, contains),
        ))
        emit(jump_if_not(local_variable(owner, DUPLICATE)), f"ready_{i}")
        emit(assign_text_return(owner, DUPLICATE_PREFIX + row, f"WFGateDuplicate_{i}"))
        emit(return_out(owner))
        label(f"ready_{i}")
        emit(assign_text_return(owner, READY_PREFIX + row, f"WFGateReady_{i}"))
        emit(return_out(owner))
        label(next_label)

    emit(assign_text_return(owner, NO_SUPPORTED_ROW, "WFGateNoSupportedRow"))
    emit(return_out(owner))
    label("missing_target")
    emit(assign_text_return(owner, MISSING_TARGET, "WFGateMissingTarget"))
    emit(return_out(owner))

    offsets = []
    total = 0
    for expr in code:
        offsets.append(total)
        total += expression_size(expr)
    for expr, target_label in unresolved:
        n = labels[target_label]
        expr["CodeOffset"] = offsets[n] if n < len(offsets) else total

    insertion = insert_top_level_statements(fn, 0, code)
    return {**insertion, "function": ERROR_FUNCTION, "decision_statuses": 2*len(candidates)+2}


def patch(asset: dict[str, Any], spec: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    result = copy.deepcopy(asset)
    validate_asset(result)
    candidates = [str(x["row"]) for x in spec.get("selection", {}).get("candidates") or []]
    if not candidates or len(candidates) != len(set(candidates)):
        raise PatchError("GRAFT gate requires nonempty unique test rows")
    error_report = build_error_probe(result, candidates)
    interaction_report = patch_can_interact(result)
    validate_asset(result)
    report = {
        "asset": "BP_Interactive_Weapon",
        "mode": "read_only_visible_graft_gate",
        "diagnostic_only": True,
        "bp_aplayer_modified": False,
        "mutation": False,
        "debit": False,
        "donor_consumption": False,
        "interaction_temporarily_disabled": True,
        "candidate_rows": candidates,
        "functions": [error_report, interaction_report],
    }
    verify(result, spec)
    return result, report


def verify(asset: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    validate_asset(asset)
    candidates = [str(x["row"]) for x in spec.get("selection", {}).get("candidates") or []]
    _, fn = find_function(asset, ERROR_FUNCTION)
    _, inter = find_function(asset, CAN_INTERACT_FUNCTION)
    code = fn.get("ScriptBytecode") or []
    status_texts = set()
    calls = set()
    for node in walk(code):
        if not isinstance(node, dict):
            continue
        t = type_name(node)
        if t in {"EX_FinalFunction", "EX_CallMath"}:
            name = object_name(asset, node.get("StackNode"))
            if name:
                calls.add(name)
        if t == "EX_StringConst" and isinstance(node.get("Value"), str):
            status_texts.add(node["Value"])
    for s in (MISSING_TARGET, NO_SUPPORTED_ROW):
        if s not in status_texts:
            raise PatchError(f"missing gate error text: {s}")
    for row in candidates:
        for s in (READY_PREFIX + row, DUPLICATE_PREFIX + row):
            if s not in status_texts:
                raise PatchError(f"missing gate row diagnostic: {s}")
    for name in ("GetAffixRowNames", "Array_Contains"):
        if name not in calls:
            raise PatchError(f"missing gate native call: {name}")
    if len(inter.get("ScriptBytecode") or []) < 2 or type_name(inter["ScriptBytecode"][0]) != "EX_LetBool":
        raise PatchError("gate must disable interaction so the status displays")
    forbidden = {
        "AddEnchantedAffix", "OnServerAddEnchantedAffix", "RemoveTicket",
        "AddTicket", "K2_DestroyActor"
    }
    if calls.intersection(forbidden):
        raise PatchError(f"read-only gate mutated gameplay: {calls & forbidden}")
    for expr in walk(code):
        if not isinstance(expr, dict):
            continue
        if type_name(expr) in {"EX_VirtualFunction", "EX_LocalVirtualFunction"}:
            if expr.get("VirtualFunctionName") in forbidden:
                raise PatchError("gate contains forbidden virtual mutation")
    # UAssetAPI requires every FFieldPath path component registered in NameMap.
    names = set(asset.get("NameMap") or [])
    missing = set()
    for expr in walk(code):
        if isinstance(expr, dict) and type_name(expr) == "FFieldPath":
            for part in expr.get("Path") or []:
                if isinstance(part, str) and part not in names:
                    missing.add(part)
    if missing:
        raise PatchError(f"missing NameMap entries: {sorted(missing)}")
    return {
        "verified": True,
        "asset": "BP_Interactive_Weapon",
        "read_only": True,
        "interaction_temporarily_disabled": True,
        "candidate_count": len(candidates),
        "stages": ["no_current_target", "no_supported_donor_affix", "duplicate_on_target", "ready"],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input_json", type=Path)
    ap.add_argument("spec_json", type=Path)
    ap.add_argument("output_json", type=Path, nargs="?")
    ap.add_argument("--verify-only", action="store_true")
    ap.add_argument("--report", type=Path)
    args = ap.parse_args()
    asset = json.loads(args.input_json.read_text(encoding="utf-8-sig"))
    spec = json.loads(args.spec_json.read_text(encoding="utf-8"))
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
