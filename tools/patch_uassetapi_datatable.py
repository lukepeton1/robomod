#!/usr/bin/env python3
"""Apply declarative patches to UAssetAPI DataTable JSON.

The first supported operation is deliberately narrow: remove selected DataTable row
handles from an ArrayProperty nested in a named DataTable row. The script preserves the
rest of the UAssetAPI JSON structure verbatim at the object level and emits a machine-
readable change report.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any


class PatchError(RuntimeError):
    pass


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def data_rows(asset: dict[str, Any]) -> list[dict[str, Any]]:
    exports = asset.get("Exports", [])
    tables = [x for x in exports if "DataTableExport" in str(x.get("$type", ""))]
    if len(tables) != 1:
        raise PatchError(f"expected exactly one DataTableExport, found {len(tables)}")
    rows = tables[0].get("Table", {}).get("Data")
    if not isinstance(rows, list):
        raise PatchError("DataTableExport has no Table.Data list")
    return rows


def nested_properties(row: dict[str, Any]) -> list[dict[str, Any]]:
    value = row.get("Value")
    if not isinstance(value, list):
        raise PatchError(f"row {row.get('Name')} has no Value list")
    # Roboquest DT_WeaponAffix wraps the actual row fields in StructPropertyData 'Affix'.
    affix = next((x for x in value if x.get("Name") == "Affix" and isinstance(x.get("Value"), list)), None)
    return affix["Value"] if affix else value


def property_by_name(row: dict[str, Any], name: str) -> dict[str, Any]:
    props = nested_properties(row)
    matches = [x for x in props if x.get("Name") == name]
    if len(matches) != 1:
        raise PatchError(
            f"row {row.get('Name')}: expected one property {name!r}, found {len(matches)}"
        )
    return matches[0]


def row_handle_name(handle: dict[str, Any]) -> str | None:
    value = handle.get("Value")
    if not isinstance(value, list):
        return None
    row_name = next((x for x in value if x.get("Name") == "RowName"), None)
    return row_name.get("Value") if row_name else None


def apply_remove_row_handles(
    row: dict[str, Any],
    field: str,
    values: list[str],
) -> dict[str, Any]:
    prop = property_by_name(row, field)
    current = prop.get("Value")
    if not isinstance(current, list):
        raise PatchError(f"row {row.get('Name')} field {field}: expected array Value")

    before = [row_handle_name(x) for x in current]
    requested = set(values)
    present = requested.intersection(x for x in before if x is not None)
    missing = requested - present
    if missing:
        raise PatchError(
            f"row {row.get('Name')} field {field}: requested handles not present: {sorted(missing)}; "
            f"current={before}"
        )

    prop["Value"] = [x for x in current if row_handle_name(x) not in requested]
    after = [row_handle_name(x) for x in prop["Value"]]
    return {"before": before, "after": after, "removed": sorted(requested)}


def apply(asset: dict[str, Any], spec: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    patched = copy.deepcopy(asset)
    rows = data_rows(patched)
    by_name = {str(x.get("Name")): x for x in rows}
    report: list[dict[str, Any]] = []

    for index, op in enumerate(spec.get("operations", [])):
        row_name = op.get("row")
        if row_name not in by_name:
            raise PatchError(f"operation {index}: DataTable row not found: {row_name!r}")

        if op.get("op") == "remove_row_handles":
            detail = apply_remove_row_handles(
                by_name[row_name],
                str(op["field"]),
                [str(x) for x in op.get("values", [])],
            )
        else:
            raise PatchError(f"operation {index}: unsupported op {op.get('op')!r}")

        report.append({
            "operation_index": index,
            "op": op.get("op"),
            "row": row_name,
            "field": op.get("field"),
            "reason": op.get("reason"),
            **detail,
        })

    return patched, report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("input_json", type=Path)
    ap.add_argument("patch_spec", type=Path)
    ap.add_argument("output_json", type=Path)
    ap.add_argument("--report", type=Path)
    args = ap.parse_args()

    asset = load(args.input_json)
    spec = load(args.patch_spec)
    patched, report = apply(asset, spec)

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(patched, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    report_payload = {
        "patch": spec.get("name"),
        "target": spec.get("target"),
        "operation_count": len(report),
        "changes": report,
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(report_payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(report_payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
