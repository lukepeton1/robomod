#!/usr/bin/env python3
"""Patch Blueprint CDO properties in UAssetAPI JSON with fail-closed schema checks."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any


class PatchError(RuntimeError):
    pass


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def ensure_name_map(asset: dict[str, Any], names: list[str]) -> list[str]:
    name_map = asset.get("NameMap")
    if not isinstance(name_map, list):
        raise PatchError("asset has no NameMap")
    existing = set(str(x) for x in name_map)
    added = []
    for name in names:
        if name and name not in existing:
            name_map.append(name)
            existing.add(name)
            added.append(name)
    if added:
        asset["NamesReferencedFromExportDataCount"] = len(name_map)
    return added


def find_cdo(asset: dict[str, Any], object_name: str) -> dict[str, Any]:
    matches = [
        e for e in asset.get("Exports", [])
        if e.get("ObjectName") == object_name
    ]
    if len(matches) != 1:
        raise PatchError(f"expected exactly one CDO {object_name!r}, found {len(matches)}")
    return matches[0]


def find_class(asset: dict[str, Any]) -> dict[str, Any]:
    matches = [
        e for e in asset.get("Exports", [])
        if "ClassExport" in str(e.get("$type", ""))
    ]
    if len(matches) != 1:
        raise PatchError(f"expected exactly one ClassExport, found {len(matches)}")
    return matches[0]


def assert_name_array_schema(asset: dict[str, Any], field: str) -> None:
    cls = find_class(asset)
    matches = [
        p for p in cls.get("LoadedProperties", [])
        if p.get("Name") == field
    ]
    if len(matches) != 1:
        raise PatchError(f"class does not expose exactly one property {field!r}")
    prop = matches[0]
    if "FArrayProperty" not in str(prop.get("$type", "")):
        raise PatchError(f"{field} is not an FArrayProperty")
    inner = prop.get("Inner") or {}
    if inner.get("SerializedType") != "NameProperty":
        raise PatchError(
            f"{field} inner type is {inner.get('SerializedType')!r}, expected NameProperty"
        )


def name_array_property(field: str, values: list[str]) -> dict[str, Any]:
    return {
        "$type": "UAssetAPI.PropertyTypes.Objects.ArrayPropertyData, UAssetAPI",
        "ArrayType": "NameProperty",
        "Name": field,
        "ArrayIndex": 0,
        "PropertyGuid": None,
        "IsZero": False,
        "PropertyTagFlags": "None",
        "PropertyTypeName": None,
        "PropertyTagExtensions": "NoExtension",
        "Value": [
            {
                "$type": "UAssetAPI.PropertyTypes.Objects.NamePropertyData, UAssetAPI",
                "Name": str(i),
                "ArrayIndex": 0,
                "PropertyGuid": None,
                "IsZero": False,
                "PropertyTagFlags": "None",
                "PropertyTypeName": None,
                "PropertyTagExtensions": "NoExtension",
                "Value": value,
            }
            for i, value in enumerate(values)
        ],
    }


def set_name_array(
    asset: dict[str, Any],
    cdo_name: str,
    field: str,
    values: list[str],
) -> dict[str, Any]:
    assert_name_array_schema(asset, field)
    cdo = find_cdo(asset, cdo_name)
    data = cdo.get("Data")
    if not isinstance(data, list):
        raise PatchError(f"CDO {cdo_name} has no Data list")

    existing = [p for p in data if p.get("Name") == field]
    if len(existing) > 1:
        raise PatchError(f"CDO contains multiple {field} properties")

    before = []
    if existing:
        prop = existing[0]
        if prop.get("ArrayType") != "NameProperty":
            raise PatchError(f"existing {field} is not Array<Name>")
        before = [
            x.get("Value") for x in prop.get("Value", [])
            if isinstance(x, dict)
        ]
        replacement = name_array_property(field, values)
        index = data.index(prop)
        data[index] = replacement
    else:
        data.append(name_array_property(field, values))

    added = ensure_name_map(asset, [field, *values])
    return {
        "cdo": cdo_name,
        "field": field,
        "before": before,
        "after": values,
        "count": len(values),
        "name_map_added": added,
    }


def apply(asset: dict[str, Any], spec: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    patched = copy.deepcopy(asset)
    report = []
    for index, op in enumerate(spec.get("operations", [])):
        kind = op.get("op")
        if kind != "set_name_array":
            raise PatchError(f"operation {index}: unsupported op {kind!r}")
        detail = set_name_array(
            patched,
            str(op["cdo"]),
            str(op["field"]),
            [str(x) for x in op.get("values", [])],
        )
        report.append({"operation_index": index, "op": kind, **detail})
    return patched, report


def verify(asset: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    checks = []
    errors = []
    for index, op in enumerate(spec.get("operations", [])):
        if op.get("op") != "set_name_array":
            errors.append(f"operation {index}: unsupported op")
            continue
        cdo = find_cdo(asset, str(op["cdo"]))
        props = [p for p in cdo.get("Data", []) if p.get("Name") == op["field"]]
        expected = [str(x) for x in op.get("values", [])]
        current = []
        array_type = None
        if len(props) == 1:
            array_type = props[0].get("ArrayType")
            current = [
                x.get("Value") for x in props[0].get("Value", [])
                if isinstance(x, dict)
            ]
        matches = len(props) == 1 and array_type == "NameProperty" and current == expected
        checks.append({
            "operation_index": index,
            "cdo": op["cdo"],
            "field": op["field"],
            "array_type": array_type,
            "current_values": current,
            "expected_values": expected,
            "matches": matches,
        })
        if not matches:
            errors.append(f"operation {index}: {op['cdo']}.{op['field']} mismatch")
    if errors:
        raise PatchError("; ".join(errors))
    return {"verified": True, "checks": checks}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("input_json", type=Path)
    ap.add_argument("patch_spec", type=Path)
    ap.add_argument("output_json", type=Path, nargs="?")
    ap.add_argument("--report", type=Path)
    ap.add_argument("--verify-only", action="store_true")
    args = ap.parse_args()

    asset, spec = load(args.input_json), load(args.patch_spec)
    if args.verify_only:
        print(json.dumps(verify(asset, spec), indent=2))
        return 0
    if args.output_json is None:
        raise SystemExit("output_json required unless --verify-only")

    patched, changes = apply(asset, spec)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(patched, indent=2) + "\n", encoding="utf-8")
    payload = {
        "patch": spec.get("name"),
        "target": spec.get("target"),
        "operation_count": len(changes),
        "changes": changes,
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
