#!/usr/bin/env python3
"""Generate the runtime identity catalog used by ground-donor GRAFT.

Roboquest does not expose ordinary donor row IDs directly in the cooked Blueprint
surfaces currently available to Weapon Foundry. It *does* expose enough native
runtime state to identify transferable rows without parsing tooltip text:

- AWeaponAffix instances carry WeaponRef;
- AWeaponAffix exposes GetCustomFloatProperties(Name);
- UObject class identity distinguishes most affix rows;
- AWeapon.GetCurrentEnchantedAffixRowName identifies the singular perfume slot;
- AWeapon.GetDataRowName plus DT_Weapons identifies chassis-native rows.

This generator compiles research/generated/affixes.json,
research/generated/weapon_mods.json and transfer_policy.json into a deterministic
class/custom-property decision catalog. The runtime implementation should fail
closed when a locked row has the same runtime signature and contextual provenance
cannot disambiguate it.
"""
from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AFFIXES = ROOT / "research/generated/affixes.json"
DEFAULT_MODS = ROOT / "research/generated/weapon_mods.json"
DEFAULT_WEAPONS = ROOT / "research/generated/weapons.json"
DEFAULT_TRANSFER = ROOT / "Source/grafting/transfer_policy.json"
DEFAULT_OUTPUT = ROOT / "Source/grafting/donor_identity_catalog.json"

