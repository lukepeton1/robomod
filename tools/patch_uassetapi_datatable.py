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

    remaining = [x for x in current if row_handle_name(x) not in requested]
    prop["Value"] = remaining

    # UAssetAPI needs a StructProperty prototype when serializing an empty array.
    # In the vanilla DT_WeaponAffix export, naturally empty RemovedPool arrays carry
    # a DummyStruct that records the WeaponAffixRowHandle type. When a patch removes
    # the last real element, preserve that schema by synthesizing the same metadata
    # from the first pre-patch element.
    first_type = (
        str(current[0].get("$type", ""))
        if current and isinstance(current[0], dict)
        else ""
    )
    is_struct_array = (
        prop.get("ArrayType") == "StructProperty"
        or "StructPropertyData" in first_type
    )
    if is_struct_array and not prop.get("ArrayType"):
        prop["ArrayType"] = "StructProperty"

    if not remaining and is_struct_array and not prop.get("DummyStruct"):
        if not current:
            raise PatchError(
                f"row {row.get('Name')} field {field}: cannot infer DummyStruct for empty StructProperty array"
            )
        dummy = copy.deepcopy(current[0])
        if not isinstance(dummy, dict):
            raise PatchError(
                f"row {row.get('Name')} field {field}: first StructProperty element is not an object"
            )
        dummy["Value"] = []
        prop["DummyStruct"] = dummy

    after = [row_handle_name(x) for x in prop["Value"]]
    return {
        "before": before,
        "after": after,
        "removed": sorted(requested),
        "dummy_struct_preserved": bool(not remaining and prop.get("DummyStruct")),
    }


def array_item_value(item: Any) -> Any:
    if not isinstance(item, dict):
        return item
    # Row-handle struct arrays need semantic extraction; scalar property arrays such
    # as Weapons (Array<NameProperty>) already store their payload in Value directly.
    row_name = row_handle_name(item)
    if row_name is not None:
        return row_name
    return item.get("Value")


def apply_copy_array(
    target_row: dict[str, Any],
    target_field: str,
    source_row: dict[str, Any],
    source_field: str,
) -> dict[str, Any]:
    target_prop = property_by_name(target_row, target_field)
    source_prop = property_by_name(source_row, source_field)

    target_values = target_prop.get("Value")
    source_values = source_prop.get("Value")
    if not isinstance(target_values, list) or not isinstance(source_values, list):
        raise PatchError("copy_array requires array-valued source and target properties")

    target_array_type = target_prop.get("ArrayType")
    source_array_type = source_prop.get("ArrayType")
    if target_array_type and source_array_type and target_array_type != source_array_type:
        raise PatchError(
            f"cannot copy {source_row.get('Name')}.{source_field} ({source_array_type}) "
            f"into {target_row.get('Name')}.{target_field} ({target_array_type})"
        )

    before = [array_item_value(x) for x in target_values]
    source_snapshot = [array_item_value(x) for x in source_values]

    # Copy the complete native element representation rather than reconstructing it.
    # This preserves NamePropertyData/StructPropertyData metadata, element names,
    # property flags and any future fields UAssetAPI expects.
    target_prop["Value"] = copy.deepcopy(source_values)

    for key in ("ArrayType", "DummyStruct"):
        if key in source_prop:
            target_prop[key] = copy.deepcopy(source_prop[key])
        elif key in target_prop and key == "DummyStruct":
            # A non-struct source array must not retain stale struct-only metadata.
            target_prop.pop(key, None)

    after = [array_item_value(x) for x in target_prop["Value"]]
    return {
        "before": before,
        "after": after,
        "copied_from_row": source_row.get("Name"),
        "copied_from_field": source_field,
        "array_type": source_prop.get("ArrayType"),
        "copied_count": len(after),
        "source_values": source_snapshot,
    }


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
        elif op.get("op") == "copy_array":
            source_row_name = str(op.get("source_row"))
            if source_row_name not in by_name:
                raise PatchError(
                    f"operation {index}: source DataTable row not found: {source_row_name!r}"
                )
            detail = apply_copy_array(
                by_name[row_name],
                str(op["field"]),
                by_name[source_row_name],
                str(op.get("source_field") or op["field"]),
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
