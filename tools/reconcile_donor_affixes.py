#!/usr/bin/env python3
"""Reference runtime reconciler for Weapon Foundry donor affix identity.

The cooked implementation will observe live AWeaponAffix instances, not row IDs.
This module converts those observations back into authoritative transferable row
identities using Source/grafting/donor_identity_catalog.json.

The reconciler is deliberately multiset-based. Rows such as Explosive2/Explosive3
or AreaSize/AreaSize_Enchanted can share the same runtime class/custom signature.
Known chassis-native and enchanted instances are subtracted before any remaining
copy is exposed as a transferable donor choice.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = ROOT / "Source/grafting/donor_identity_catalog.json"


class DonorIdentityError(RuntimeError):
    pass


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_number(value: Any) -> Any:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        numeric = float(value)
        if numeric.is_integer():
            return int(numeric)
    return value


def custom_value(custom: dict[str, Any], key: str) -> Any:
    return canonical_number(custom.get(key, 0))


class DonorIdentityReconciler:
    def __init__(self, catalog: dict[str, Any]):
        self.catalog = catalog
        self.identities = catalog.get("identities", [])
        self.by_class: dict[str, list[dict[str, Any]]] = {}
        self.by_row: dict[str, dict[str, Any]] = {}
        self.guard_owner: dict[str, str] = {}

        for identity in self.identities:
            self.by_class.setdefault(str(identity["class"]), []).append(identity)
            self.by_row[str(identity["row"])] = identity
            for guard in identity.get("context_guards") or []:
                row = str(guard["row"])
                if guard["type"] in {"current_enchanted_row", "chassis_or_internal_row"}:
                    previous = self.guard_owner.get(row)
                    if previous is not None and previous != identity["row"]:
                        raise DonorIdentityError(
                            f"guard row {row} maps to multiple transferable identities: "
                            f"{previous}, {identity['row']}"
                        )
                    self.guard_owner[row] = str(identity["row"])

    @classmethod
    def from_repo(cls) -> "DonorIdentityReconciler":
        return cls(load_json(DEFAULT_CATALOG))

    def identify_observation(self, observation: dict[str, Any]) -> dict[str, Any] | None:
        class_path = str(observation.get("class") or "")
        if not class_path:
            raise DonorIdentityError("observation is missing class")

        candidates = self.by_class.get(class_path, [])
        if not candidates:
            return None

        observed_custom = {
            str(key): canonical_number(value)
            for key, value in (observation.get("custom") or {}).items()
        }

        matches = []
        for identity in candidates:
            keys = identity.get("class_discriminator_keys") or []
            expected = identity.get("custom") or {}
            if all(
                custom_value(observed_custom, key) == custom_value(expected, key)
                for key in keys
            ):
                matches.append(identity)

        if len(matches) == 1:
            return matches[0]
        if not matches:
            return None
        raise DonorIdentityError(
            f"ambiguous transferable identity for class {class_path}: "
            f"{[row['row'] for row in matches]}"
        )

    def _subtract(
        self,
        counts: Counter[str],
        row_id: str,
        *,
        source: str,
        subtractions: list[dict[str, Any]],
    ) -> None:
        target = self.guard_owner.get(str(row_id))
        if target is None:
            return
        if counts[target] <= 0:
            raise DonorIdentityError(
                f"cannot subtract {source} row {row_id}: no matching live "
                f"AWeaponAffix instance was observed for transferable identity {target}"
            )
        counts[target] -= 1
        subtractions.append({
            "source": source,
            "row": str(row_id),
            "transferable_signature": target,
        })

    def reconcile(
        self,
        observations: list[dict[str, Any]],
        *,
        donor_weapon_row: str,
        current_enchanted_row: str | None = None,
    ) -> dict[str, Any]:
        counts: Counter[str] = Counter()
        observed_matches = []
        ignored = []

        for index, observation in enumerate(observations):
            identity = self.identify_observation(observation)
            if identity is None:
                ignored.append({
                    "index": index,
                    "class": observation.get("class"),
                    "reason": "no_transferable_runtime_identity",
                })
                continue
            row_id = str(identity["row"])
            counts[row_id] += 1
            observed_matches.append({
                "index": index,
                "row": row_id,
                "kind": identity["kind"],
                "identity_mode": identity["identity_mode"],
            })

        raw_counts = dict(sorted(counts.items()))
        subtractions: list[dict[str, Any]] = []

        if current_enchanted_row and current_enchanted_row != "None":
            self._subtract(
                counts,
                current_enchanted_row,
                source="current_enchanted_row",
                subtractions=subtractions,
            )

        for native_row in (
            self.catalog.get("chassis_native_rows", {}).get(str(donor_weapon_row), [])
        ):
            self._subtract(
                counts,
                native_row,
                source="chassis_native_row",
                subtractions=subtractions,
            )

        choices = []
        for row_id in sorted(counts):
            instances = int(counts[row_id])
            if instances <= 0:
                continue
            identity = self.by_row[row_id]
            choices.append({
                "row": row_id,
                "kind": identity["kind"],
                "instances": instances,
                "identity_mode": identity["identity_mode"],
            })

        return {
            "donor_weapon_row": str(donor_weapon_row),
            "current_enchanted_row": current_enchanted_row,
            "observed_instance_count": len(observations),
            "matched_instance_count": len(observed_matches),
            "ignored_instance_count": len(ignored),
            "raw_transferable_signature_counts": raw_counts,
            "subtractions": subtractions,
            "choices": choices,
            "observed_matches": observed_matches,
            "ignored": ignored,
        }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("observations_json", type=Path)
    ap.add_argument("donor_weapon_row")
    ap.add_argument("--current-enchanted-row")
    ap.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    args = ap.parse_args()

    observations = load_json(args.observations_json)
    if not isinstance(observations, list):
        raise SystemExit("observations_json must contain a JSON array")

    result = DonorIdentityReconciler(load_json(args.catalog)).reconcile(
        observations,
        donor_weapon_row=args.donor_weapon_row,
        current_enchanted_row=args.current_enchanted_row,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
