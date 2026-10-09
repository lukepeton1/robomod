#!/usr/bin/env python3
"""Read-only raw donor FName inspector, displayed through native GetErrorText.

This probe is intentionally separate from the older 11-candidate gate. It
distinguishes a missing weapon, an empty native row array, a non-matching row,
a verified candidate, and a duplicate. It also displays the first three
native FName values to diagnose assumptions about DataTable row IDs.

The probe does not mutate weapons, send RPCs, spend currency, or consume drops.
Normal pickup is temporarily disabled so the text is visible on E.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

from kismet_layout import expression_size, insert_top_level_statements, validate_asset
from patch_donor_rowname_probe import (
    CAN_INTERACT_FUNCTION, ERROR_FUNCTION, PatchError, add_import,
    assign_text_return, ensure_names, find_function, instance_variable,
    local_out_variable, local_variable, object_name, patch_can_interact,
    property_pointer, require_import, return_out, walk,
)
from patch_ground_graft_gate_probe import (
    array_contains, bool_property, bool_set, context, final_call,
    jump_if_not, local_set, name_array_property, name_const, object_property,
    set_array, type_name,
)

DONOR_WEAPON = "WF_RawDonorWeapon"
TARGET_WEAPON = "WF_RawTargetWeapon"
DONOR_VALID = "WF_RawDonorValid"
TARGET_VALID = "WF_RawTargetValid"
DONOR_ROWS = "WF_RawDonorRows"
TARGET_ROWS = "WF_RawTargetRows"
COUNT = "WF_RawCount"
MESSAGE = "WF_RawMessage"
ROW_NAMES = ("WF_RawRow0", "WF_RawRow1", "WF_RawRow2")
SELF_CONTAINS = "WF_RawSelfContains"
MATCHES = "WF_RawMatches"
DUPLICATE = "WF_RawDuplicate"

MISSING_DONOR = "WF RAW: donor weapon missing"
MISSING_TARGET = "WF RAW: current target missing"
ZERO_ROWS = "WF RAW: donor rows=0"
NO_MATCH = " |gate=NO_MATCH"
SELF_OK = " |self=OK"
SELF_FAIL = " |self=FAIL"


def generic_property(name: str, serialized_type: str, element_size: int) -> dict[str, Any]:
    return {
        "$type": "UAssetAPI.FieldTypes.FGenericProperty, UAssetAPI",
        "ArrayDim": "TArray", "ElementSize": element_size,
        "PropertyFlags": "CPF_None", "RepIndex": 0,
        "RepNotifyFunc": "None", "BlueprintReplicationCondition": "COND_None",
        "RawValue": None, "SerializedType": serialized_type,
        "Name": name, "Flags": "RF_Public", "MetaDataMap": None,
    }


def int_const(value: int) -> dict[str, Any]:
    return {
        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_IntConst, UAssetAPI",
        "Value": value,
    }


def str_const(value: str) -> dict[str, Any]:
    return {
        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_StringConst, UAssetAPI",
        "Value": value,
    }


def math_call(index: int, *args: dict[str, Any]) -> dict[str, Any]:
    return {
        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_CallMath, UAssetAPI",
        "StackNode": index, "Parameters": list(args),
    }


def jump() -> dict[str, Any]:
    return {
        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_Jump, UAssetAPI",
        "CodeOffset": 0,
    }


def object_to_bool(owner: int, local_name: str) -> dict[str, Any]:
    return {
        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_PrimitiveCast, UAssetAPI",
        "ConversionType": "ObjectToBool",
        "Target": local_variable(owner, local_name),
    }


def assign_message_return(owner: int, converter: int) -> dict[str, Any]:
    return {
        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_Let, UAssetAPI",
        "Value": property_pointer(owner, "ReturnValue"),
        "Variable": local_out_variable(owner, "ReturnValue"),
        "Expression": math_call(converter, local_variable(owner, MESSAGE)),
    }


def build_error_probe(asset: dict[str, Any], candidates: list[str]) -> dict[str, Any]:
    owner, fn = find_function(asset, ERROR_FUNCTION)
    engine = require_import(asset, "/Script/Engine")
    weapon_cls = require_import(asset, "AWeapon")
    interactive_cls = require_import(asset, "AInteractiveWeapon")
    player_cls = require_import(asset, "Character_Player")
    math_cls = require_import(asset, "KismetMathLibrary")

    array_cls = add_import(asset, "KismetArrayLibrary", outer_index=engine,
                           class_package="/Script/CoreUObject", class_name="Class")
    default_array = add_import(asset, "Default__KismetArrayLibrary",
                               outer_index=engine, class_package="/Script/Engine",
                               class_name="KismetArrayLibrary")
    string_cls = add_import(asset, "KismetStringLibrary", outer_index=engine,
                            class_package="/Script/CoreUObject", class_name="Class")
    text_cls = add_import(asset, "KismetTextLibrary", outer_index=engine,
                          class_package="/Script/CoreUObject", class_name="Class")

    get_rows = add_import(asset, "GetAffixRowNames", outer_index=weapon_cls,
                          class_package="/Script/CoreUObject", class_name="Object")
    array_length = add_import(asset, "Array_Length", outer_index=array_cls,
                              class_package="/Script/CoreUObject", class_name="Object")
    array_get = add_import(asset, "Array_Get", outer_index=array_cls,
                           class_package="/Script/CoreUObject", class_name="Object")
    contains = add_import(asset, "Array_Contains", outer_index=array_cls,
                          class_package="/Script/CoreUObject", class_name="Object")
    greater = add_import(asset, "Greater_IntInt", outer_index=math_cls,
                         class_package="/Script/CoreUObject", class_name="Object")
    int_to_string = add_import(asset, "Conv_IntToString", outer_index=string_cls,
                               class_package="/Script/CoreUObject", class_name="Object")
    name_to_string = add_import(asset, "Conv_NameToString", outer_index=string_cls,
                                class_package="/Script/CoreUObject", class_name="Object")
    concat = add_import(asset, "Concat_StrStr", outer_index=string_cls,
                        class_package="/Script/CoreUObject", class_name="Object")
    string_to_text = add_import(asset, "Conv_StringToText", outer_index=text_cls,
                                class_package="/Script/CoreUObject", class_name="Object")

    definitions = [
        object_property(DONOR_WEAPON, weapon_cls),
        object_property(TARGET_WEAPON, weapon_cls),
        bool_property(DONOR_VALID), bool_property(TARGET_VALID),
        name_array_property(DONOR_ROWS), name_array_property(TARGET_ROWS),
        generic_property(COUNT, "IntProperty", 4),
        generic_property(MESSAGE, "StrProperty", 16),
        *(generic_property(n, "NameProperty", 12) for n in ROW_NAMES),
        bool_property(SELF_CONTAINS),
        bool_property(MATCHES), bool_property(DUPLICATE),
    ]
    already = {p.get("Name") for p in fn.get("LoadedProperties") or []}
    overlap = already.intersection(p["Name"] for p in definitions)
    if overlap:
        raise PatchError(f"raw row inspector locals already present: {sorted(overlap)}")
    fn.setdefault("LoadedProperties", []).extend(definitions)
    ensure_names(asset, [*(p["Name"] for p in definitions), "currentWeapon",
                         "SpawnedWeapon", "PlayerCharacter", "ReturnValue", *candidates])

    code: list[dict[str, Any]] = []
    labels: dict[str, int] = {}
    unresolved: list[tuple[dict[str, Any], str]] = []

    def emit(expr: dict[str, Any], dest: str | None = None) -> None:
        code.append(expr)
        if dest is not None:
            unresolved.append((expr, dest))

    def label(name: str) -> None:
        if name in labels:
            raise PatchError(f"duplicate probe label: {name}")
        labels[name] = len(code)

    def append(text_expr: dict[str, Any]) -> None:
        emit(local_set(owner, MESSAGE, math_call(
            concat, local_variable(owner, MESSAGE), text_expr,
        )))

    def append_static(value: str) -> None:
        append(str_const(value))

    def has_at_least(amount: int) -> dict[str, Any]:
        return math_call(greater, local_variable(owner, COUNT), int_const(amount - 1))

    def library_call(out_name: str, import_idx: int,
                     args: list[dict[str, Any]]) -> dict[str, Any]:
        return context(
            {"$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_ObjectConst, UAssetAPI",
             "Value": default_array},
            property_pointer(owner, out_name),
            final_call(import_idx, args),
        )

    # Check references before any native calls. GetErrorText is a read-only
    # interaction callback, not a server-authoritative commit seam.
    emit(local_set(owner, DONOR_WEAPON,
                   instance_variable(interactive_cls, "SpawnedWeapon")))
    emit(bool_set(owner, DONOR_VALID, object_to_bool(owner, DONOR_WEAPON)))
    emit(jump_if_not(local_variable(owner, DONOR_VALID)), "missing_donor")
    emit(local_set(owner, TARGET_WEAPON, context(
        local_variable(owner, "PlayerCharacter"),
        property_pointer(owner, TARGET_WEAPON),
        instance_variable(player_cls, "currentWeapon"),
    )))
    emit(bool_set(owner, TARGET_VALID, object_to_bool(owner, TARGET_WEAPON)))
    emit(jump_if_not(local_variable(owner, TARGET_VALID)), "missing_target")

    emit(set_array(owner, DONOR_ROWS))
    emit(local_set(owner, DONOR_ROWS, context(
        local_variable(owner, DONOR_WEAPON),
        property_pointer(owner, DONOR_ROWS), final_call(get_rows, []),
    )))
    emit(local_set(owner, COUNT,
                   library_call(COUNT, array_length,
                                [local_variable(owner, DONOR_ROWS)])))
    emit(jump_if_not(has_at_least(1)), "zero_rows")

    emit(set_array(owner, TARGET_ROWS))
    emit(local_set(owner, TARGET_ROWS, context(
        local_variable(owner, TARGET_WEAPON),
        property_pointer(owner, TARGET_ROWS), final_call(get_rows, []),
    )))
    emit(local_set(owner, MESSAGE, math_call(
        concat, str_const("WF n="),
        math_call(int_to_string, local_variable(owner, COUNT)),
    )))

    # Unroll a bounded sample: every Array_Get is reached only when
    # Array_Length > index. Do not read an empty or short native array.
    for i, row_name in enumerate(ROW_NAMES):
        label_suffix = f"sample_next_{i}"
        emit(jump_if_not(has_at_least(i + 1)), label_suffix)
        emit(library_call(row_name, array_get, [
            local_variable(owner, DONOR_ROWS), int_const(i),
            local_out_variable(owner, row_name),
        ]))
        append_static(f" |{i}=")
        append(math_call(name_to_string, local_variable(owner, row_name)))
        label(label_suffix)

    # Round-trip the exact FName extracted at index 0 through Array_Contains.
    # This distinguishes "native rows exist" from generic-array thunk failure.
    emit(bool_set(owner, SELF_CONTAINS,
                  library_call(SELF_CONTAINS, contains, [
                      local_variable(owner, DONOR_ROWS),
                      local_variable(owner, ROW_NAMES[0]),
                  ])))
    emit(jump_if_not(local_variable(owner, SELF_CONTAINS)), "self_failed")
    append_static(SELF_OK)
    emit(jump(), "after_self")
    label("self_failed")
    append_static(SELF_FAIL)
    label("after_self")

    # Check known row IDs only after printing actual native names. The prior
    # diagnostic conflated an empty array, an unexpected FName and a bad
    # generic-array comparison as one "unsupported" status.
    for i, row in enumerate(candidates):
        emit(bool_set(owner, MATCHES,
                      library_call(MATCHES, contains, [
                          local_variable(owner, DONOR_ROWS), name_const(row),
                      ])))
        emit(jump_if_not(local_variable(owner, MATCHES)), f"next_candidate_{i}")
        emit(bool_set(owner, DUPLICATE,
                      library_call(DUPLICATE, contains, [
                          local_variable(owner, TARGET_ROWS), name_const(row),
                      ])))
        emit(jump_if_not(local_variable(owner, DUPLICATE)), f"ready_{i}")
        append_static(" |gate=DUP:" + row)
        emit(jump(), "after_gate")
        label(f"ready_{i}")
        append_static(" |gate=OK:" + row)
        emit(jump(), "after_gate")
        label(f"next_candidate_{i}")

    append_static(NO_MATCH)
    label("after_gate")
    emit(assign_message_return(owner, string_to_text))
    emit(return_out(owner))

    label("zero_rows")
    emit(assign_text_return(owner, ZERO_ROWS, "WFRawRowsZero"))
    emit(return_out(owner))
    label("missing_target")
    emit(assign_text_return(owner, MISSING_TARGET, "WFRawTargetMissing"))
    emit(return_out(owner))
    label("missing_donor")
    emit(assign_text_return(owner, MISSING_DONOR, "WFRawDonorMissing"))
    emit(return_out(owner))

    offsets: list[int] = []
    size = 0
    for expr in code:
        offsets.append(size)
        size += expression_size(expr)
    for expr, to in unresolved:
        if to not in labels:
            raise PatchError(f"unresolved diagnostic label: {to}")
        position = labels[to]
        expr["CodeOffset"] = offsets[position] if position < len(offsets) else size

    report = insert_top_level_statements(fn, 0, code)
    return {**report, "function": ERROR_FUNCTION, "samples": len(ROW_NAMES),
            "candidate_rows": len(candidates)}


def patch(asset: dict[str, Any], spec: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    result = copy.deepcopy(asset)
    validate_asset(result)
    candidates = [str(x["row"]) for x in spec.get("selection", {}).get("candidates") or []]
    if not candidates or len(candidates) != len(set(candidates)):
        raise PatchError("raw GRAFT probe needs unique, nonempty candidate rows")
    error = build_error_probe(result, candidates)
    interact = patch_can_interact(result)
    validate_asset(result)
    verify(result, spec)
    return result, {
        "asset": "BP_Interactive_Weapon",
        "mode": "read_only_raw_donor_row_inspector",
        "diagnostic_only": True,
        "bp_aplayer_modified": False,
        "mutation": False, "debit": False, "donor_consumption": False,
        "interaction_temporarily_disabled": True,
        "candidate_rows": candidates,
        "sample_count": len(ROW_NAMES),
        "functions": [error, interact],
    }


def verify(asset: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    validate_asset(asset)
    owner, fn = find_function(asset, ERROR_FUNCTION)
    _, interact = find_function(asset, CAN_INTERACT_FUNCTION)
    code = fn.get("ScriptBytecode") or []
    props = {p.get("Name"): p for p in fn.get("LoadedProperties") or []}
    required = (DONOR_WEAPON, TARGET_WEAPON, DONOR_VALID, TARGET_VALID,
                DONOR_ROWS, TARGET_ROWS, COUNT, MESSAGE, *ROW_NAMES,
                SELF_CONTAINS, MATCHES, DUPLICATE)
    missing = set(required) - set(props)
    if missing:
        raise PatchError(f"raw probe has missing locals: {sorted(missing)}")
    if props[DONOR_ROWS].get("SerializedType") != "ArrayProperty" or (
        props[DONOR_ROWS].get("Inner") or {}
    ).get("SerializedType") != "NameProperty":
        raise PatchError("donor rows must be TArray<FName>")
    if props[MESSAGE].get("SerializedType") != "StrProperty":
        raise PatchError("raw row display buffer must be FString")
    for n in ROW_NAMES:
        if props[n].get("SerializedType") != "NameProperty":
            raise PatchError(f"raw name sample is not FName: {n}")

    calls = []
    texts = set()
    array_get_indices = []
    self_test = False
    for expr in walk(code):
        if not isinstance(expr, dict):
            continue
        kind = type_name(expr)
        if kind in ("EX_FinalFunction", "EX_CallMath"):
            name = object_name(asset, expr.get("StackNode"))
            if name:
                calls.append(name)
            if name == "Array_Get":
                params = expr.get("Parameters") or []
                if len(params) != 3 or type_name(params[1]) != "EX_IntConst":
                    raise PatchError("Array_Get must use constant bounded index")
                array_get_indices.append(params[1].get("Value"))
            if name == "Array_Contains":
                params = expr.get("Parameters") or []
                if len(params) >= 2 and type_name(params[1]) == "EX_LocalVariable":
                    name_path = (((params[1].get("Variable") or {}).get("New") or {}).get("Path"))
                    if name_path == [ROW_NAMES[0]]:
                        self_test = True
        if kind == "EX_StringConst":
            texts.add(expr.get("Value"))

    necessary_calls = {
        "GetAffixRowNames", "Array_Length", "Array_Get", "Array_Contains",
        "Greater_IntInt", "Conv_IntToString", "Conv_NameToString",
        "Concat_StrStr", "Conv_StringToText",
    }
    if not necessary_calls.issubset(calls):
        raise PatchError(f"raw row calls missing: {sorted(necessary_calls - set(calls))}")
    if array_get_indices != list(range(len(ROW_NAMES))) or not self_test:
        raise PatchError("missing bounded donor sample or native self-contains check")
    for text_value in (SELF_OK, SELF_FAIL, NO_MATCH):
        if text_value not in texts:
            raise PatchError(f"missing diagnostic marker: {text_value}")
    candidates = [str(x["row"]) for x in spec.get("selection", {}).get("candidates") or []]
    for row in candidates:
        if name_const(row) not in [e for e in walk(code) if type_name(e) == "EX_NameConst"]:
            raise PatchError(f"candidate not compared: {row}")

    # Every generic Array_Get must have its own exact count > index guard,
    # with a jump destination beyond the array read itself.
    top = code
    guarded_indices: list[int] = []
    for i, expr in enumerate(top):
        if type_name(expr) != "EX_Context":
            continue
        call = expr.get("ContextExpression") or {}
        if type_name(call) != "EX_FinalFunction" or (
            object_name(asset, call.get("StackNode")) != "Array_Get"
        ):
            continue
        call_params = call.get("Parameters") or []
        index = call_params[1].get("Value") if len(call_params) == 3 else None
        if not isinstance(index, int) or i == 0 or (
            type_name(top[i - 1]) != "EX_JumpIfNot"
        ):
            raise PatchError("Array_Get is not preceded by its count guard")
        guard = top[i - 1]
        cond = guard.get("BooleanExpression") or {}
        if type_name(cond) != "EX_CallMath" or (
            object_name(asset, cond.get("StackNode")) != "Greater_IntInt"
        ):
            raise PatchError("Array_Get count guard is not Greater_IntInt")
        params = cond.get("Parameters") or []
        count_path = (((params[0].get("Variable") or {}).get("New") or {}).get("Path")
                      if params and type_name(params[0]) == "EX_LocalVariable" else None)
        threshold = (params[1].get("Value") if len(params) == 2 and
                     type_name(params[1]) == "EX_IntConst" else None)
        if count_path != [COUNT] or threshold != index:
            raise PatchError("Array_Get guard does not compare COUNT > exact index")
        end_of_read = sum(expression_size(item) for item in top[:i + 1])
        if not isinstance(guard.get("CodeOffset"), int) or (
            guard["CodeOffset"] < end_of_read
        ):
            raise PatchError("Array_Get zero/short-array branch can enter the read")
        guarded_indices.append(index)
    if guarded_indices != list(range(len(ROW_NAMES))):
        raise PatchError("unverified bounded FName sample indices")

    inter_code = interact.get("ScriptBytecode") or []
    if len(inter_code) < 2 or type_name(inter_code[0]) != "EX_LetBool" or (
        type_name(inter_code[0].get("AssignmentExpression")) != "EX_False"
    ):
        raise PatchError("read-only raw probe must disable normal pickup")
    forbidden = {
        "AddEnchantedAffix", "OnServerAddEnchantedAffix",
        "RemoveTicket", "AddTicket", "K2_DestroyActor",
    }
    if forbidden.intersection(calls):
        raise PatchError(f"raw probe contains a mutation call: {forbidden & set(calls)}")
    names = set(asset.get("NameMap") or [])
    for expr in walk(code):
        if isinstance(expr, dict) and type_name(expr) == "FFieldPath":
            if not set(expr.get("Path") or []).issubset(names):
                raise PatchError("raw probe introduced unregistered FFieldPath name")
    return {
        "verified": True,
        "read_only": True,
        "sample_indices": array_get_indices,
        "array_self_check": self_test,
        "candidate_count": len(candidates),
        "functions": [ERROR_FUNCTION, CAN_INTERACT_FUNCTION],
        "stages": ["missing_donor", "missing_target", "zero_rows",
                   "raw_rows", "self_check", "candidate_match", "duplicate"],
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
