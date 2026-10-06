#!/usr/bin/env python3
"""Build a machine-readable Roboquest research catalog from FModel JSON property exports.

This script intentionally does not depend on a wiki or hard-coded weapon lists. It walks
an exported RoboQuest/Content tree and records the classes, inheritance, CDO properties,
functions, and object references actually present in the installed build.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
from pathlib import Path
from typing import Any, Iterable

OBJ_PATH_RE = re.compile(r"(?:ObjectPath|AssetPathName|PathName)\"?\s*[:=]\s*\"?([^\"']+)")
DATA_TABLE_RE = re.compile(r"(/Game/[^\"']*/DT_[A-Za-z0-9_]+(?:\.\d+)?)")
GAME_PATH_RE = re.compile(r"(/Game/[A-Za-z0-9_./-]+(?:\.\d+)?)")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def objref(value: Any) -> str | None:
    if isinstance(value, dict):
        for key in ("ObjectPath", "AssetPathName", "PathName"):
            v = value.get(key)
            if isinstance(v, str):
                return v
    return None


def collect_refs(value: Any, out: set[str]) -> None:
    if isinstance(value, dict):
        p = objref(value)
        if p and p.startswith("/Game/"):
            out.add(p)
        for v in value.values():
            collect_refs(v, out)
    elif isinstance(value, list):
        for v in value:
            collect_refs(v, out)
    elif isinstance(value, str):
        for m in GAME_PATH_RE.finditer(value):
            out.add(m.group(1))


def cdo_for(objects: list[dict[str, Any]]) -> dict[str, Any] | None:
    for obj in objects:
        flags = str(obj.get("Flags", ""))
        name = str(obj.get("Name", ""))
        if "RF_ClassDefaultObject" in flags or name.startswith("Default__"):
            return obj
    return None


def generated_class_for(objects: list[dict[str, Any]]) -> dict[str, Any] | None:
    for obj in objects:
        if obj.get("Type") == "BlueprintGeneratedClass":
            return obj
    return None


def parent_class(objects: list[dict[str, Any]]) -> str | None:
    gc = generated_class_for(objects)
    if not gc:
        return None
    ss = gc.get("Super") or gc.get("SuperStruct") or {}
    if isinstance(ss, dict):
        return ss.get("ObjectName") or ss.get("ObjectPath")
    return str(ss) if ss else None


def functions(objects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for obj in objects:
        if obj.get("Type") != "Function":
            continue
        entry = {
            "name": obj.get("Name"),
            "flags": obj.get("FunctionFlags"),
        }
        ss = obj.get("SuperStruct") or {}
        if isinstance(ss, dict) and ss.get("ObjectName"):
            entry["overrides"] = ss.get("ObjectName")
        params = []
        for cp in obj.get("ChildProperties") or []:
            if not isinstance(cp, dict):
                continue
            pf = str(cp.get("PropertyFlags", ""))
            if "Parm" in pf:
                p = {"name": cp.get("Name"), "type": cp.get("Type")}
                if cp.get("Enum"):
                    p["enum"] = objref(cp.get("Enum")) or (cp.get("Enum") or {}).get("ObjectName")
                if cp.get("Struct"):
                    p["struct"] = objref(cp.get("Struct")) or (cp.get("Struct") or {}).get("ObjectName")
                if cp.get("PropertyClass"):
                    p["class"] = objref(cp.get("PropertyClass")) or (cp.get("PropertyClass") or {}).get("ObjectName")
                params.append(p)
        if params:
            entry["params"] = params
        locals_ = [
            cp.get("Name") for cp in (obj.get("ChildProperties") or [])
            if isinstance(cp, dict) and cp.get("Name")
        ]
        calls = sorted({
            name[len("CallFunc_"):].rsplit("_ReturnValue", 1)[0]
            for name in locals_
            if name.startswith("CallFunc_")
        })
        dynamic_casts = sorted({
            name[len("K2Node_DynamicCast_As"):]
            for name in locals_
            if name.startswith("K2Node_DynamicCast_As")
        })
        made_structs = sorted({
            name[len("K2Node_MakeStruct_"):].rstrip("_0123456789")
            for name in locals_
            if name.startswith("K2Node_MakeStruct_")
        })
        if calls:
            entry["call_hints"] = calls
        if dynamic_casts:
            entry["dynamic_cast_hints"] = dynamic_casts
        if made_structs:
            entry["make_struct_hints"] = made_structs
        out.append(entry)
    return out


def child_properties(objects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    gc = generated_class_for(objects)
    if not gc:
        return []
    result = []
    for cp in gc.get("ChildProperties") or []:
        if not isinstance(cp, dict):
            continue
        row = {
            "name": cp.get("Name"),
            "type": cp.get("Type"),
            "flags": cp.get("PropertyFlags"),
        }
        for k in ("Enum", "Struct", "PropertyClass", "MetaClass", "InterfaceClass"):
            if cp.get(k):
                row[k.lower()] = objref(cp[k]) or (cp[k].get("ObjectName") if isinstance(cp[k], dict) else cp[k])
        result.append(row)
    return result


def summarize_asset(path: Path, content_root: Path) -> dict[str, Any]:
    objects = load_json(path)
    if not isinstance(objects, list):
        objects = [objects]
    rel = path.relative_to(content_root).as_posix()
    gc = generated_class_for(objects)
    cdo = cdo_for(objects)
    refs: set[str] = set()
    collect_refs(objects, refs)
    summary: dict[str, Any] = {
        "path": rel,
        "asset": path.stem,
        "object_types": sorted(collections.Counter(str(o.get("Type")) for o in objects if isinstance(o, dict)).items()),
        "references": sorted(refs),
    }
    if gc:
        summary["class"] = gc.get("Name")
        summary["parent"] = parent_class(objects)
        summary["class_flags"] = gc.get("ClassFlags")
    if cdo:
        summary["cdo_type"] = cdo.get("Type")
        summary["cdo_properties"] = cdo.get("Properties") or {}
    fs = functions(objects)
    if fs:
        summary["functions"] = fs
    cps = child_properties(objects)
    if cps:
        summary["class_properties"] = cps
    return summary


def keep_cdo_props(props: dict[str, Any], *, max_depth: int = 4) -> dict[str, Any]:
    """Drop bulky editor/scene-component noise but preserve gameplay-facing values and refs."""
    noisy_exact = {
        "UberGraphFrame", "SimpleConstructionScript", "InheritableComponentHandler", "RootComponent",
        "Mesh", "IdleSoundComponent", "DefaultSceneRoot", "DefaultSceneRoot_GEN_VARIABLE",
    }
    def trim(v: Any, depth: int) -> Any:
        if depth > max_depth:
            if isinstance(v, (dict, list)):
                return "<truncated>"
            return v
        if isinstance(v, dict):
            return {k: trim(x, depth + 1) for k, x in v.items() if k not in noisy_exact}
        if isinstance(v, list):
            if len(v) > 64:
                return [trim(x, depth + 1) for x in v[:64]] + [f"<+{len(v)-64} more>"]
            return [trim(x, depth + 1) for x in v]
        return v
    return trim(props, 0)


def compact_asset(s: dict[str, Any]) -> dict[str, Any]:
    out = {k: s[k] for k in ("path", "asset", "class", "parent", "cdo_type") if k in s}
    if "functions" in s:
        out["functions"] = s["functions"]
    if "class_properties" in s:
        out["class_properties"] = s["class_properties"]
    props = s.get("cdo_properties") or {}
    if props:
        out["cdo_properties"] = keep_cdo_props(props)
    if s.get("references"):
        out["references"] = s["references"]
    return out


def walk_assets(content_root: Path) -> list[dict[str, Any]]:
    assets = []
    for p in sorted(content_root.rglob("*.json")):
        try:
            assets.append(summarize_asset(p, content_root))
        except Exception as exc:
            assets.append({"path": p.relative_to(content_root).as_posix(), "error": f"{type(exc).__name__}: {exc}"})
    return assets


def subset(assets: Iterable[dict[str, Any]], prefix: str) -> list[dict[str, Any]]:
    return [compact_asset(x) for x in assets if x.get("path", "").startswith(prefix) and "error" not in x]


def datatable_refs(assets: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    refs: dict[str, list[str]] = collections.defaultdict(list)
    for a in assets:
        for r in a.get("references") or []:
            if "/DT_" in r:
                refs[r].append(a["path"])
    return [
        {"datatable": k, "reference_count": len(v), "referenced_by": sorted(v)}
        for k, v in sorted(refs.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    ]


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("content_root", type=Path, help="Path to exported RoboQuest/Content")
    ap.add_argument("--out", type=Path, default=Path("research/generated"))
    args = ap.parse_args()
    root = args.content_root.resolve()
    out = args.out.resolve()
    assets = walk_assets(root)

    counts = collections.Counter()
    top_dirs = collections.Counter()
    errors = []
    for a in assets:
        p = a.get("path", "")
        top = "/".join(p.split("/")[:2])
        top_dirs[top] += 1
        if "error" in a:
            errors.append(a)
        for typ, n in a.get("object_types") or []:
            counts[typ] += n
    inventory = {
        "content_root": "RoboQuest/Content",
        "json_file_count": len(assets),
        "parse_error_count": len(errors),
        "top_directory_file_counts": dict(sorted(top_dirs.items())),
        "object_type_counts": dict(counts.most_common()),
        "parse_errors": errors,
    }
    write_json(out / "inventory.json", inventory)
    write_json(out / "affixes.json", subset(assets, "Blueprint/Weapon/Affixes/"))
    write_json(out / "weapon_prefabs.json", subset(assets, "Blueprint/Weapon/Prefab/"))
    write_json(out / "weapon_skills.json", subset(assets, "Blueprint/Skill/Weapon/"))
    write_json(out / "projectiles.json", subset(assets, "Blueprint/Projectile/"))
    write_json(out / "interactives.json", subset(assets, "Blueprint/Interactive/"))
    write_json(out / "datatable_refs.json", datatable_refs(assets))

    edges = []
    for a in assets:
        for ref in a.get("references") or []:
            edges.append({"source": a.get("path"), "target": ref})
    write_json(out / "asset_reference_edges.json", edges)

    print(f"Cataloged {len(assets)} JSON assets; {len(errors)} parse errors")
    for fname in ("affixes.json", "weapon_prefabs.json", "weapon_skills.json", "projectiles.json", "interactives.json", "datatable_refs.json"):
        p = out / fname
        print(f"{fname}: {p.stat().st_size:,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
