#!/usr/bin/env python3
"""Patch BP_WA_Fragmentation using same-shape Kismet substitutions.

Every edit preserves the decoded expression topology and parameter cardinality. The
patch therefore does not insert/remove bytecode instructions and does not require
rebasing UE4 absolute execution-flow offsets.

Verified target: Roboquest UE4.26 cooked BP_WA_Fragmentation.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any


class PatchError(RuntimeError):
    pass


FUNCTION = "ExecuteUbergraph_BP_WA_Fragmentation"


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def type_name(value: Any) -> str:
    if not isinstance(value, dict):
        return type(value).__name__
    raw = str(value.get("$type", ""))
    return raw.rsplit(".", 1)[-1].split(",", 1)[0]


def package_object(asset: dict[str, Any], index: int) -> dict[str, Any] | None:
    if not isinstance(index, int) or index == 0:
        return None
    seq = asset.get("Exports", []) if index > 0 else asset.get("Imports", [])
    slot = index - 1 if index > 0 else -index - 1
    return seq[slot] if 0 <= slot < len(seq) else None


def import_index(asset: dict[str, Any], object_name: str) -> int:
    matches = [
        -i
        for i, entry in enumerate(asset.get("Imports", []), start=1)
        if entry.get("ObjectName") == object_name
    ]
    if len(matches) != 1:
        raise PatchError(
            f"expected exactly one import named {object_name!r}, found {len(matches)}"
        )
    return matches[0]


def local_path(expr: Any) -> str | None:
    if not isinstance(expr, dict):
        return None
    if type_name(expr) not in {"EX_LocalVariable", "EX_LocalOutVariable", "EX_InstanceVariable"}:
        return None
    new = (expr.get("Variable") or {}).get("New") or {}
    path = new.get("Path")
    if isinstance(path, list) and len(path) == 1:
        return str(path[0])
    return None


def set_local_path(expr: dict[str, Any], name: str) -> None:
    if local_path(expr) is None:
        raise PatchError("expression is not a one-component local/instance variable")
    expr["Variable"]["New"]["Path"] = [name]


def structural_shape(value: Any) -> Any:
    """Fingerprint serialization topology while ignoring scalar values/indexes."""
    if isinstance(value, dict):
        return {
            key: structural_shape(child) if isinstance(child, (dict, list)) else type(child).__name__
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [structural_shape(child) for child in value]
    return type(value).__name__


def function_export(asset: dict[str, Any]) -> dict[str, Any]:
    matches = [
        x for x in asset.get("Exports", [])
        if "FunctionExport" in str(x.get("$type", ""))
        and x.get("ObjectName") == FUNCTION
    ]
    if len(matches) != 1:
        raise PatchError(f"expected exactly one {FUNCTION}, found {len(matches)}")
    fn = matches[0]
    if not isinstance(fn.get("ScriptBytecode"), list) or fn.get("ScriptBytecodeRaw"):
        raise PatchError("Fragmentation function does not have fully decoded ScriptBytecode")
    return fn


def find_bool_assignment(code: list[dict[str, Any]], local_name: str) -> tuple[int, dict[str, Any]]:
    matches = [
        (i, expr)
        for i, expr in enumerate(code)
        if type_name(expr) == "EX_LetBool"
        and local_path(expr.get("VariableExpression")) == local_name
    ]
    if len(matches) != 1:
        raise PatchError(
            f"expected one EX_LetBool assignment to {local_name}, found {len(matches)}"
        )
    return matches[0]


def find_child_gameplay_tag_copy(code: list[dict[str, Any]]) -> tuple[int, dict[str, Any]]:
    matches: list[tuple[int, dict[str, Any]]] = []
    for i, expr in enumerate(code):
        if type_name(expr) != "EX_Let":
            continue
        variable = expr.get("Variable")
        source = expr.get("Expression")
        if type_name(variable) != "EX_Context" or type_name(source) != "EX_Context":
            continue
        if local_path(variable.get("ObjectExpression")) != "CallFunc_Array_Get_Item_2":
            continue
        dst_path = ((variable.get("RValuePointer") or {}).get("New") or {}).get("Path")
        if dst_path == ["GameplayTags"]:
            matches.append((i, expr))
    if len(matches) != 1:
        raise PatchError(
            f"expected one child GameplayTags assignment, found {len(matches)}"
        )
    return matches[0]


def patch(asset: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    patched = copy.deepcopy(asset)
    fn = function_export(patched)
    code = fn["ScriptBytecode"]
    function_shape_before = structural_shape(code)
    bytecode_size_before = fn.get("ScriptBytecodeSize")

    less_equal_int = import_index(patched, "LessEqual_IntInt")
    a_skill = import_index(patched, "ASkill")

    changes: list[dict[str, Any]] = []

    # 1) Universalize the Fragmentation gameplay-tag gate without changing bytecode
    # shape. The original boolean local is assigned:
    #   CheckFlagToBitmask(MakeLiteralByte(0), GameplayTags)
    # Replace the call with:
    #   LessEqual_IntInt(GameplayTags, GameplayTags)
    # which is deterministically true for every int while retaining EX_CallMath and
    # two EX_LocalVariable parameters of identical serialized shape.
    index, gate = find_bool_assignment(code, "CallFunc_CheckFlagToBitmask_ReturnValue")
    assignment = gate.get("AssignmentExpression")
    if type_name(assignment) != "EX_CallMath":
        raise PatchError("Fragmentation tag gate is no longer an EX_CallMath")
    old_node = assignment.get("StackNode")
    old_import = package_object(patched, old_node) if isinstance(old_node, int) else None
    if not old_import or old_import.get("ObjectName") != "CheckFlagToBitmask":
        raise PatchError(
            f"Fragmentation tag gate call changed; expected CheckFlagToBitmask, got {old_import}"
        )
    params = assignment.get("Parameters")
    if not isinstance(params, list) or len(params) != 2:
        raise PatchError("CheckFlagToBitmask call no longer has two parameters")
    if local_path(params[1]) != "CallFunc_GetGameplayTags_ReturnValue":
        raise PatchError("Fragmentation tag gate second parameter is no longer GameplayTags")

    statement_shape = structural_shape(gate)
    assignment["StackNode"] = less_equal_int
    assignment["Parameters"][0] = copy.deepcopy(assignment["Parameters"][1])
    if structural_shape(gate) != statement_shape:
        raise PatchError("universal gate substitution changed Kismet expression topology")
    changes.append({
        "statement_index": index,
        "change": "universal_fragmentation_gate",
        "from": "CheckFlagToBitmask(tag_0, GameplayTags)",
        "to": "LessEqual_IntInt(GameplayTags, GameplayTags)",
        "same_shape": True,
    })

    # 2) Vanilla copies GameplayTags to spawned fragments only when the *source*
    # projectile exists. For raycast-origin attacks source projectile is null. The
    # spawned fragment itself must be valid, so retarget that IsValid call to the
    # current spawned child while keeping EX_CallMath + one EX_LocalVariable.
    index, validity = find_bool_assignment(code, "CallFunc_IsValid_ReturnValue_1")
    assignment = validity.get("AssignmentExpression")
    if type_name(assignment) != "EX_CallMath":
        raise PatchError("child tag-copy validity check is no longer EX_CallMath")
    old_node = assignment.get("StackNode")
    old_import = package_object(patched, old_node) if isinstance(old_node, int) else None
    if not old_import or old_import.get("ObjectName") != "IsValid":
        raise PatchError("child tag-copy validity check no longer calls IsValid")
    params = assignment.get("Parameters")
    if not isinstance(params, list) or len(params) != 1:
        raise PatchError("child tag-copy IsValid call no longer has one parameter")
    if local_path(params[0]) != "K2Node_CustomEvent_Projectile":
        raise PatchError("child tag-copy validity source is no longer the source projectile")

    statement_shape = structural_shape(validity)
    set_local_path(params[0], "CallFunc_Array_Get_Item_2")
    if structural_shape(validity) != statement_shape:
        raise PatchError("child validity substitution changed Kismet expression topology")
    changes.append({
        "statement_index": index,
        "change": "validate_spawned_fragment_for_tag_copy",
        "from": "IsValid(source projectile)",
        "to": "IsValid(spawned fragment)",
        "same_shape": True,
    })

    # 3) Copy the originating ASkill GameplayTags into every spawned fragment instead
    # of reading AProjectile.GameplayTags. GetGameplayTags() already proves ASkill has
    # the same integer property. This also keeps the source Context expression topology
    # byte-for-byte shaped: one local object + one instance-property context.
    index, tag_copy = find_child_gameplay_tag_copy(code)
    source = tag_copy["Expression"]
    if local_path(source.get("ObjectExpression")) != "K2Node_CustomEvent_Projectile":
        raise PatchError("fragment GameplayTags source is no longer source projectile")
    source_rvalue = (source.get("RValuePointer") or {}).get("New") or {}
    source_context = (((source.get("ContextExpression") or {}).get("Variable") or {}).get("New") or {})
    if source_rvalue.get("Path") != ["GameplayTags"] or source_context.get("Path") != ["GameplayTags"]:
        raise PatchError("fragment GameplayTags source property has changed")

    statement_shape = structural_shape(tag_copy)
    set_local_path(source["ObjectExpression"], "K2Node_CustomEvent_Skill")
    source["RValuePointer"]["New"]["ResolvedOwner"] = a_skill
    source["ContextExpression"]["Variable"]["New"]["ResolvedOwner"] = a_skill
    if structural_shape(tag_copy) != statement_shape:
        raise PatchError("GameplayTags source substitution changed Kismet expression topology")
    changes.append({
        "statement_index": index,
        "change": "inherit_skill_gameplay_tags",
        "from": "source AProjectile.GameplayTags",
        "to": "source ASkill.GameplayTags",
        "same_shape": True,
    })

    if structural_shape(code) != function_shape_before:
        raise PatchError("Fragmentation patch changed overall ScriptBytecode topology")
    if fn.get("ScriptBytecodeSize") != bytecode_size_before:
        raise PatchError("Fragmentation patch changed declared ScriptBytecodeSize")

    report = {
        "asset": "BP_WA_Fragmentation",
        "function": FUNCTION,
        "declared_script_bytecode_size": bytecode_size_before,
        "statement_count": len(code),
        "same_shape_only": True,
        "absolute_flow_offsets_modified": False,
        "changes": changes,
    }
    return patched, report


def verify(asset: dict[str, Any]) -> dict[str, Any]:
    fn = function_export(asset)
    code = fn["ScriptBytecode"]
    less_equal_int = import_index(asset, "LessEqual_IntInt")
    a_skill = import_index(asset, "ASkill")

    _, gate = find_bool_assignment(code, "CallFunc_CheckFlagToBitmask_ReturnValue")
    assignment = gate["AssignmentExpression"]
    gate_ok = (
        type_name(assignment) == "EX_CallMath"
        and assignment.get("StackNode") == less_equal_int
        and len(assignment.get("Parameters") or []) == 2
        and all(
            local_path(x) == "CallFunc_GetGameplayTags_ReturnValue"
            for x in assignment.get("Parameters") or []
        )
    )

    _, validity = find_bool_assignment(code, "CallFunc_IsValid_ReturnValue_1")
    vparams = (validity.get("AssignmentExpression") or {}).get("Parameters") or []
    validity_ok = len(vparams) == 1 and local_path(vparams[0]) == "CallFunc_Array_Get_Item_2"

    _, tag_copy = find_child_gameplay_tag_copy(code)
    source = tag_copy["Expression"]
    tag_copy_ok = (
        local_path(source.get("ObjectExpression")) == "K2Node_CustomEvent_Skill"
        and ((source.get("RValuePointer") or {}).get("New") or {}).get("ResolvedOwner") == a_skill
        and ((((source.get("ContextExpression") or {}).get("Variable") or {}).get("New") or {}).get("ResolvedOwner")) == a_skill
    )

    checks = {
        "universal_gate": gate_ok,
        "spawned_fragment_validity": validity_ok,
        "skill_gameplay_tag_inheritance": tag_copy_ok,
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise PatchError(f"Fragmentation bytecode verification failed: {failed}")

    return {
        "verified": True,
        "asset": "BP_WA_Fragmentation",
        "function": FUNCTION,
        "declared_script_bytecode_size": fn.get("ScriptBytecodeSize"),
        "checks": checks,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("input_json", type=Path)
    ap.add_argument("output_json", type=Path, nargs="?")
    ap.add_argument("--report", type=Path)
    ap.add_argument("--verify-only", action="store_true")
    args = ap.parse_args()

    asset = load(args.input_json)

    if args.verify_only:
        result = verify(asset)
        print(json.dumps(result, indent=2))
        return 0

    if args.output_json is None:
        raise SystemExit("output_json is required unless --verify-only is used")

    patched, report = patch(asset)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(patched, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
