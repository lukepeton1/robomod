#!/usr/bin/env python3
"""Patch BP_APlayer.OnServerPingActor with an end-to-end ground GRAFT probe.

The existing Roboquest ping action is used as a temporary alternate interaction:
- pinging ordinary actors falls through to vanilla OnServerPingActor behavior;
- pinging an AInteractiveWeapon lets the *server* read SpawnedWeapon.GetAffixRowNames();
- the first probe-approved donor row is selected by deterministic priority;
- target/current weapon, duplicate state, quality cap and Power Cells are validated;
- Power Cells are debited;
- the existing BP_APlayer.AddEnchantedAffix(RowName) replication chain mutates target;
- target GetAffixRowNames() is re-read synchronously;
- failed verification refunds currency and leaves donor untouched;
- successful verification destroys the dropped donor interactive and returns early.

This is deliberately a diagnostic bridge to the final explicit donor-row selection UI.
It does not replace normal E equip/swap behavior.
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


FUNCTION = "OnServerPingActor"

LOCAL_DONOR_INTERACTIVE = "WF_DonorInteractive"
LOCAL_CAST_OK = "WF_CastOk"
LOCAL_DONOR_WEAPON = "WF_DonorWeapon"
LOCAL_DONOR_VALID = "WF_DonorValid"
LOCAL_DONOR_ROWS = "WF_DonorRows"
LOCAL_CONTAINS = "WF_Contains"
LOCAL_SELECTED_ROW = "WF_SelectedRow"
LOCAL_BASE_COST = "WF_BaseCost"
LOCAL_DISTINCT = "WF_Distinct"
LOCAL_TARGET_ROWS = "WF_TargetRows"
LOCAL_TARGET_CONTAINS = "WF_TargetContains"
LOCAL_NON_COMMON = "WF_NonCommon"
LOCAL_UNDER_CAP = "WF_UnderCap"
LOCAL_TOTAL_COST = "WF_TotalCost"
LOCAL_HAS_FUNDS = "WF_HasFunds"
LOCAL_VERIFIED = "WF_Verified"


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


def name_const(asset: dict[str, Any], value: str) -> dict[str, Any]:
    ensure_name(asset, value)
    return {
        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_NameConst, UAssetAPI",
        "Value": value,
    }


def false_const() -> dict[str, Any]:
    return {"$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_False, UAssetAPI"}


def nothing() -> dict[str, Any]:
    return {"$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_Nothing, UAssetAPI"}


def math_call(stack_node: int, parameters: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_CallMath, UAssetAPI",
        "StackNode": stack_node,
        "Parameters": parameters,
    }


def final_call(stack_node: int, parameters: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_FinalFunction, UAssetAPI",
        "StackNode": stack_node,
        "Parameters": parameters,
    }


def local_virtual(name: str, parameters: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_LocalVirtualFunction, UAssetAPI",
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


def property_context(
    obj: dict[str, Any],
    owner: int,
    name: str,
) -> dict[str, Any]:
    expr = instance(owner, name)
    return context(obj, pointer(owner, name), expr)


def function_context(
    obj: dict[str, Any],
    function_index: int,
    rvalue: dict[str, Any],
    parameters: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    expr = final_call(function_index, parameters or [])
    return context(obj, rvalue, expr)


def struct_member(
    struct_expression: dict[str, Any],
    struct_owner: int,
    name: str,
) -> dict[str, Any]:
    return {
        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_StructMemberContext, UAssetAPI",
        "StructMemberExpression": pointer(struct_owner, name),
        "StructExpression": struct_expression,
    }


def object_to_bool(expr: dict[str, Any]) -> dict[str, Any]:
    return {
        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_PrimitiveCast, UAssetAPI",
        "ConversionType": "ObjectToBool",
        "Target": expr,
    }


def let(owner: int, name: str, expr: dict[str, Any]) -> dict[str, Any]:
    return {
        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_Let, UAssetAPI",
        "Value": pointer(owner, name),
        "Variable": local(owner, name),
        "Expression": expr,
    }


def let_obj(owner: int, name: str, expr: dict[str, Any]) -> dict[str, Any]:
    return {
        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_LetObj, UAssetAPI",
        "VariableExpression": local(owner, name),
        "AssignmentExpression": expr,
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


def return_void() -> dict[str, Any]:
    return {
        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_Return, UAssetAPI",
        "ReturnExpression": nothing(),
    }


def object_property(name: str, class_index: int) -> dict[str, Any]:
    return {
        "$type": "UAssetAPI.FieldTypes.FObjectProperty, UAssetAPI",
        "PropertyClass": class_index,
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


def name_array_property(name: str) -> dict[str, Any]:
    inner = generic_property(name, "NameProperty", 12)
    return {
        "$type": "UAssetAPI.FieldTypes.FArrayProperty, UAssetAPI",
        "Inner": inner,
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


def add_probe_locals(
    asset: dict[str, Any],
    fn: dict[str, Any],
    ainteractive_weapon: int,
    aweapon: int,
) -> None:
    loaded = fn.setdefault("LoadedProperties", [])
    names = {p.get("Name") for p in loaded}
    definitions = [
        object_property(LOCAL_DONOR_INTERACTIVE, ainteractive_weapon),
        bool_property(LOCAL_CAST_OK),
        object_property(LOCAL_DONOR_WEAPON, aweapon),
        bool_property(LOCAL_DONOR_VALID),
        name_array_property(LOCAL_DONOR_ROWS),
        bool_property(LOCAL_CONTAINS),
        generic_property(LOCAL_SELECTED_ROW, "NameProperty", 12),
        generic_property(LOCAL_BASE_COST, "IntProperty", 4),
        bool_property(LOCAL_DISTINCT),
        name_array_property(LOCAL_TARGET_ROWS),
        bool_property(LOCAL_TARGET_CONTAINS),
        bool_property(LOCAL_NON_COMMON),
        bool_property(LOCAL_UNDER_CAP),
        generic_property(LOCAL_TOTAL_COST, "IntProperty", 4),
        bool_property(LOCAL_HAS_FUNDS),
        bool_property(LOCAL_VERIFIED),
    ]
    overlap = names & {p["Name"] for p in definitions}
    if overlap:
        raise PatchError(f"ground GRAFT probe locals already exist: {sorted(overlap)}")
    for prop in definitions:
        ensure_name(asset, prop["Name"])
        loaded.append(prop)


def array_contains(
    owner: int,
    array_name: str,
    item: dict[str, Any],
    result_name: str,
    default_array: int,
    array_contains_index: int,
) -> dict[str, Any]:
    expr = final_call(
        array_contains_index,
        [local(owner, array_name), item],
    )
    return context(
        object_const(default_array),
        pointer(owner, result_name),
        expr,
    )


def get_row_names(
    owner: int,
    weapon_expr: dict[str, Any],
    array_name: str,
    getter_index: int,
) -> dict[str, Any]:
    return function_context(
        weapon_expr,
        getter_index,
        pointer(owner, array_name),
    )


def compile_block(
    asset: dict[str, Any],
    fn_index: int,
    fn: dict[str, Any],
    spec: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if len(fn.get("ScriptBytecode") or []) < 3:
        raise PatchError("OnServerPingActor bytecode shape is unexpectedly short")

    ainteractive_weapon = require_import(asset, "AInteractiveWeapon")
    aweapon = require_import(asset, "AWeapon")
    character_player = require_import(asset, "Character_Player")
    actor_class = require_import(asset, "Actor")
    roboquest_package = require_import(asset, "/Script/RoboQuest")
    kismet_array = require_import(asset, "KismetArrayLibrary")
    default_array = require_import(asset, "Default__KismetArrayLibrary")
    kismet_math = require_import(asset, "KismetMathLibrary")

    get_rows = add_import(asset, "GetAffixRowNames", outer_index=aweapon)
    destroy_actor = add_import(asset, "K2_DestroyActor", outer_index=actor_class)
    greater_byte = add_import(asset, "Greater_ByteByte", outer_index=kismet_math)
    max_int = add_import(asset, "Max_IntInt", outer_index=kismet_math)
    weapon_affix_rarity = add_import(
        asset,
        "WeaponAffixRarity",
        outer_index=roboquest_package,
    )

    array_contains_index = require_import(asset, "Array_Contains")
    less_int = require_import(asset, "Less_IntInt")
    conv_byte_to_int = require_import(asset, "Conv_ByteToInt")
    add_int = require_import(asset, "Add_IntInt")
    subtract_int = require_import(asset, "Subtract_IntInt")
    greater_equal_int = require_import(asset, "GreaterEqual_IntInt")
    not_equal_object = require_import(asset, "NotEqual_ObjectObject")
    remove_ticket = require_import(asset, "RemoveTicket")
    add_ticket = require_import(asset, "AddTicket")

    add_probe_locals(asset, fn, ainteractive_weapon, aweapon)

    candidates = list(spec.get("selection", {}).get("candidates") or [])
    if not candidates:
        raise PatchError("probe spec has no candidate rows")

    free_affixes = int(spec.get("free_complexity_affixes", 2))
    if free_affixes != 2:
        raise PatchError("probe currently expects the production free-affix threshold of 2")

    statements: list[dict[str, Any]] = []
    labels: dict[str, int] = {}
    jump_targets: list[tuple[dict[str, Any], str]] = []

    def label(name: str) -> None:
        if name in labels:
            raise PatchError(f"duplicate block label {name}")
        labels[name] = len(statements)

    def emit(expr: dict[str, Any], target: str | None = None) -> None:
        statements.append(expr)
        if target is not None:
            jump_targets.append((expr, target))

    # ActorRef -> AInteractiveWeapon.
    emit({
        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_Let, UAssetAPI",
        "Value": pointer(0, []),
        "Variable": local(fn_index, LOCAL_DONOR_INTERACTIVE),
        "Expression": {
            "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_DynamicCast, UAssetAPI",
            "ClassPtr": ainteractive_weapon,
            "Target": local(fn_index, "ActorRef"),
        },
    })
    emit(let_bool(
        fn_index,
        LOCAL_CAST_OK,
        object_to_bool(local(fn_index, LOCAL_DONOR_INTERACTIVE)),
    ))
    emit(jump_if_not(local(fn_index, LOCAL_CAST_OK)), "fallthrough")

    donor_spawned_weapon = property_context(
        local(fn_index, LOCAL_DONOR_INTERACTIVE),
        ainteractive_weapon,
        "SpawnedWeapon",
    )
    emit(let_obj(fn_index, LOCAL_DONOR_WEAPON, donor_spawned_weapon))
    emit(let_bool(
        fn_index,
        LOCAL_DONOR_VALID,
        object_to_bool(local(fn_index, LOCAL_DONOR_WEAPON)),
    ))
    emit(jump_if_not(local(fn_index, LOCAL_DONOR_VALID)), "fallthrough")

    emit(let(
        fn_index,
        LOCAL_DONOR_ROWS,
        get_row_names(
            fn_index,
            local(fn_index, LOCAL_DONOR_WEAPON),
            LOCAL_DONOR_ROWS,
            get_rows,
        ),
    ))

    # Deterministic automatic choice for the probe. Final UI will replace this.
    for i, candidate in enumerate(candidates):
        row_id = str(candidate["row"])
        base_cost = int(candidate["base_cost"])
        label(f"candidate_{i}")
        emit(let_bool(
            fn_index,
            LOCAL_CONTAINS,
            array_contains(
                fn_index,
                LOCAL_DONOR_ROWS,
                name_const(asset, row_id),
                LOCAL_CONTAINS,
                default_array,
                array_contains_index,
            ),
        ))
        emit(
            jump_if_not(local(fn_index, LOCAL_CONTAINS)),
            f"candidate_{i + 1}" if i + 1 < len(candidates) else "fallthrough",
        )
        emit(let(fn_index, LOCAL_SELECTED_ROW, name_const(asset, row_id)))
        emit(let(fn_index, LOCAL_BASE_COST, int_const(base_cost)))
        emit(jump(), "selected")

    label("selected")

    current_weapon = instance(character_player, "currentWeapon")
    emit(let_bool(
        fn_index,
        LOCAL_DISTINCT,
        math_call(
            not_equal_object,
            [local(fn_index, LOCAL_DONOR_WEAPON), copy.deepcopy(current_weapon)],
        ),
    ))
    emit(jump_if_not(local(fn_index, LOCAL_DISTINCT)), "fallthrough")

    emit(let(
        fn_index,
        LOCAL_TARGET_ROWS,
        get_row_names(
            fn_index,
            copy.deepcopy(current_weapon),
            LOCAL_TARGET_ROWS,
            get_rows,
        ),
    ))
    emit(let_bool(
        fn_index,
        LOCAL_TARGET_CONTAINS,
        array_contains(
            fn_index,
            LOCAL_TARGET_ROWS,
            local(fn_index, LOCAL_SELECTED_ROW),
            LOCAL_TARGET_CONTAINS,
            default_array,
            array_contains_index,
        ),
    ))
    # Continue only if duplicate lookup is false.
    emit(jump_if_not(local(fn_index, LOCAL_TARGET_CONTAINS)), "no_duplicate")
    emit(jump(), "fallthrough")

    label("no_duplicate")

    current_bundle = property_context(
        copy.deepcopy(current_weapon),
        aweapon,
        "CurrentAffixBundle",
    )
    color = struct_member(
        current_bundle,
        weapon_affix_rarity,
        "Color",
    )
    emit(let_bool(
        fn_index,
        LOCAL_NON_COMMON,
        math_call(
            greater_byte,
            [copy.deepcopy(color), byte_const(0)],
        ),
    ))
    emit(jump_if_not(local(fn_index, LOCAL_NON_COMMON)), "fallthrough")

    affix_amount = property_context(
        copy.deepcopy(current_weapon),
        aweapon,
        "AffixAmount",
    )
    quality_cap = math_call(
        add_int,
        [
            math_call(conv_byte_to_int, [copy.deepcopy(color)]),
            int_const(free_affixes),
        ],
    )
    emit(let_bool(
        fn_index,
        LOCAL_UNDER_CAP,
        math_call(
            less_int,
            [copy.deepcopy(affix_amount), quality_cap],
        ),
    ))
    emit(jump_if_not(local(fn_index, LOCAL_UNDER_CAP)), "fallthrough")

    surcharge = math_call(
        max_int,
        [
            math_call(
                subtract_int,
                [copy.deepcopy(affix_amount), int_const(free_affixes)],
            ),
            int_const(0),
        ],
    )
    emit(let(
        fn_index,
        LOCAL_TOTAL_COST,
        math_call(
            add_int,
            [local(fn_index, LOCAL_BASE_COST), surcharge],
        ),
    ))
    emit(let_bool(
        fn_index,
        LOCAL_HAS_FUNDS,
        math_call(
            greater_equal_int,
            [
                instance(character_player, "CurrentTicket"),
                local(fn_index, LOCAL_TOTAL_COST),
            ],
        ),
    ))
    emit(jump_if_not(local(fn_index, LOCAL_HAS_FUNDS)), "fallthrough")

    # Commit.
    emit(final_call(remove_ticket, [local(fn_index, LOCAL_TOTAL_COST)]))
    emit(local_virtual(
        "AddEnchantedAffix",
        [local(fn_index, LOCAL_SELECTED_ROW)],
    ))

    # Verify the actual native target row list before donor destruction.
    emit(let(
        fn_index,
        LOCAL_TARGET_ROWS,
        get_row_names(
            fn_index,
            copy.deepcopy(current_weapon),
            LOCAL_TARGET_ROWS,
            get_rows,
        ),
    ))
    emit(let_bool(
        fn_index,
        LOCAL_VERIFIED,
        array_contains(
            fn_index,
            LOCAL_TARGET_ROWS,
            local(fn_index, LOCAL_SELECTED_ROW),
            LOCAL_VERIFIED,
            default_array,
            array_contains_index,
        ),
    ))
    emit(jump_if_not(local(fn_index, LOCAL_VERIFIED)), "refund")

    destroy_expr = final_call(destroy_actor, [])
    emit(context(
        local(fn_index, LOCAL_DONOR_INTERACTIVE),
        pointer(0, []),
        destroy_expr,
    ))
    emit(return_void())

    label("refund")
    emit(final_call(
        add_ticket,
        [local(fn_index, LOCAL_TOTAL_COST), false_const()],
    ))
    emit(jump(), "fallthrough")

    label("fallthrough")

    original_offsets, _ = top_level_offsets(fn["ScriptBytecode"])
    insertion_index = 2  # preserve ActorRef/Location -> persistent-frame assignments
    insertion_offset = original_offsets[insertion_index]

    relative_offsets: list[int] = []
    cursor = 0
    for statement in statements:
        relative_offsets.append(cursor)
        cursor += expression_size(statement)
    block_size = cursor

    for statement, target_name in jump_targets:
        if target_name not in labels:
            raise PatchError(f"unknown block label {target_name}")
        target_index = labels[target_name]
        if target_index == len(statements):
            target_offset = insertion_offset + block_size
        else:
            target_offset = insertion_offset + relative_offsets[target_index]
        statement["CodeOffset"] = target_offset

    report = {
        "function": FUNCTION,
        "insertion_index": insertion_index,
        "insertion_offset": insertion_offset,
        "block_size": block_size,
        "candidate_rows": [
            {"row": str(row["row"]), "base_cost": int(row["base_cost"])}
            for row in candidates
        ],
        "imports": {
            "GetAffixRowNames": get_rows,
            "K2_DestroyActor": destroy_actor,
            "Greater_ByteByte": greater_byte,
            "Max_IntInt": max_int,
            "WeaponAffixRarity": weapon_affix_rarity,
        },
    }
    return statements, report


def patch(
    asset: dict[str, Any],
    spec: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    patched = copy.deepcopy(asset)
    validate_asset(patched)

    fn_index, fn = find_function(patched, FUNCTION)
    statements, report = compile_block(patched, fn_index, fn, spec)

    insertion = insert_top_level_statements(fn, 2, statements)
    validate_asset(patched)

    report.update(insertion)
    report.update({
        "asset": "BP_APlayer",
        "diagnostic_only": True,
        "trigger": "existing server ping RPC on AInteractiveWeapon",
        "non_weapon_ping": "vanilla fallthrough",
        "donor_rows": "AAWeapon.GetAffixRowNames()",
        "target": "Character_Player.currentWeapon",
        "mutation": "BP_APlayer.AddEnchantedAffix",
        "debit": "RemoveTicket",
        "refund": "AddTicket",
        "consume": "K2_DestroyActor donor only after row verification",
    })
    return patched, report


def walk(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def object_name(asset: dict[str, Any], index: int) -> str | None:
    if not isinstance(index, int) or index == 0:
        return None
    seq = asset.get("Exports", []) if index > 0 else asset.get("Imports", [])
    slot = index - 1 if index > 0 else -index - 1
    if 0 <= slot < len(seq):
        return str(seq[slot].get("ObjectName"))
    return None


def verify(asset: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    validate_asset(asset)
    fn_index, fn = find_function(asset, FUNCTION)
    code = fn.get("ScriptBytecode") or []

    if len(code) < 6:
        raise PatchError("patched server ping function is unexpectedly short")

    # Original two persistent-frame assignments must remain first.
    if type_name(code[0]) != "EX_LetValueOnPersistentFrame":
        raise PatchError("ActorRef persistent-frame assignment moved")
    if type_name(code[1]) != "EX_LetValueOnPersistentFrame":
        raise PatchError("Location persistent-frame assignment moved")
    if type_name(code[2]) != "EX_Let":
        raise PatchError("ground GRAFT block is not inserted before vanilla ping dispatch")

    expected_rows = [
        str(row["row"])
        for row in spec.get("selection", {}).get("candidates") or []
    ]
    if not expected_rows:
        raise PatchError("probe spec has no candidate rows")

    loaded = {p.get("Name"): p for p in fn.get("LoadedProperties") or []}
    for name in (
        LOCAL_DONOR_INTERACTIVE,
        LOCAL_DONOR_WEAPON,
        LOCAL_DONOR_ROWS,
        LOCAL_SELECTED_ROW,
        LOCAL_BASE_COST,
        LOCAL_TARGET_ROWS,
        LOCAL_TOTAL_COST,
        LOCAL_VERIFIED,
    ):
        if name not in loaded:
            raise PatchError(f"ground GRAFT local missing: {name}")

    if loaded[LOCAL_DONOR_ROWS].get("SerializedType") != "ArrayProperty":
        raise PatchError("donor row local is not an array")
    if (loaded[LOCAL_DONOR_ROWS].get("Inner") or {}).get("SerializedType") != "NameProperty":
        raise PatchError("donor row array is not TArray<FName>")

    calls: list[str] = []
    virtuals: list[str] = []
    names: list[str] = []
    for expression in walk(code[2:]):
        t = type_name(expression)
        if t in {"EX_FinalFunction", "EX_CallMath"}:
            name = object_name(asset, expression.get("StackNode"))
            if name:
                calls.append(name)
        elif t in {"EX_LocalVirtualFunction", "EX_VirtualFunction"}:
            name = expression.get("VirtualFunctionName")
            if name:
                virtuals.append(str(name))
        elif t == "EX_NameConst":
            value = expression.get("Value")
            if isinstance(value, str):
                names.append(value)

    required_calls = {
        "GetAffixRowNames",
        "Array_Contains",
        "RemoveTicket",
        "AddTicket",
        "K2_DestroyActor",
        "Greater_ByteByte",
        "Max_IntInt",
        "GreaterEqual_IntInt",
    }
    missing = required_calls - set(calls)
    if missing:
        raise PatchError(f"ground GRAFT calls missing: {sorted(missing)}")
    if "AddEnchantedAffix" not in virtuals:
        raise PatchError("ground GRAFT does not use the existing AddEnchantedAffix chain")

    for row_id in expected_rows:
        if row_id not in names:
            raise PatchError(f"ground GRAFT candidate name missing: {row_id}")

    # The original wrapper dispatch to ExecuteUbergraph must still exist after
    # the inserted block so validation failures preserve vanilla ping behavior.
    vanilla_dispatch = [
        expression
        for expression in code
        if type_name(expression) == "EX_LocalFinalFunction"
        and object_name(asset, expression.get("StackNode")) == "ExecuteUbergraph_BP_APlayer"
    ]
    if len(vanilla_dispatch) != 1:
        raise PatchError("vanilla OnServerPingActor dispatch was not preserved exactly once")

    return {
        "verified": True,
        "asset": "BP_APlayer",
        "function": FUNCTION,
        "candidate_count": len(expected_rows),
        "candidate_rows": expected_rows,
        "authoritative_donor_rows": "AAWeapon.GetAffixRowNames()",
        "mutation": "AddEnchantedAffix",
        "currency": "RemoveTicket/AddTicket",
        "donor_consume": "K2_DestroyActor after target row verification",
        "vanilla_ping_fallthrough": True,
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
