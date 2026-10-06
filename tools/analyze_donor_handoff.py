#!/usr/bin/env python3
"""Rank donor-affix / tooltip / weapon-state seams in an expanded legacy handoff.

Input is the extracted handoff directory produced by collect-legacy-handoff.ps1.
The scanner does not modify game assets. It reads UAssetAPI JSON and emits a ranked
machine-readable report of functions, properties and imports likely to expose:

- ordinary affix row IDs;
- weapon-mod / alt-fire row IDs;
- CurrentAffixBundle / quality data;
- tooltip initialization payloads;
- dropped-weapon interaction / donor consumption;
- player-controller UI seams.

This exists so the next raw handoff can be turned into GRAFT implementation work
immediately instead of another manual discovery pass.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


TOKENS = {
    "affix": 8,
    "rowname": 8,
    "row": 3,
    "weaponaffix": 10,
    "weaponmod": 10,
    "currentaffixbundle": 10,
    "affixamount": 7,
    "affixrow": 10,
    "weaponaffixrow": 12,
    "currentenchantedaffixrowname": 14,
    "weaponaffixtooltipwidget": 12,
    "weapontooltipwidget": 10,
    "tooltip": 5,
    "weapon": 2,
    "interactiveweapon": 7,
    "consume": 6,
    "destroy": 5,
    "remove": 2,
    "pickup": 4,
    "swap": 4,
    "merchant": 3,
    "quality": 4,
    "datatable": 3,
    "get": 1,
}

TARGET_PATH_HINTS = {
    "WGT_Tooltip_Weapon": 12,
    "WGT_Tooltip_WeaponAffix": 12,
    "WGT_WeaponCompendium_Affix": 10,
    "BP_Interactive_Weapon": 12,
    "BP_IngamePlayerController": 8,
    "BP_Merchant_UpgradeAffix": 5,
    "WGT_Merchant_AddEnchantedAffix": 8,
    "WGT_Merchant_UpgradeWeapon": 8,
    "BP_Interactive_WeaponSpawner": 6,
}


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def type_name(value: Any) -> str:
    if not isinstance(value, dict):
        return type(value).__name__
    raw = str(value.get("$type", ""))
    return raw.split(",", 1)[0].rsplit(".", 1)[-1]


def walk(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def score_text(text: str) -> tuple[int, list[str]]:
    lower = text.lower()
    hits = []
    score = 0
    for token, weight in TOKENS.items():
        if token in lower:
            hits.append(token)
            score += weight
    return score, sorted(set(hits))


def object_name(asset: dict[str, Any], index: int) -> str | None:
    if not isinstance(index, int) or index == 0:
        return None
    seq = asset.get("Exports", []) if index > 0 else asset.get("Imports", [])
    slot = index - 1 if index > 0 else -index - 1
    if 0 <= slot < len(seq):
        return str(seq[slot].get("ObjectName"))
    return None


def function_evidence(asset: dict[str, Any], fn: dict[str, Any]) -> dict[str, Any]:
    calls = []
    names = []
    fields = []
    classes = []

    for node in walk(fn.get("ScriptBytecode") or []):
        stack = node.get("StackNode")
        if isinstance(stack, int):
            name = object_name(asset, stack)
            if name:
                calls.append(name)

        if type_name(node) == "EX_NameConst":
            names.append(str(node.get("Value")))

        for pointer_key in ("Variable", "RValuePointer", "Value"):
            pointer = node.get(pointer_key)
            if isinstance(pointer, dict):
                new = pointer.get("New")
                if isinstance(new, dict):
                    path = new.get("Path")
                    if isinstance(path, list):
                        fields.extend(str(x) for x in path)

        if type_name(node) == "EX_DynamicCast":
            ptr = node.get("ClassPtr")
            if isinstance(ptr, int):
                name = object_name(asset, ptr)
                if name:
                    classes.append(name)

    evidence = {
        "function": fn.get("ObjectName"),
        "calls": sorted(set(calls)),
        "name_constants": sorted(set(names)),
        "field_paths": sorted(set(fields)),
        "dynamic_casts": sorted(set(classes)),
        "script_bytecode_size": fn.get("ScriptBytecodeSize"),
        "decoded": isinstance(fn.get("ScriptBytecode"), list) and not bool(fn.get("ScriptBytecodeRaw")),
    }
    text = json.dumps(evidence, sort_keys=True)
    score, hits = score_text(text)
    evidence["score"] = score
    evidence["token_hits"] = hits
    return evidence


def scan_asset(path: Path, root: Path) -> dict[str, Any]:
    asset = load(path)
    rel = path.relative_to(root).as_posix()
    path_score = 0
    path_hits = []
    for hint, weight in TARGET_PATH_HINTS.items():
        if hint.lower() in rel.lower():
            path_score += weight
            path_hits.append(hint)

    functions = []
    for export in asset.get("Exports", []):
        if "FunctionExport" in str(export.get("$type", "")):
            evidence = function_evidence(asset, export)
            evidence["score"] += path_score
            if evidence["score"] > 0:
                functions.append(evidence)
    functions.sort(key=lambda x: (-x["score"], str(x["function"])))

    properties = []
    for export in asset.get("Exports", []):
        for prop in export.get("LoadedProperties") or []:
            text = json.dumps(prop, sort_keys=True)
            score, hits = score_text(text)
            if score:
                properties.append({
                    "owner": export.get("ObjectName"),
                    "name": prop.get("Name"),
                    "type": type_name(prop),
                    "score": score + path_score,
                    "token_hits": hits,
                })
    properties.sort(key=lambda x: (-x["score"], str(x["name"])))

    imports = []
    for idx, imp in enumerate(asset.get("Imports", []), start=1):
        text = json.dumps(imp, sort_keys=True)
        score, hits = score_text(text)
        if score:
            imports.append({
                "package_index": -idx,
                "object_name": imp.get("ObjectName"),
                "class_name": imp.get("ClassName"),
                "outer_index": imp.get("OuterIndex"),
                "score": score + path_score,
                "token_hits": hits,
            })
    imports.sort(key=lambda x: (-x["score"], str(x["object_name"])))

    best = max(
        [path_score]
        + [x["score"] for x in functions[:1]]
        + [x["score"] for x in properties[:1]]
        + [x["score"] for x in imports[:1]]
    )
    return {
        "path": rel,
        "path_score": path_score,
        "path_hints": path_hits,
        "best_score": best,
        "functions": functions[:40],
        "properties": properties[:40],
        "imports": imports[:60],
    }


def locate_json_root(handoff: Path) -> Path:
    candidates = [
        handoff / "uassetapi-json" / "RoboQuest" / "Content",
        handoff / "uassetapi-json",
        handoff,
    ]
    for candidate in candidates:
        if candidate.is_dir() and any(candidate.rglob("*.json")):
            return candidate
    raise SystemExit(f"could not find UAssetAPI JSON under {handoff}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("handoff", type=Path)
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()

    handoff = args.handoff.resolve()
    root = locate_json_root(handoff)
    rows = []
    for path in sorted(root.rglob("*.json")):
        try:
            row = scan_asset(path, root)
        except Exception as exc:
            rows.append({
                "path": path.relative_to(root).as_posix(),
                "error": str(exc),
                "best_score": -1,
            })
            continue
        if row["best_score"] > 0:
            rows.append(row)

    rows.sort(key=lambda x: (-x.get("best_score", -1), x["path"]))
    payload = {
        "schema_version": 1,
        "handoff": str(handoff),
        "json_root": str(root),
        "asset_count": len(rows),
        "ranking_policy": {
            "tokens": TOKENS,
            "path_hints": TARGET_PATH_HINTS,
        },
        "top_candidates": rows[:80],
    }

    output = args.output or (handoff / "donor-affix-seams.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    print(f"wrote {output}")
    for row in rows[:15]:
        print(f"{row['best_score']:>4}  {row['path']}")
        for fn in row.get("functions", [])[:3]:
            print(
                f"      fn {fn['score']:>3} {fn['function']} "
                f"[{', '.join(fn['token_hits'])}]"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
