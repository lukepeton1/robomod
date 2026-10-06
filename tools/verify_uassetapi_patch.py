#!/usr/bin/env python3
"""Verify that a declarative UAssetAPI DataTable patch is present in an asset."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from patch_uassetapi_datatable import PatchError, data_rows, property_by_name, row_handle_name


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def verify_applied(asset: dict, spec: dict) -> list[dict]:
    by_name = {str(x.get("Name")): x for x in data_rows(asset)}
    results = []
    errors = []

    for index, op in enumerate(spec.get("operations", [])):
        row_name = str(op["row"])
        row = by_name.get(row_name)
        if row is None:
            errors.append(f"operation {index}: row not found: {row_name}")
            continue

        if op.get("op") == "remove_row_handles":
            prop = property_by_name(row, str(op["field"]))
            current = [row_handle_name(x) for x in prop.get("Value", [])]
            forbidden = [str(x) for x in op.get("values", [])]
            still_present = [x for x in forbidden if x in current]
            results.append({
                "operation_index": index,
                "op": op.get("op"),
                "row": row_name,
                "field": op["field"],
                "forbidden_values": forbidden,
                "current_values": current,
                "still_present": still_present,
            })
            if still_present:
                errors.append(
                    f"operation {index}: {row_name}.{op['field']} still contains {still_present}"
                )

        elif op.get("op") == "copy_row_handles":
            source_row_name = str(op.get("source_row"))
            source_row = by_name.get(source_row_name)
            if source_row is None:
                errors.append(f"operation {index}: source row not found: {source_row_name}")
                continue
            target_prop = property_by_name(row, str(op["field"]))
            source_prop = property_by_name(
                source_row,
                str(op.get("source_field") or op["field"]),
            )
            current = [row_handle_name(x) for x in target_prop.get("Value", [])]
            expected = [row_handle_name(x) for x in source_prop.get("Value", [])]
            matches = current == expected
            results.append({
                "operation_index": index,
                "op": op.get("op"),
                "row": row_name,
                "field": op["field"],
                "source_row": source_row_name,
                "source_field": op.get("source_field") or op["field"],
                "current_values": current,
                "expected_values": expected,
                "matches": matches,
            })
            if not matches:
                errors.append(
                    f"operation {index}: {row_name}.{op['field']} does not match "
                    f"{source_row_name}.{op.get('source_field') or op['field']}"
                )
        else:
            errors.append(f"operation {index}: unsupported verification op {op.get('op')!r}")

    if errors:
        raise PatchError("; ".join(errors))
    return results


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("input_json", type=Path)
    ap.add_argument("patch_spec", type=Path)
    args = ap.parse_args()

    asset = load(args.input_json)
    spec = load(args.patch_spec)
    results = verify_applied(asset, spec)
    print(json.dumps({
        "verified": True,
        "patch": spec.get("name"),
        "operation_count": len(results),
        "checks": results,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
