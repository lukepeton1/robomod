#!/usr/bin/env python3
"""Static preflight validation for a Weapon Foundry release candidate.

This intentionally does not require extracted game assets. It verifies that the
repository's production contracts agree before the Windows builder touches UAssetGUI,
retoc, or the installed game.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


class ReleaseValidationError(RuntimeError):
    pass


def load_json(path: str) -> dict[str, Any]:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ReleaseValidationError(message)


def main() -> int:
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    require(bool(re.fullmatch(r"\d+\.\d+\.\d+-rc\d+", version)), f"invalid RC version: {version!r}")

    production = load_json("Source/manifests/production_packages.json")
    core = load_json("Source/patches/weapon_foundry_core.json")
    mods = load_json("Source/patches/weapon_foundry_mods.json")
    transfer = load_json("Source/grafting/transfer_policy.json")
    progression = load_json("Source/grafting/progression_policy.json")
    matrix = load_json("Source/grafting/compatibility_matrix.json")
    merchant = load_json("Source/patches/foundry_merchant.json")
    transaction = load_json("Source/grafting/graft_transaction.json")
    ui = load_json("Source/grafting/ui_contract.json")
    alt_profiles = load_json("Source/composition/alt_fire_skill_profiles.json")

    packages = production["packages"]
    require(len(packages) == 5, f"expected 5 production packages after Homing safety rollback, found {len(packages)}")
    package_paths = [row["path"] for row in packages]
    require(len(package_paths) == len(set(package_paths)), "duplicate production package path")

    for row in packages:
        source = ROOT / row["source"]
        require(source.is_file(), f"missing production patch source: {row['source']}")

    excluded = set(production.get("excluded_diagnostic_packages") or [])
    require(excluded.isdisjoint(package_paths), "diagnostic package leaked into production manifest")

    quality_caps = progression["quality_color_caps"]
    require(quality_caps == {"0": 0, "1": 3, "2": 4, "3": 5, "4": 6}, f"unexpected quality caps: {quality_caps}")
    require(progression["native_alt_fire_slots"] == 1, "native alt-fire slot policy changed")
    require(
        transaction["rule_engine"]["progression_policy"] == "Source/grafting/progression_policy.json",
        "transaction does not point to progression policy",
    )
    require(
        ui["shared"]["progression_policy"] == "Source/grafting/progression_policy.json",
        "UI does not point to progression policy",
    )

    transfer_summary = transfer["summary"]
    require(transfer_summary["transferable_affixes"] == 50, "expected 50 transferable affixes")
    require(transfer_summary["transferable_alt_fires"] == 15, "expected 15 transferable alt-fires")

    matrix_summary = matrix["summary"]
    require(
        matrix_summary["transferable_property_count"] == 65,
        "compatibility matrix should contain 65 transferable properties",
    )
    require(
        matrix_summary["transferable_affix_count"] == transfer_summary["transferable_affixes"],
        "matrix/transfer affix count mismatch",
    )
    require(
        matrix_summary["transferable_alt_fire_count"] == transfer_summary["transferable_alt_fires"],
        "matrix/transfer alt-fire count mismatch",
    )

    transferable_rows = {row["row"] for row in transfer["transferable"]}
    matrix_rows = {row["row"] for row in matrix["properties"]}
    require(transferable_rows == matrix_rows, "compatibility matrix rows do not exactly match transfer catalog")

    standard_count = core["policy"]["standard_weapon_count"]
    require(standard_count == 74, f"expected 74 standard chassis, found {standard_count}")
    require(core["policy"].get("seeker_resolver_enabled") is False, "unsafe Seeker resolver unexpectedly enabled")
    require(core["policy"].get("seeker_supported_weapon_count") == 7, "Seeker should remain on the 7 vanilla chassis")
    require(
        not any(
            row["op"] == "replace_name_array" and row["row"] == "Homing"
            for row in core["operations"]
        ),
        "production core must not widen Homing eligibility while the resolver is disabled",
    )

    require(mods["policy"]["resolved_alt_fire_count"] == 15, "expected 15 production alt-fire rows")
    require(len(mods["operations"]) == 15, "weapon-mod patch operation count changed")
    require(alt_profiles["production_alt_fire_count"] == 15, "alt-fire profile count changed")
    require(
        {row["row"] for row in alt_profiles["profiles"]}
        == {row["row"] for row in transfer["transferable"] if row["kind"] == "weapon_mod"},
        "alt-fire profiles do not exactly cover transferable weapon mods",
    )

    merchant_rows = merchant["operations"][0]["values"]
    require(len(merchant_rows) == 14, f"expected 14 globally safe conflict-free merchant affixes with Homing withheld, found {len(merchant_rows)}")
    require("Homing" not in merchant_rows, "Homing must remain target-specific while the raycast resolver is disabled")
    transfer_affixes = {
        row["row"]: row for row in transfer["transferable"] if row["kind"] == "affix"
    }
    require(set(merchant_rows).issubset(transfer_affixes), "merchant exposes non-transferable row")
    generalized = {
        op["row"] for op in core["operations"] if op["op"] == "replace_name_array"
    }
    unsafe = [
        row for row in merchant_rows
        if transfer_affixes[row].get("vanilla_weapons", 0) < standard_count
        and row not in generalized
    ]
    require(not unsafe, f"merchant exposes target-specific rows globally: {unsafe}")

    matrix_by_row = {row["row"]: row for row in matrix["properties"]}
    pairwise_conflicts = sorted({
        tuple(sorted((row, conflict)))
        for row in merchant_rows
        for conflict in matrix_by_row[row].get("transferable_conflicts", [])
        if conflict in merchant_rows
    })
    require(
        not pairwise_conflicts,
        f"global merchant contains mutually exclusive transferable rows: {pairwise_conflicts}",
    )
    require(
        set(merchant["policy"].get("excluded_global_conflict_rows") or [])
        == {"BossDamage", "FlyDamage", "TurretDamage"},
        "expected mutually exclusive damage-specialization rows to remain target-aware only",
    )

    builder = (ROOT / "tools/windows/build-weapon-foundry.ps1").read_text(encoding="utf-8")
    required_builder_tokens = [
        "patch_fragmentation_bytecode.py",
        "patch_foundry_interactive.py",
        "foundry_merchant.json",
        "weapon_foundry_mods.json",
        "progression_policy.json",
        "14/14",
    ]
    missing_tokens = [token for token in required_builder_tokens if token not in builder]
    require(not missing_tokens, f"production builder missing required tokens: {missing_tokens}")

    packager = (ROOT / "tools/windows/package-release.ps1").read_text(encoding="utf-8")
    required_release_sources = [
        "Source\\grafting\\progression_policy.json",
        "Source\\grafting\\compatibility_matrix.json",
        "Source\\grafting\\ui_contract.json",
        "Source\\composition\\alt_fire_skill_profiles.json",
        "tools\\evaluate_graft.py",
        "tools\\patch_homing_resolver.py",
        "tools\\patch_foundry_interactive.py",
    ]
    missing_release = [token for token in required_release_sources if token not in packager]
    require(not missing_release, f"release package omits source artifacts: {missing_release}")

    result = {
        "verified": True,
        "version": version,
        "production_package_count": len(packages),
        "standard_weapon_count": standard_count,
        "transferable_affixes": transfer_summary["transferable_affixes"],
        "transferable_alt_fires": transfer_summary["transferable_alt_fires"],
        "global_merchant_affixes": len(merchant_rows),
        "quality_caps": quality_caps,
        "native_alt_fire_slots": progression["native_alt_fire_slots"],
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
