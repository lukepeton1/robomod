#!/usr/bin/env python3
"""Readable disassembly helpers for UAssetAPI JSON Kismet bytecode.

This is intentionally dependency-free. It does not attempt to recompile bytecode; it
resolves UAsset package indexes and prints the decoded expressions that UAssetAPI
already produced. The output is designed for reverse-engineering and review.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable


def load_asset(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


class PackageResolver:
    def __init__(self, asset: dict[str, Any]):
        self.asset = asset
        self.exports = asset.get("Exports", [])
        self.imports = asset.get("Imports", [])

    def object(self, index: int) -> dict[str, Any] | None:
        if not isinstance(index, int) or index == 0:
            return None
        seq = self.exports if index > 0 else self.imports
        slot = index - 1 if index > 0 else -index - 1
        return seq[slot] if 0 <= slot < len(seq) else None

    def name(self, index: int) -> str:
        obj = self.object(index)
        if not obj:
            return f"<index:{index}>"
        return str(obj.get("ObjectName") or f"<index:{index}>")

    def full_name(self, index: int) -> str:
        obj = self.object(index)
        if not obj:
            return f"<index:{index}>"
        name = str(obj.get("ObjectName") or f"<index:{index}>")
        outer = obj.get("OuterIndex", 0)
        if isinstance(outer, int) and outer:
            return f"{self.full_name(outer)}.{name}"
        return name


def short_type(expr: dict[str, Any]) -> str:
    t = str(expr.get("$type", ""))
    if "." in t:
        t = t.rsplit(".", 1)[-1]
    return t.split(",", 1)[0]


def property_pointer(pointer: Any, r: PackageResolver) -> str:
    if not isinstance(pointer, dict):
        return str(pointer)
    new = pointer.get("New")
    if isinstance(new, dict):
        path = new.get("Path") or []
        owner = new.get("ResolvedOwner")
        name = ".".join(str(x) for x in path) if path else "<unnamed>"
        if isinstance(owner, int) and owner:
            return f"{r.name(owner)}::{name}"
        return name
    old = pointer.get("Old")
    if isinstance(old, int):
        return r.full_name(old)
    return "<property>"


def scalar(expr: dict[str, Any], r: PackageResolver) -> str | None:
    t = short_type(expr)
    if t in {"EX_IntConst", "EX_IntConstByte", "EX_ByteConst", "EX_Int64Const", "EX_UInt64Const",
             "EX_FloatConst", "EX_DoubleConst", "EX_StringConst", "EX_UnicodeStringConst",
             "EX_NameConst"}:
        return repr(expr.get("Value"))
    if t == "EX_True":
        return "true"
    if t == "EX_False":
        return "false"
    if t == "EX_Nothing":
        return "nothing"
    if t == "EX_Self":
        return "self"
    if t == "EX_ObjectConst":
        return r.full_name(int(expr.get("Value", 0)))
    if t in {"EX_LocalVariable", "EX_InstanceVariable", "EX_DefaultVariable"}:
        return property_pointer(expr.get("Variable"), r)
    return None


def inline(expr: Any, r: PackageResolver, depth: int = 0) -> str:
    if not isinstance(expr, dict):
        return repr(expr)
    s = scalar(expr, r)
    if s is not None:
        return s
    if depth >= 4:
        return short_type(expr)

    t = short_type(expr)
    if t in {"EX_FinalFunction", "EX_CallMath", "EX_LocalFinalFunction", "EX_LocalVirtualFunction",
             "EX_VirtualFunction"}:
        node = expr.get("StackNode")
        fn = r.full_name(node) if isinstance(node, int) else str(expr.get("VirtualFunctionName") or t)
        params = ", ".join(inline(x, r, depth + 1) for x in expr.get("Parameters", []))
        return f"{fn}({params})"
    if t in {"EX_Context", "EX_ClassContext"}:
        return f"{inline(expr.get('ObjectExpression'), r, depth+1)}.{inline(expr.get('ContextExpression'), r, depth+1)}"
    if t.startswith("EX_Let"):
        var = expr.get("Variable") or expr.get("VariableExpression")
        val = expr.get("Expression") or expr.get("AssignmentExpression")
        return f"{inline(var, r, depth+1)} = {inline(val, r, depth+1)}"
    if t == "EX_JumpIfNot":
        return f"if_not {inline(expr.get('BooleanExpression'), r, depth+1)} -> {expr.get('CodeOffset')}"
    if t == "EX_Jump":
        return f"jump -> {expr.get('CodeOffset')}"
    if t == "EX_PushExecutionFlow":
        return f"push_flow -> {expr.get('PushingAddress')}"
    if t == "EX_ComputedJump":
        return f"computed_jump {inline(expr.get('CodeOffsetExpression'), r, depth+1)}"
    if t == "EX_DynamicCast":
        cls = expr.get("ClassPtr")
        return f"cast<{r.full_name(cls) if isinstance(cls, int) else cls}>({inline(expr.get('Target'), r, depth+1)})"
    return t


def walk(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        if "$type" in value and "UAssetAPI.Kismet" in str(value["$type"]):
            yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def function_exports(asset: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        x for x in asset.get("Exports", [])
        if "FunctionExport" in str(x.get("$type", ""))
    ]


def function_summary(fn: dict[str, Any], r: PackageResolver) -> dict[str, Any]:
    bytecode = fn.get("ScriptBytecode")
    calls: set[str] = set()
    names: set[str] = set()
    jumps: list[dict[str, Any]] = []

    for expr in walk(bytecode or []):
        t = short_type(expr)
        node = expr.get("StackNode")
        if isinstance(node, int):
            calls.add(r.full_name(node))
        if t == "EX_NameConst":
            names.add(str(expr.get("Value")))
        if t == "EX_JumpIfNot":
            jumps.append({"type": t, "offset": expr.get("CodeOffset")})
        elif t == "EX_Jump":
            jumps.append({"type": t, "offset": expr.get("CodeOffset")})
        elif t == "EX_PushExecutionFlow":
            jumps.append({"type": t, "offset": expr.get("PushingAddress")})

    return {
        "name": fn.get("ObjectName"),
        "script_bytecode_size": fn.get("ScriptBytecodeSize"),
        "statement_count": len(bytecode or []),
        "raw_bytecode_bytes": len(fn.get("ScriptBytecodeRaw") or []),
        "calls": sorted(calls),
        "name_constants": sorted(names),
        "absolute_flow_offsets": jumps,
    }


def render_function(fn: dict[str, Any], r: PackageResolver, start: int = 0, end: int | None = None) -> str:
    code = fn.get("ScriptBytecode") or []
    if end is None:
        end = len(code)
    lines = [
        f"Function: {fn.get('ObjectName')}",
        f"ScriptBytecodeSize: {fn.get('ScriptBytecodeSize')}",
        f"Statements: {len(code)}",
        "",
    ]
    for i in range(max(0, start), min(end, len(code))):
        expr = code[i]
        lines.append(f"[{i:04d}] {inline(expr, r)}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("asset", type=Path, help="UAssetAPI JSON produced by UAssetGUI tojson")
    ap.add_argument("--function", help="Exact function ObjectName. Omit to list functions.")
    ap.add_argument("--start", type=int, default=0, help="First top-level statement index")
    ap.add_argument("--end", type=int, help="Exclusive top-level statement index")
    ap.add_argument("--summary-json", action="store_true", help="Emit machine-readable function summaries")
    args = ap.parse_args()

    asset = load_asset(args.asset)
    r = PackageResolver(asset)
    funcs = function_exports(asset)

    if args.summary_json:
        selected = funcs if not args.function else [x for x in funcs if x.get("ObjectName") == args.function]
        print(json.dumps([function_summary(x, r) for x in selected], indent=2))
        return 0 if selected else 2

    if not args.function:
        for fn in funcs:
            raw = fn.get("ScriptBytecodeRaw") or []
            print(f"{fn.get('ObjectName')}\t{fn.get('ScriptBytecodeSize')} bytes\t{len(fn.get('ScriptBytecode') or [])} statements\traw={len(raw)}")
        return 0

    selected = [x for x in funcs if x.get("ObjectName") == args.function]
    if not selected:
        raise SystemExit(f"Function not found: {args.function}")
    print(render_function(selected[0], r, args.start, args.end))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
