#!/usr/bin/env python3
"""Deterministic Weapon Foundry target-aware GRAFT / Smith rule engine.

This module is intentionally independent from UI and cooked-asset mutation. It consumes
only generated policy data and returns an authoritative decision object:

- transferable / known property;
- target weapon compatibility;
- conflicts with rows already on the target;
- duplicate-instance policy;
- quality-scaled affix complexity cap;
- single native secondary-fire slot policy;
- exact Power Cell cost;
- optional donor-contains-row and available-funds checks.

The eventual dropped-weapon GRAFT UI and Smith/editor should call the same logic (or
mirror this contract in Blueprint) rather than implementing their own legality rules.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MATRIX = ROOT / "Source/grafting/compatibility_matrix.json"
DEFAULT_TRANSFER = ROOT / "Source/grafting/transfer_policy.json"
DEFAULT_TRANSACTION = ROOT / "Source/grafting/graft_transaction.json"
DEFAULT_PROGRESSION = ROOT / "Source/grafting/progression_policy.json"


class GraftRuleError(RuntimeError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        value = str(value)
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out


class GraftRules:
    def __init__(
        self,
        matrix: dict[str, Any],
        transfer: dict[str, Any],
        transaction: dict[str, Any] | None = None,
        progression: dict[str, Any] | None = None,
    ):
        self.matrix = matrix
        self.transfer = transfer
        self.transaction = transaction or {}
        self.progression = progression or {}
        self.properties = {
            row["row"]: row
            for row in matrix.get("properties", [])
        }
        self.transferable = {
            row["row"]: row
            for row in transfer.get("transferable", [])
        }

    @classmethod
    def from_repo(cls) -> "GraftRules":
        return cls(
            load_json(DEFAULT_MATRIX),
            load_json(DEFAULT_TRANSFER),
            load_json(DEFAULT_TRANSACTION),
            load_json(DEFAULT_PROGRESSION),
        )

    def quality_cap(self, quality_color: int) -> int:
        try:
            quality_color = int(quality_color)
        except (TypeError, ValueError) as exc:
            raise GraftRuleError("quality_color must be an integer") from exc
        raw_caps = self.progression.get("quality_color_caps") or {}
        caps = {int(key): int(value) for key, value in raw_caps.items()}
        if quality_color not in caps:
            raise GraftRuleError(
                f"unsupported quality color {quality_color}; expected one of {sorted(caps)}"
            )
        return caps[quality_color]

    def power_cell_cost(
        self,
        row_id: str,
        *,
        current_affix_count: int,
        duplicate_instance: bool = False,
    ) -> dict[str, int]:
        transfer = self.transferable.get(row_id)
        if transfer is None:
            raise GraftRuleError(f"row is not transferable: {row_id}")

        base = int(transfer["cell_cost_base"])
        free_affixes = int(
            self.progression.get("power_cell_economy", {}).get(
                "free_complexity_affixes",
                2,
            )
        )
        complexity = max(0, int(current_affix_count) - free_affixes)
        duplicate = (
            int(self.transfer["cost_model"].get("duplicate_instance_surcharge", 0))
            if duplicate_instance
            else 0
        )
        return {
            "base": base,
            "complexity_surcharge": complexity,
            "duplicate_surcharge": duplicate,
            "total": base + complexity + duplicate,
        }

    def evaluate(
        self,
        *,
        target_weapon: str,
        row_id: str,
        existing_affix_rows: Iterable[str] = (),
        existing_weapon_mod_rows: Iterable[str] = (),
        current_affix_count: int | None = None,
        quality_color: int = 0,
        available_power_cells: int | None = None,
        donor_rows: Iterable[str] | None = None,
        requested_kind: str | None = None,
    ) -> dict[str, Any]:
        affixes = _dedupe(existing_affix_rows)
        mods = _dedupe(existing_weapon_mod_rows)
        existing = set(affixes) | set(mods)
        reasons: list[dict[str, Any]] = []

        prop = self.properties.get(row_id)
        transfer = self.transferable.get(row_id)

        if prop is None or transfer is None:
            reasons.append({
                "code": "locked_property",
                "message": f"{row_id} is not in the transferable compatibility matrix.",
            })
            return self._result(
                allowed=False,
                target_weapon=target_weapon,
                row_id=row_id,
                kind=requested_kind,
                reasons=reasons,
                cost=None,
                quality_color=quality_color,
                quality_cap=None,
                current_affix_count=(
                    len(affixes) if current_affix_count is None else int(current_affix_count)
                ),
            )

        kind = str(prop["kind"])
        if requested_kind is not None and str(requested_kind) != kind:
            reasons.append({
                "code": "property_kind_mismatch",
                "message": f"{row_id} is {kind}, not {requested_kind}.",
            })

        if donor_rows is not None and row_id not in set(map(str, donor_rows)):
            reasons.append({
                "code": "donor_missing_property",
                "message": f"Donor does not contain {row_id}.",
            })

        compatible_weapons = set(prop.get("production_weapons") or [])
        if target_weapon not in compatible_weapons:
            reasons.append({
                "code": "incompatible_target",
                "message": f"{row_id} is not compatible with target weapon {target_weapon}.",
            })

        is_duplicate = row_id in existing
        duplicate_status = prop.get("duplicate_status")
        if is_duplicate and duplicate_status != "supported":
            reasons.append({
                "code": "duplicate_not_supported",
                "message": (
                    f"{row_id} is already present and duplicate-instance semantics are "
                    f"not production-verified ({duplicate_status})."
                ),
                "duplicate_status": duplicate_status,
            })

        conflicts = sorted(set(prop.get("transferable_conflicts") or []) & existing)
        if conflicts:
            reasons.append({
                "code": "transferable_conflict",
                "message": f"{row_id} conflicts with existing transferable rows.",
                "conflicts": conflicts,
            })

        affix_count = len(affixes) if current_affix_count is None else int(current_affix_count)
        cap: int | None = None

        if kind == "affix":
            cap = self.quality_cap(quality_color)
            if cap == 0:
                reasons.append({
                    "code": "quality_locked",
                    "message": "Common-quality weapons cannot accept ordinary Foundry grafts.",
                })
            elif affix_count >= cap:
                reasons.append({
                    "code": "complexity_cap",
                    "message": (
                        f"Target has {affix_count} affixes; quality tier {quality_color} "
                        f"caps Foundry complexity at {cap}."
                    ),
                    "current_affix_count": affix_count,
                    "quality_cap": cap,
                })
        elif kind == "weapon_mod":
            # The shipped weapon tooltip / skill surface exposes one secondary action.
            # Keep one native elite secondary-fire slot until multi-mod semantics are
            # explicitly verified in-game.
            if mods and not is_duplicate:
                reasons.append({
                    "code": "alt_fire_slot_occupied",
                    "message": (
                        "Target already has a native weapon-mod / secondary-fire row. "
                        "Multi-alt-fire storage and input semantics are not production-verified."
                    ),
                    "existing_weapon_mod_rows": mods,
                })
        else:
            reasons.append({
                "code": "unknown_property_kind",
                "message": f"Unsupported property kind {kind}.",
            })

        cost = self.power_cell_cost(
            row_id,
            current_affix_count=affix_count,
            duplicate_instance=is_duplicate,
        )
        if available_power_cells is not None and int(available_power_cells) < cost["total"]:
            reasons.append({
                "code": "insufficient_power_cells",
                "message": (
                    f"Need {cost['total']} Power Cells; only "
                    f"{int(available_power_cells)} available."
                ),
                "required": cost["total"],
                "available": int(available_power_cells),
            })

        return self._result(
            allowed=not reasons,
            target_weapon=target_weapon,
            row_id=row_id,
            kind=kind,
            reasons=reasons,
            cost=cost,
            quality_color=int(quality_color),
            quality_cap=cap,
            current_affix_count=affix_count,
            property=prop,
        )

    def plan_donor(
        self,
        *,
        target_weapon: str,
        donor_rows: Iterable[str],
        existing_affix_rows: Iterable[str] = (),
        existing_weapon_mod_rows: Iterable[str] = (),
        current_affix_count: int | None = None,
        quality_color: int = 0,
        available_power_cells: int | None = None,
    ) -> dict[str, Any]:
        donor = _dedupe(donor_rows)
        choices = [
            self.evaluate(
                target_weapon=target_weapon,
                row_id=row_id,
                existing_affix_rows=existing_affix_rows,
                existing_weapon_mod_rows=existing_weapon_mod_rows,
                current_affix_count=current_affix_count,
                quality_color=quality_color,
                available_power_cells=available_power_cells,
                donor_rows=donor,
            )
            for row_id in donor
        ]
        choices.sort(
            key=lambda result: (
                not result["allowed"],
                (result.get("cost") or {}).get("total", 10**9),
                result["row_id"],
            )
        )
        return {
            "mode": "donor",
            "target_weapon": target_weapon,
            "quality_color": int(quality_color),
            "donor_rows": donor,
            "allowed_count": sum(result["allowed"] for result in choices),
            "blocked_count": sum(not result["allowed"] for result in choices),
            "choices": choices,
        }

    def plan_smith(
        self,
        *,
        target_weapon: str,
        existing_affix_rows: Iterable[str] = (),
        existing_weapon_mod_rows: Iterable[str] = (),
        current_affix_count: int | None = None,
        quality_color: int = 0,
        available_power_cells: int | None = None,
    ) -> dict[str, Any]:
        choices = [
            self.evaluate(
                target_weapon=target_weapon,
                row_id=row_id,
                existing_affix_rows=existing_affix_rows,
                existing_weapon_mod_rows=existing_weapon_mod_rows,
                current_affix_count=current_affix_count,
                quality_color=quality_color,
                available_power_cells=available_power_cells,
            )
            for row_id in sorted(self.transferable)
        ]
        choices.sort(
            key=lambda result: (
                not result["allowed"],
                result.get("kind") or "",
                (result.get("cost") or {}).get("total", 10**9),
                result["row_id"],
            )
        )
        return {
            "mode": "smith",
            "target_weapon": target_weapon,
            "quality_color": int(quality_color),
            "allowed_count": sum(result["allowed"] for result in choices),
            "blocked_count": sum(not result["allowed"] for result in choices),
            "choices": choices,
        }

    @staticmethod
    def _result(
        *,
        allowed: bool,
        target_weapon: str,
        row_id: str,
        kind: str | None,
        reasons: list[dict[str, Any]],
        cost: dict[str, int] | None,
        quality_color: int,
        quality_cap: int | None,
        current_affix_count: int,
        property: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = {
            "allowed": bool(allowed),
            "target_weapon": target_weapon,
            "row_id": row_id,
            "kind": kind,
            "quality_color": quality_color,
            "quality_cap": quality_cap,
            "current_affix_count": current_affix_count,
            "cost": cost,
            "reasons": reasons,
        }
        if property is not None:
            result["display_name"] = property.get("display_name")
            result["rarity"] = property.get("rarity")
            result["widened_by_weapon_foundry"] = property.get(
                "widened_by_weapon_foundry", False
            )
            result["secondary_skill_row"] = property.get("secondary_skill_row")
        return result


def parse_csv(value: str) -> list[str]:
    return [x.strip() for x in value.split(",") if x.strip()]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("target_weapon")
    ap.add_argument("row_id")
    ap.add_argument("--kind", choices=["affix", "weapon_mod"])
    ap.add_argument("--quality-color", type=int, default=1)
    ap.add_argument("--affix-count", type=int)
    ap.add_argument("--existing-affixes", default="")
    ap.add_argument("--existing-mods", default="")
    ap.add_argument("--donor-rows", default=None)
    ap.add_argument("--power-cells", type=int)
    args = ap.parse_args()

    rules = GraftRules.from_repo()
    result = rules.evaluate(
        target_weapon=args.target_weapon,
        row_id=args.row_id,
        requested_kind=args.kind,
        quality_color=args.quality_color,
        current_affix_count=args.affix_count,
        existing_affix_rows=parse_csv(args.existing_affixes),
        existing_weapon_mod_rows=parse_csv(args.existing_mods),
        donor_rows=(
            parse_csv(args.donor_rows)
            if args.donor_rows is not None
            else None
        ),
        available_power_cells=args.power_cells,
    )
    print(json.dumps(result, indent=2))
    return 0 if result["allowed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
