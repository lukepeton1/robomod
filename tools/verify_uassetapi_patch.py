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
        if op.get("op") != "remove_row_handles":
            errors.append(f"operation {index}: unsupported verification op {op.get('op')!r}")
            continue
        row_name = str(op["row"])
        row = by_name.get(row_name)
        if row is None:
            errors.append(f"operation {index}: row not found: {row_name}")
            continue
        prop = property_by_name(row, str(op["field"]))
        current = [row_handle_name(x) for x in prop.get("Value", [])]
        forbidden = [str(x) for x in op.get("values", [])]
        still_present = [x for x in forbidden if x in current]
        results.append({
            "operation_index": index,
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
