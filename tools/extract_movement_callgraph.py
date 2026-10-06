#!/usr/bin/env python3
"""Extract a resolved movement call graph from a Roboquest Momentum UAssetAPI handoff.

This script is read-only. It resolves UAsset package indices used by decoded Kismet
bytecode and emits a compact report showing which Blueprint functions hand execution
to native RoboQuest functions, Unreal movement primitives, or other movement-related
Blueprint functions.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Iterable

MOVEMENT_RE = re.compile(
    r"(move|movement|speed|dash|slide|power.?slide|grapple|jetpack|rocket.?jump|jump|"
    r"crouch|sprint|velocity|gravity|ground|fall|air|land|impulse|launch|friction|"
    r"acceler|brak|walk|floor|wall|predict|replicat|ledge|capsule)",
    re.IGNORECASE,
)

CORE_PACKAGES = (
    "Blueprint/Player/BP_APlayer",
    "Blueprint/Player/BP_APlayerController",
    "Blueprint/Player/BP_AGamePlayerController",
    "Blueprint/Player/BP_IngamePlayerController",
    "Blueprint/Skill/Ability/BP_PS_Dash",
    "Blueprint/Item/Common/BP_PowerSlideSkill",
    "Blueprint/Upgrade/Artefact/BP_Grapple",
    "Blueprint/Upgrade/Artefact/BP_Jetpack",
    "Blueprint/Skill/Mod/BP_WS_RocketJump",
    "Blueprint/Skill/Perk/BP_PS_RocketJump",
    "Blueprint/Interactive/Level/BP_Jumpad",
    "Blueprint/Upgrade/Artefact/BP_BunnyCrouch",
)

def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))

class Resolver:
    def __init__(self, asset: dict[str, Any]):
        self.exports = asset.get("Exports", [])
        self.imports = asset.get("Imports", [])

    def object(self, index: int) -> dict[str, Any] | None:
        if not isinstance(index, int) or index == 0:
            return None
        seq = self.exports if index > 0 else self.imports
        slot = index - 1 if index > 0 else -index - 1
        return seq[slot] if 0 <= slot < len(seq) else None

    def full_name(self, index: int) -> str:
        obj = self.object(index)
        if not obj:
            return f"<index:{index}>"
        name = str(obj.get("ObjectName") or f"<index:{index}>")
        outer = obj.get("OuterIndex")
        if isinstance(outer, int) and outer:
            return f"{self.full_name(outer)}.{name}"
        return name

def type_name(expr: Any) -> str:
    if not isinstance(expr, dict):
        return type(expr).__name__
    raw = str(expr.get("$type", ""))
    return raw.split(",", 1)[0].rsplit(".", 1)[-1]

def walk(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)

def functions(asset: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        exp for exp in asset.get("Exports", [])
        if "FunctionExport" in str(exp.get("$type", ""))
    ]

def package_path(path: Path, root: Path) -> str:
    rel = path.relative_to(root).as_posix()
    return rel[:-5] if rel.endswith(".json") else rel

def function_calls(fn: dict[str, Any], resolver: Resolver) -> list[dict[str, str]]:
    found: dict[tuple[str, str], dict[str, str]] = {}
    for expr in walk(fn.get("ScriptBytecode") or []):
        t = type_name(expr)
        if t not in {
            "EX_FinalFunction", "EX_CallMath", "EX_LocalFinalFunction",
            "EX_LocalVirtualFunction", "EX_VirtualFunction",
        }:
            continue

        target = ""
        kind = t
        node = expr.get("StackNode")
        if isinstance(node, int):
            target = resolver.full_name(node)
        if not target or target.startswith("<index:"):
            virtual = expr.get("VirtualFunctionName")
            if isinstance(virtual, str):
                target = virtual
                kind = f"{t}:virtual"
        if target:
            found[(kind, target)] = {"kind": kind, "target": target}
    return sorted(found.values(), key=lambda row: (row["target"].lower(), row["kind"]))

def import_summary(asset: dict[str, Any]) -> list[str]:
    result = []
    for imp in asset.get("Imports", []):
        name = str(imp.get("ObjectName", ""))
        class_name = str(imp.get("ClassName", ""))
        package = str(imp.get("ClassPackage", ""))
        joined = " ".join((name, class_name, package))
        if MOVEMENT_RE.search(joined) or "RoboquestMovementComponent" in joined or "Character_Player" in joined:
            result.append(name)
    return sorted(set(result))

def analyze_asset(path: Path, root: Path) -> dict[str, Any]:
    asset = load(path)
    resolver = Resolver(asset)
    rows = []
    for fn in functions(asset):
        calls = function_calls(fn, resolver)
        fn_name = str(fn.get("ObjectName", ""))
        if MOVEMENT_RE.search(fn_name) or any(MOVEMENT_RE.search(row["target"]) for row in calls):
            rows.append({
                "function": fn_name,
                "script_bytecode_size": fn.get("ScriptBytecodeSize"),
                "statement_count": len(fn.get("ScriptBytecode") or []),
                "raw_fallback_bytes": len(fn.get("ScriptBytecodeRaw") or []),
                "calls": calls,
            })
    return {
        "package": package_path(path, root),
        "imports": import_summary(asset),
        "functions": rows,
    }

def architecture_summary(assets: list[dict[str, Any]]) -> dict[str, Any]:
    all_calls = []
    for asset in assets:
        for fn in asset["functions"]:
            for call in fn["calls"]:
                all_calls.append({
                    "package": asset["package"],
                    "function": fn["function"],
                    **call,
                })

    character_player = sorted({
        row["target"] for row in all_calls
        if "Character_Player" in row["target"] and MOVEMENT_RE.search(row["target"])
    })
    unreal_primitives = sorted({
        row["target"] for row in all_calls
        if "/Script/Engine" in row["target"] and MOVEMENT_RE.search(row["target"])
    })
    movement_component_calls = sorted({
        row["target"] for row in all_calls
        if "RoboquestMovementComponent" in row["target"]
    })

    component_import_assets = []
    for asset in assets:
        if any("RoboquestMovementComponent" in item for item in asset["imports"]):
            component_import_assets.append(asset["package"])

    return {
        "character_player_movement_calls": character_player,
        "unreal_movement_primitives": unreal_primitives,
        "roboquest_movement_component_call_targets": movement_component_calls,
        "assets_importing_roboquest_movement_component": sorted(component_import_assets),
        "evidence": [
            "Decoded cooked Blueprint bytecode contains no direct reflected call target on RoboquestMovementComponent when the corresponding list is empty.",
            "Native Character_Player movement calls are Blueprint-visible semantic entry points, but the per-step ground/air integrator is not exposed by this cooked call graph.",
            "A full Source-style locomotion replacement should not be implemented as ReceiveTick plus SetActorLocation because that would bypass the native movement/prediction pipeline.",
        ],
    }

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("handoff", type=Path, help="movement-assets handoff directory")
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    root = args.handoff.resolve() / "uassetapi-json" / "RoboQuest" / "Content"
    if not root.is_dir():
        raise SystemExit(f"UAssetAPI root not found: {root}")

    reports = []
    missing = []
    for package in CORE_PACKAGES:
        path = root / f"{package}.json"
        if not path.is_file():
            missing.append(package)
            continue
        reports.append(analyze_asset(path, root))

    output = {
        "schema_version": 1,
        "handoff_root": str(args.handoff.resolve()),
        "missing_core_packages": missing,
        "assets": reports,
        "architecture": architecture_summary(reports),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "core_assets": len(reports),
        "missing": missing,
        "character_player_calls": len(output["architecture"]["character_player_movement_calls"]),
        "movement_component_calls": len(output["architecture"]["roboquest_movement_component_call_targets"]),
        "output": str(args.output),
    }, indent=2))
    return 1 if missing else 0

if __name__ == "__main__":
    raise SystemExit(main())
