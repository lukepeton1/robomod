#!/usr/bin/env python3
"""Add a real raycast -> projectile resolver to BP_WA_Homing.

The vanilla Homing Blueprint already:
- accepts BaseHitType Raycast or Projectile in AffectedHitTypes;
- restores HitType = BaseHitType on removal;
- exposes ProjectileSpeed and ProjectileCollisionSize custom properties;
- enables native bHomingProjectile and homing parameters.

This patch inserts, on the successful OnApply path:
- HitType = Projectile (enum byte 1);
- Speed = custom ProjectileSpeed;
- CollisionSize = custom ProjectileCollisionSize;
- GravityScale = 0.

BaseHitType is deliberately preserved, so vanilla OnRemove restores the original
hit model. Absolute Kismet flow targets are rebased through kismet_layout.py.
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


FUNCTION = "ExecuteUbergraph_BP_WA_Homing"


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def type_name(expr: Any) -> str:
    if not isinstance(expr, dict):
        return type(expr).__name__
    return str(expr.get("$type", "")).split(",", 1)[0].rsplit(".", 1)[-1]


def ensure_names(asset: dict[str, Any], names: list[str]) -> list[str]:
    name_map = asset.get("NameMap")
    if not isinstance(name_map, list):
        raise PatchError("asset has no NameMap")
    existing = set(str(x) for x in name_map)
    added = []
    for name in names:
        if name not in existing:
            name_map.append(name)
            existing.add(name)
            added.append(name)
    if added:
        asset["NamesReferencedFromExportDataCount"] = len(name_map)
    return added


def function_export(asset: dict[str, Any]) -> dict[str, Any]:
    matches = [
        x for x in asset.get("Exports", [])
        if "FunctionExport" in str(x.get("$type", ""))
        and x.get("ObjectName") == FUNCTION
    ]
    if len(matches) != 1:
        raise PatchError(f"expected one {FUNCTION}, found {len(matches)}")
    fn = matches[0]
    if not isinstance(fn.get("ScriptBytecode"), list) or fn.get("ScriptBytecodeRaw"):
        raise PatchError("Homing bytecode is not fully decoded")
    return fn


def local_path(expr: Any) -> str | None:
    if not isinstance(expr, dict):
        return None
    if type_name(expr) not in {
        "EX_LocalVariable", "EX_LocalOutVariable", "EX_InstanceVariable"
    }:
        return None
    new = (expr.get("Variable") or {}).get("New") or {}
    path = new.get("Path")
    if isinstance(path, list) and len(path) == 1:
        return str(path[0])
    return None


def find_apply_homing_statement(code: list[dict[str, Any]]) -> int:
    matches = []
    for i, expr in enumerate(code):
        if type_name(expr) != "EX_LetBool":
            continue
        var = expr.get("VariableExpression")
        if type_name(var) != "EX_Context":
            continue
        ptr = (var.get("RValuePointer") or {}).get("New") or {}
        if ptr.get("Path") == ["bHomingProjectile"]:
            rhs = expr.get("AssignmentExpression") or {}
            if type_name(rhs) == "EX_True":
                matches.append(i)
    if len(matches) != 1:
        raise PatchError(f"expected one bHomingProjectile=true assignment, found {len(matches)}")
    return matches[0]


def find_remove_hit_type_template(code: list[dict[str, Any]]) -> dict[str, Any]:
    for expr in code:
        if type_name(expr) != "EX_Let":
            continue
        var = expr.get("Variable")
        rhs = expr.get("Expression")
        if type_name(var) != "EX_Context" or type_name(rhs) != "EX_Context":
            continue
        vptr = (var.get("RValuePointer") or {}).get("New") or {}
        rptr = (rhs.get("RValuePointer") or {}).get("New") or {}
        if vptr.get("Path") == ["HitType"] and rptr.get("Path") == ["BaseHitType"]:
            return copy.deepcopy(expr)
    raise PatchError("could not find vanilla HitType = BaseHitType template")


def find_custom_get_template(code: list[dict[str, Any]]) -> dict[str, Any]:
    for expr in code:
        if type_name(expr) != "EX_Let":
            continue
        rhs = expr.get("Expression")
        if type_name(rhs) != "EX_FinalFunction":
            continue
        params = rhs.get("Parameters") or []
        if params and type_name(params[0]) == "EX_NameConst":
            if params[0].get("Value") == "HomingRange":
                return copy.deepcopy(expr)
    raise PatchError("could not find GetCustomFloatProperties template")


def find_float_assignment_template(code: list[dict[str, Any]]) -> dict[str, Any]:
    for expr in code:
        if type_name(expr) != "EX_Let":
            continue
        var = expr.get("Variable")
        rhs = expr.get("Expression")
        if type_name(var) != "EX_Context" or type_name(rhs) != "EX_LocalVariable":
            continue
        ptr = (var.get("RValuePointer") or {}).get("New") or {}
        if ptr.get("Path") == ["HomingRange"]:
            return copy.deepcopy(expr)
    raise PatchError("could not find HomingRange assignment template")


def set_context_property(expr: dict[str, Any], property_name: str) -> None:
    if type_name(expr) != "EX_Context":
        raise PatchError("target is not EX_Context")
    expr["RValuePointer"]["New"]["Path"] = [property_name]
    inner = expr.get("ContextExpression") or {}
    if type_name(inner) != "EX_InstanceVariable":
        raise PatchError("context target does not contain instance variable")
    inner["Variable"]["New"]["Path"] = [property_name]


def set_name_const(expr: dict[str, Any], value: str) -> None:
    rhs = expr.get("Expression") or {}
    params = rhs.get("Parameters") or []
    if not params or type_name(params[0]) != "EX_NameConst":
        raise PatchError("custom float getter template shape changed")
    params[0]["Value"] = value


def set_context_object_local(expr: dict[str, Any], local_name: str) -> None:
    if type_name(expr) != "EX_Context":
        raise PatchError("target is not EX_Context")
    obj = expr.get("ObjectExpression") or {}
    if type_name(obj) != "EX_LocalVariable":
        raise PatchError("context object is not a local variable")
    new = (obj.get("Variable") or {}).get("New") or {}
    path = new.get("Path")
    if not isinstance(path, list) or len(path) != 1:
        raise PatchError("context object local path shape changed")
    new["Path"] = [local_name]


def make_hit_type_assignment(template: dict[str, Any]) -> dict[str, Any]:
    expr = copy.deepcopy(template)
    # Vanilla OnRemove uses K2Node_DynamicCast_AsAPlayer_Skill, while OnApply
    # uses the separate _1 local. Retarget the cloned l-value to the apply local.
    set_context_object_local(
        expr["Variable"],
        "K2Node_DynamicCast_AsAPlayer_Skill_1",
    )
    expr["Expression"] = {
        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_ByteConst, UAssetAPI",
        "Value": 1,
    }
    return expr


def make_custom_assignment(
    get_template: dict[str, Any],
    set_template: dict[str, Any],
    custom_name: str,
    target_property: str,
) -> list[dict[str, Any]]:
    getter = copy.deepcopy(get_template)
    setter = copy.deepcopy(set_template)
    set_name_const(getter, custom_name)
    set_context_property(setter["Variable"], target_property)
    return [getter, setter]


def make_gravity_assignment(set_template: dict[str, Any]) -> dict[str, Any]:
    setter = copy.deepcopy(set_template)
    set_context_property(setter["Variable"], "GravityScale")
    setter["Expression"] = {
        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_FloatConst, UAssetAPI",
        "Value": 0.0,
    }
    return setter


def patch(asset: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    patched = copy.deepcopy(asset)
    validate_asset(patched)
    added_names = ensure_names(
        patched,
        ["Speed", "CollisionSize", "GravityScale", "ProjectileSpeed", "ProjectileCollisionSize"],
    )

    fn = function_export(patched)
    code = fn["ScriptBytecode"]
    insertion_index = find_apply_homing_statement(code)

    hit_template = find_remove_hit_type_template(code)
    get_template = find_custom_get_template(code)
    set_template = find_float_assignment_template(code)

    statements = [make_hit_type_assignment(hit_template)]
    statements += make_custom_assignment(
        get_template, set_template, "ProjectileSpeed", "Speed"
    )
    statements += make_custom_assignment(
        get_template, set_template, "ProjectileCollisionSize", "CollisionSize"
    )
    statements.append(make_gravity_assignment(set_template))

    report = insert_top_level_statements(fn, insertion_index, statements)
    validate_asset(patched)
    report.update({
        "asset": "BP_WA_Homing",
        "function": FUNCTION,
        "resolver": "Raycast/Projectile -> live Projectile while Homing is applied",
        "projectile_enum_byte": 1,
        "name_map_added": added_names,
        "inserted_semantics": [
            "HitType = Projectile",
            "Speed = CustomFloat(ProjectileSpeed)",
            "CollisionSize = CustomFloat(ProjectileCollisionSize)",
            "GravityScale = 0",
        ],
        "remove_semantics": "vanilla OnRemove restores HitType = BaseHitType",
    })
    return patched, report


def _context_path(expr: Any) -> str | None:
    if type_name(expr) != "EX_Context":
        return None
    ptr = (expr.get("RValuePointer") or {}).get("New") or {}
    path = ptr.get("Path")
    return str(path[0]) if isinstance(path, list) and len(path) == 1 else None


def verify(asset: dict[str, Any]) -> dict[str, Any]:
    validate_asset(asset)
    fn = function_export(asset)
    code = fn["ScriptBytecode"]
    apply_index = find_apply_homing_statement(code)

    prior = code[max(0, apply_index - 8):apply_index]
    targets = []
    custom_names = []
    projectile_assignment = False
    projectile_assignment_uses_apply_local = False
    gravity_zero = False

    for expr in prior:
        if type_name(expr) != "EX_Let":
            continue
        var = expr.get("Variable")
        rhs = expr.get("Expression")
        target = _context_path(var)
        if target:
            targets.append(target)
        if target == "HitType" and type_name(rhs) == "EX_ByteConst" and rhs.get("Value") == 1:
            projectile_assignment = True
            obj = (var.get("ObjectExpression") or {})
            projectile_assignment_uses_apply_local = (
                local_path(obj) == "K2Node_DynamicCast_AsAPlayer_Skill_1"
            )
        if target == "GravityScale" and type_name(rhs) == "EX_FloatConst" and float(rhs.get("Value", 1)) == 0.0:
            gravity_zero = True

        if type_name(rhs) == "EX_FinalFunction":
            params = rhs.get("Parameters") or []
            if params and type_name(params[0]) == "EX_NameConst":
                custom_names.append(params[0].get("Value"))

    required_targets = {"HitType", "Speed", "CollisionSize", "GravityScale"}
    if not required_targets.issubset(set(targets)):
        raise PatchError(f"resolver target assignments missing: {required_targets - set(targets)}")
    if not {"ProjectileSpeed", "ProjectileCollisionSize"}.issubset(set(custom_names)):
        raise PatchError("resolver custom property lookups missing")
    if not projectile_assignment:
        raise PatchError("resolver does not assign HitType byte 1")
    if not projectile_assignment_uses_apply_local:
        raise PatchError("resolver HitType assignment does not use the OnApply skill local")
    if not gravity_zero:
        raise PatchError("resolver does not assign GravityScale=0")

    return {
        "verified": True,
        "asset": "BP_WA_Homing",
        "function": FUNCTION,
        "script_bytecode_size": fn.get("ScriptBytecodeSize"),
        "apply_homing_statement_index": apply_index,
        "targets": sorted(required_targets),
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