CONTEXT_GUARD_REASONS = {
    "chassis_or_internal_variant",
    "narrow_chassis_specific_pool",
    "narrow_chassis_specific_alt_fire",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_scalar(value: Any) -> Any:
    # Runtime custom properties are floats, but identity comparison only needs
    # numeric value. Canonicalize whole-number floats so generated JSON is stable
    # across Python/JSON producers while preserving fractional discriminators.
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        numeric = float(value)
        if numeric.is_integer():
            return int(numeric)
    return value


def normalize_custom(custom: dict[str, Any] | None) -> dict[str, Any]:
    return {
        str(key): normalize_scalar(value)
        for key, value in sorted((custom or {}).items())
    }


def runtime_value(custom: dict[str, Any], key: str) -> Any:
    """Model GetCustomFloatProperties(Name): absent keys resolve as zero."""
    return normalize_scalar(custom.get(key, 0))


def row_signature(row: dict[str, Any]) -> tuple[str | None, tuple[tuple[str, Any], ...]]:
    custom = normalize_custom(row.get("custom"))
    return row.get("class"), tuple(custom.items())


def minimal_discriminator_keys(rows: Iterable[dict[str, Any]]) -> list[str]:
    rows = list(rows)
    if len(rows) < 2:
        return []
    keys = sorted({key for row in rows for key in (row.get("custom") or {})})
    for width in range(1, len(keys) + 1):
        for combo in itertools.combinations(keys, width):
            seen: set[tuple[Any, ...]] = set()
            unique = True
            for row in rows:
                custom = normalize_custom(row.get("custom"))
                sig = tuple(runtime_value(custom, key) for key in combo)
                if sig in seen:
                    unique = False
                    break
                seen.add(sig)
            if unique:
                return list(combo)
    return []


def build_catalog(
    affixes: list[dict[str, Any]],
    mods: list[dict[str, Any]],
    weapons: list[dict[str, Any]],
    transfer: dict[str, Any],
) -> dict[str, Any]:
    sources = {
        "affix": {row["row"]: row for row in affixes},
        "weapon_mod": {row["row"]: row for row in mods},
    }
    locked_reason = {
        (row["kind"], row["row"]): row.get("reason")
        for row in transfer.get("locked", [])
    }

    all_rows: list[dict[str, Any]] = []
    for kind, rows in (("affix", affixes), ("weapon_mod", mods)):
        for row in rows:
            if not row.get("class"):
                continue
            all_rows.append({**row, "kind": kind, "custom": normalize_custom(row.get("custom"))})

    by_signature: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for row in all_rows:
        by_signature.setdefault(row_signature(row), []).append(row)

    transferable_sources: list[dict[str, Any]] = []
    for entry in transfer.get("transferable", []):
        kind = str(entry["kind"])
        row_id = str(entry["row"])
        source = sources.get(kind, {}).get(row_id)
        if source is None:
            raise RuntimeError(f"transferable row missing from generated catalog: {kind}:{row_id}")
        if not source.get("class"):
            raise RuntimeError(f"transferable row has no runtime affix class: {kind}:{row_id}")
        transferable_sources.append({**source, "kind": kind, "custom": normalize_custom(source.get("custom"))})

    by_class: dict[str, list[dict[str, Any]]] = {}
    for row in transferable_sources:
        by_class.setdefault(str(row["class"]), []).append(row)

    class_discriminators = []
    class_keys: dict[str, list[str]] = {}
    for class_path, rows in sorted(by_class.items()):
        keys = minimal_discriminator_keys(rows)
        if len(rows) > 1 and not keys:
            names = [row["row"] for row in rows]
            raise RuntimeError(f"transferable rows cannot be distinguished for {class_path}: {names}")
        class_keys[class_path] = keys
        if len(rows) > 1:
            class_discriminators.append({
                "class": class_path,
                "keys": keys,
                "rows": [row["row"] for row in sorted(rows, key=lambda x: x["row"])],
            })

    identities = []
    exact_count = 0
    guarded_count = 0
    for row in sorted(transferable_sources, key=lambda x: (x["kind"], x["row"])):
        collisions = []
        for other in by_signature[row_signature(row)]:
            if other["kind"] == row["kind"] and other["row"] == row["row"]:
                continue
            collisions.append({
                "row": other["row"],
                "kind": other["kind"],
                "active": bool(other.get("active")),
                "enchanted": bool(other.get("enchanted")),
                "locked_reason": locked_reason.get((other["kind"], other["row"])),
            })

        guards = []
        unresolved = []
        for collision in collisions:
            if not collision["active"]:
                guards.append({
                    "type": "ignore_inactive_row",
                    "row": collision["row"],
                })
            elif collision["enchanted"] or collision["locked_reason"] == "enchanted_slot_reserved":
                guards.append({
                    "type": "current_enchanted_row",
                    "row": collision["row"],
                    "rule": "do not identify this transferable row from an instance accounted for by the donor's current enchanted row",
                })
            elif collision["locked_reason"] in CONTEXT_GUARD_REASONS:
                guards.append({
                    "type": "chassis_or_internal_row",
                    "row": collision["row"],
                    "rule": "subtract chassis/native/internal instances before exposing donor choices; fail closed if provenance is ambiguous",
                })
            else:
                unresolved.append(collision)

        if unresolved:
            raise RuntimeError(
                f"unresolved runtime identity collision for {row['kind']}:{row['row']}: {unresolved}"
            )

        if collisions:
            guarded_count += 1
            identity_mode = "class_custom_plus_context"
        else:
            exact_count += 1
            identity_mode = "class_custom_exact"

        identities.append({
            "row": row["row"],
            "kind": row["kind"],
            "class": row["class"],
            "custom": normalize_custom(row.get("custom")),
            "class_discriminator_keys": class_keys[str(row["class"])],
            "identity_mode": identity_mode,
            "signature_collisions": collisions,
            "context_guards": guards,
        })

    guarded_native_rows = {
        guard["row"]
        for identity in identities
        for guard in identity["context_guards"]
        if guard["type"] == "chassis_or_internal_row"
    }
    chassis_native_rows = {}
    for weapon in sorted(weapons, key=lambda row: row.get("row") or ""):
        row_name = weapon.get("row")
        if not row_name:
            continue
        preset = [
            str(row)
            for row in (weapon.get("preset_affixes") or [])
            if str(row) in guarded_native_rows
        ]
        if preset:
            chassis_native_rows[str(row_name)] = preset

    return {
        "schema_version": 1,
        "name": "weapon-foundry-donor-runtime-identity",
        "runtime_model": {
            "acquisition": "retrieve live AWeaponAffix UObject references from the owning AWeapon or another native owner/container; actor enumeration is explicitly invalid",
            "actor_enumeration": "DISPROVEN: GameplayStatics.GetAllActorsOfClass(AWeaponAffix) returned 0 in a real run with an affixed dropped weapon present",
            "ownership_filter": "after references are obtained, keep only AWeaponAffix instances whose WeaponRef equals the donor AWeapon",
            "class_identity": "GetObjectClass(AWeaponAffix instance)",
            "custom_identity": "AWeaponAffix.GetCustomFloatProperties(Name); absent keys are treated as 0",
            "enchanted_disambiguation": "AWeapon.GetCurrentEnchantedAffixRowName()",
            "chassis_identity": "AWeapon.GetDataRowName(); use native/chassis affix provenance to exclude non-transferable base/internal rows",
            "source_of_truth": "row IDs and runtime signatures come from DT_WeaponAffix/DT_WeaponMod generated catalogs; never infer row identity from tooltip/display strings",
            "failure_policy": "fail closed when an active locked row shares a signature and provenance cannot distinguish the instance",
        },
        "summary": {
            "transferable_rows": len(identities),
            "exact_signature_rows": exact_count,
            "context_guarded_rows": guarded_count,
            "class_discriminator_groups": len(class_discriminators),
        },
        "class_discriminators": class_discriminators,
        "chassis_native_rows": chassis_native_rows,
        "identities": identities,
    }


def build_from_repo() -> dict[str, Any]:
    return build_catalog(
        load_json(DEFAULT_AFFIXES),
        load_json(DEFAULT_MODS),
        load_json(DEFAULT_WEAPONS),
        load_json(DEFAULT_TRANSFER),
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = ap.parse_args()
    payload = build_from_repo()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
