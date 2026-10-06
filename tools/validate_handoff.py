#!/usr/bin/env python3
"""Validate a Weapon Foundry legacy handoff produced by collect-legacy-handoff.ps1."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("handoff", type=Path, help="Extracted legacy-assets handoff directory")
    args = ap.parse_args()

    root = args.handoff.resolve()
    manifest_path = root / "handoff-manifest.json"
    if not manifest_path.is_file():
        raise SystemExit(f"Missing manifest: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    raw_root = root / "raw-legacy" / "RoboQuest" / "Content"
    json_root = root / "uassetapi-json" / "RoboQuest" / "Content"

    errors: list[str] = []
    function_exports = 0
    decoded_functions = 0
    raw_fallback_functions = 0
    json_count = 0

    if manifest.get("missing_count") != 0:
        errors.append(f"collector reported missing_count={manifest.get('missing_count')}")
    if manifest.get("collected_count") != manifest.get("target_count"):
        errors.append(
            f"collector count mismatch: {manifest.get('collected_count')} / {manifest.get('target_count')}"
        )

    for package in manifest.get("packages", []):
        rel = package["package"]
        for entry in package.get("files", []):
            path = raw_root / f"{rel}{entry['extension']}"
            if not path.is_file():
                errors.append(f"missing raw file: {path}")
                continue
            observed = sha256(path)
            expected = str(entry.get("sha256", "")).lower()
            if observed != expected:
                errors.append(f"hash mismatch: {path} expected={expected} observed={observed}")

        json_rel = package.get("uassetapi_json")
        if not json_rel:
            errors.append(f"package has no UAssetAPI JSON: {rel}")
            continue
        json_path = root / json_rel
        if not json_path.is_file():
            errors.append(f"missing UAssetAPI JSON: {json_path}")
            continue
        json_count += 1
        try:
            asset: dict[str, Any] = json.loads(json_path.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            errors.append(f"invalid JSON {json_path}: {exc}")
            continue

        for export in asset.get("Exports", []):
            if "FunctionExport" not in str(export.get("$type", "")):
                continue
            function_exports += 1
            code = export.get("ScriptBytecode")
            raw = export.get("ScriptBytecodeRaw") or []
            if isinstance(code, list):
                decoded_functions += 1
            if raw:
                raw_fallback_functions += 1

    summary = {
        "unreal_version": manifest.get("unreal_version"),
        "target_count": manifest.get("target_count"),
        "collected_count": manifest.get("collected_count"),
        "json_count": json_count,
        "function_exports": function_exports,
        "decoded_function_exports": decoded_functions,
        "raw_fallback_function_exports": raw_fallback_functions,
        "errors": errors,
    }
    print(json.dumps(summary, indent=2))

    if function_exports and decoded_functions != function_exports:
        errors.append(
            f"not all functions have decoded ScriptBytecode: {decoded_functions}/{function_exports}"
        )
    if raw_fallback_functions:
        errors.append(f"{raw_fallback_functions} functions contain raw bytecode fallback")

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
