#!/usr/bin/env python3
"""UE4.26 Kismet byte-size and absolute-flow-offset utilities for UAssetAPI JSON.

The sizing model is derived from UAssetAPI's KismetSerializer and was validated
against every decoded FunctionExport in the Weapon Foundry legacy handoff.

Scope:
- exact serialized expression sizes for the UE4.26 expression forms currently
  observed in Roboquest;
- script-size validation against ScriptBytecodeSize;
- safe rebasing of *absolute* flow targets after a top-level insertion;
- top-level statement insertion without hand-editing every jump target.

Context skip offsets are relative to their own expression and are intentionally
not modified by a top-level insertion.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any


class KismetLayoutError(RuntimeError):
    pass


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def type_name(expr: Any) -> str:
    if not isinstance(expr, dict):
        return type(expr).__name__
    raw = str(expr.get("$type", ""))
    return raw.split(",", 1)[0].rsplit(".", 1)[-1]


def _string_expr_size(expr: dict[str, Any]) -> int:
    return expression_size(expr)


def expression_size(expr: dict[str, Any]) -> int:
    if not isinstance(expr, dict):
        raise KismetLayoutError(f"expected Kismet expression object, got {type(expr).__name__}")

    t = type_name(expr)
    b = 1  # opcode

    if t == "EX_PrimitiveCast":
        conv = expr.get("ConversionType") or expr.get("CastType")
        return b + 1 + (8 if str(conv).endswith("ObjectToInterface") else 0) + expression_size(expr["Target"])
    if t == "EX_SetSet":
        return b + expression_size(expr["SetProperty"]) + 4 + sum(expression_size(x) for x in expr.get("Elements", [])) + 1
    if t == "EX_SetConst":
        return b + 8 + 4 + sum(expression_size(x) for x in expr.get("Elements", [])) + 1
    if t == "EX_SetMap":
        return b + expression_size(expr["MapProperty"]) + 4 + sum(expression_size(x) for x in expr.get("Elements", [])) + 1
    if t == "EX_MapConst":
        return b + 8 + 4 + sum(expression_size(x) for x in expr.get("Elements", [])) + 1
    if t in {"EX_ObjToInterfaceCast", "EX_CrossInterfaceCast", "EX_InterfaceToObjCast"}:
        return b + 8 + expression_size(expr["Target"])
    if t == "EX_Let":
        return b + 8 + expression_size(expr["Variable"]) + expression_size(expr["Expression"])
    if t in {"EX_LetObj", "EX_LetWeakObjPtr", "EX_LetBool", "EX_LetDelegate", "EX_LetMulticastDelegate"}:
        return b + expression_size(expr["VariableExpression"]) + expression_size(expr["AssignmentExpression"])
    if t == "EX_LetValueOnPersistentFrame":
        return b + 8 + expression_size(expr["AssignmentExpression"])
    if t == "EX_StructMemberContext":
        return b + 8 + expression_size(expr["StructExpression"])
    if t == "EX_LocalVirtualFunction":
        return b + 12 + sum(expression_size(x) for x in expr.get("Parameters", [])) + 1
    if t == "EX_LocalFinalFunction":
        return b + 8 + sum(expression_size(x) for x in expr.get("Parameters", [])) + 1
    if t == "EX_ComputedJump":
        return b + expression_size(expr["CodeOffsetExpression"])
    if t == "EX_Jump":
        return b + 4
    if t in {"EX_LocalVariable", "EX_DefaultVariable", "EX_InstanceVariable", "EX_LocalOutVariable"}:
        return b + 8
    if t == "EX_InterfaceContext":
        return b + expression_size(expr["InterfaceValue"])
    if t in {
        "EX_DeprecatedOp4A", "EX_Nothing", "EX_EndOfScript", "EX_IntZero",
        "EX_IntOne", "EX_True", "EX_False", "EX_NoObject", "EX_NoInterface",
        "EX_Self", "EX_PopExecutionFlow", "EX_Breakpoint", "EX_WireTracepoint",
        "EX_Tracepoint",
    }:
        return b
    if t == "EX_Return":
        return b + expression_size(expr["ReturnExpression"])
    if t in {"EX_CallMath", "EX_FinalFunction"}:
        return b + 8 + sum(expression_size(x) for x in expr.get("Parameters", [])) + 1
    if t == "EX_CallMulticastDelegate":
        return b + 8 + expression_size(expr["Delegate"]) + sum(expression_size(x) for x in expr.get("Parameters", [])) + 1
    if t == "EX_VirtualFunction":
        return b + 12 + sum(expression_size(x) for x in expr.get("Parameters", [])) + 1
    if t in {"EX_Context", "EX_ClassContext"}:
        return b + expression_size(expr["ObjectExpression"]) + 4 + 8 + expression_size(expr["ContextExpression"])
    if t in {"EX_IntConst", "EX_SkipOffsetConst", "EX_FloatConst"}:
        return b + 4
    if t == "EX_DoubleConst":
        return b + 8
    if t == "EX_StringConst":
        return b + len(str(expr.get("Value", ""))) + 1
    if t == "EX_UnicodeStringConst":
        return b + 2 * (len(str(expr.get("Value", ""))) + 1)
    if t == "EX_TextConst":
        value = expr["Value"]
        kind = value.get("TextLiteralType")
        total = b + 1
        if kind == "LocalizedText":
            total += _string_expr_size(value["LocalizedSource"])
            total += _string_expr_size(value["LocalizedKey"])
            total += _string_expr_size(value["LocalizedNamespace"])
        elif kind == "InvariantText":
            total += _string_expr_size(value["InvariantLiteralString"])
        elif kind == "LiteralString":
            total += _string_expr_size(value["LiteralString"])
        elif kind == "StringTableEntry":
            total += 8
            total += _string_expr_size(value["StringTableId"])
            total += _string_expr_size(value["StringTableKey"])
        elif kind != "Empty":
            raise KismetLayoutError(f"unsupported text literal type {kind!r}")
        return total
    if t == "EX_ObjectConst":
        return b + 8
    if t == "EX_SoftObjectConst":
        return b + expression_size(expr["Value"])
    if t == "EX_NameConst":
        return b + 12
    if t in {"EX_RotationConst", "EX_VectorConst"}:
        return b + 12  # UE4.26 floats, not UE5 large-world doubles
    if t == "EX_TransformConst":
        return b + 40
    if t == "EX_StructConst":
        values = expr.get("Value", expr.get("Properties", []))
        if isinstance(values, dict):
            values = list(values.values())
        flat = []
        for item in values:
            flat.extend(item if isinstance(item, list) else [item])
        return b + 8 + 4 + sum(expression_size(x) for x in flat) + 1
    if t == "EX_SetArray":
        return b + expression_size(expr["AssigningProperty"]) + sum(expression_size(x) for x in expr.get("Elements", [])) + 1
    if t == "EX_ArrayConst":
        return b + 8 + 4 + sum(expression_size(x) for x in expr.get("Elements", [])) + 1
    if t in {"EX_ByteConst", "EX_IntConstByte"}:
        return b + 1
    if t in {"EX_Int64Const", "EX_UInt64Const"}:
        return b + 8
    if t == "EX_FieldPathConst":
        return b + expression_size(expr["Value"])
    if t in {"EX_MetaCast", "EX_DynamicCast"}:
        return b + 8 + expression_size(expr["Target"])
    if t == "EX_JumpIfNot":
        return b + 4 + expression_size(expr["BooleanExpression"])
    if t == "EX_Assert":
        return b + 3 + expression_size(expr["AssertExpression"])
    if t == "EX_InstanceDelegate":
        return b + 12
    if t in {"EX_AddMulticastDelegate", "EX_RemoveMulticastDelegate"}:
        return b + expression_size(expr["Delegate"]) + expression_size(expr["DelegateToAdd"])
    if t == "EX_ClearMulticastDelegate":
        return b + expression_size(expr["DelegateToClear"])
    if t == "EX_BindDelegate":
        return b + 12 + expression_size(expr["Delegate"]) + expression_size(expr["ObjectTerm"])
    if t == "EX_PushExecutionFlow":
        return b + 4
    if t == "EX_PopExecutionFlowIfNot":
        return b + expression_size(expr["BooleanExpression"])
    if t == "EX_InstrumentationEvent":
        return b + 1 + (12 if expr.get("EventType") == "InlineEvent" else 0)
    if t == "EX_SwitchValue":
        cases = expr.get("Cases", [])
        return (
            b + 6 + expression_size(expr["IndexTerm"])
            + sum(
                expression_size(case["CaseIndexValueTerm"]) + 4 + expression_size(case["CaseTerm"])
                for case in cases
            )
            + expression_size(expr["DefaultTerm"])
        )
    if t == "EX_ArrayGetByRef":
        return b + expression_size(expr["ArrayVariable"]) + expression_size(expr["ArrayIndex"])

    raise KismetLayoutError(f"unsupported Kismet expression type {t}")


def script_size(code: list[dict[str, Any]]) -> int:
    return sum(expression_size(expr) for expr in code)


def top_level_offsets(code: list[dict[str, Any]]) -> tuple[list[int], int]:
    offsets = []
    offset = 0
    for expr in code:
        offsets.append(offset)
        offset += expression_size(expr)
    return offsets, offset


def walk(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def rebase_absolute_flow_offsets(value: Any, threshold: int, delta: int) -> int:
    """Shift absolute Kismet destinations at/after threshold.

    This deliberately does not touch EX_Context.Offset because that is a relative
    skip length local to the context expression.
    """
    changed = 0
    for node in walk(value):
        if not isinstance(node, dict):
            continue
        t = type_name(node)
        if t in {"EX_Jump", "EX_JumpIfNot"}:
            key = "CodeOffset"
            if isinstance(node.get(key), int) and node[key] >= threshold:
                node[key] += delta
                changed += 1
        elif t == "EX_PushExecutionFlow":
            key = "PushingAddress"
            if isinstance(node.get(key), int) and node[key] >= threshold:
                node[key] += delta
                changed += 1
        elif t == "EX_SkipOffsetConst":
            key = "Value"
            if isinstance(node.get(key), int) and node[key] >= threshold:
                node[key] += delta
                changed += 1
        elif t == "EX_SwitchValue":
            if isinstance(node.get("EndGotoOffset"), int) and node["EndGotoOffset"] >= threshold:
                node["EndGotoOffset"] += delta
                changed += 1
            for case in node.get("Cases", []):
                if isinstance(case, dict) and isinstance(case.get("NextOffset"), int) and case["NextOffset"] >= threshold:
                    case["NextOffset"] += delta
                    changed += 1
    return changed


def insert_top_level_statements(
    function_export: dict[str, Any],
    statement_index: int,
    statements: list[dict[str, Any]],
) -> dict[str, Any]:
    code = function_export.get("ScriptBytecode")
    if not isinstance(code, list):
        raise KismetLayoutError("function has no decoded ScriptBytecode")
    if function_export.get("ScriptBytecodeRaw"):
        raise KismetLayoutError("function contains raw bytecode fallback")
    if statement_index < 0 or statement_index > len(code):
        raise KismetLayoutError(f"statement index out of range: {statement_index}")

    offsets, old_size = top_level_offsets(code)
    declared = function_export.get("ScriptBytecodeSize")
    if declared != old_size:
        raise KismetLayoutError(f"declared ScriptBytecodeSize {declared} != calculated {old_size}")

    insertion_offset = old_size if statement_index == len(code) else offsets[statement_index]
    delta = script_size(statements)
    changed_targets = rebase_absolute_flow_offsets(code, insertion_offset, delta)

    code[statement_index:statement_index] = copy.deepcopy(statements)
    new_size = script_size(code)
    if new_size != old_size + delta:
        raise KismetLayoutError("post-insertion script size is inconsistent")
    function_export["ScriptBytecodeSize"] = new_size

    return {
        "statement_index": statement_index,
        "insertion_offset": insertion_offset,
        "inserted_statement_count": len(statements),
        "inserted_byte_count": delta,
        "old_script_size": old_size,
        "new_script_size": new_size,
        "rebased_absolute_targets": changed_targets,
    }


def function_exports(asset: dict[str, Any]):
    return [
        exp for exp in asset.get("Exports", [])
        if "FunctionExport" in str(exp.get("$type", ""))
    ]


def validate_asset(asset: dict[str, Any]) -> dict[str, Any]:
    checked = 0
    errors = []
    for fn in function_exports(asset):
        code = fn.get("ScriptBytecode")
        if not isinstance(code, list):
            continue
        checked += 1
        try:
            calculated = script_size(code)
        except Exception as exc:
            errors.append({"function": fn.get("ObjectName"), "error": str(exc)})
            continue
        declared = fn.get("ScriptBytecodeSize")
        if calculated != declared:
            errors.append({
                "function": fn.get("ObjectName"),
                "declared": declared,
                "calculated": calculated,
                "delta": calculated - declared,
            })
    if errors:
        raise KismetLayoutError(json.dumps(errors, indent=2))
    return {"verified": True, "functions_checked": checked}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("asset_json", type=Path)
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--summary", action="store_true")
    args = ap.parse_args()

    asset = load(args.asset_json)
    result = validate_asset(asset)
    if args.summary:
        rows = []
        for fn in function_exports(asset):
            code = fn.get("ScriptBytecode")
            if isinstance(code, list):
                rows.append({
                    "function": fn.get("ObjectName"),
                    "statement_count": len(code),
                    "script_bytecode_size": fn.get("ScriptBytecodeSize"),
                    "calculated_size": script_size(code),
                })
        result["functions"] = rows
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
