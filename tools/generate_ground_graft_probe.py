#!/usr/bin/env python3
"""Generate the server-ping quick-GRAFT transaction probe policy.

This is an end-to-end diagnostic, not the final selection UI. It uses the same
ordinary-affix pool already exposed globally by the production Foundry merchant,
so every candidate has broad target compatibility. Runtime selection is the first
candidate (in the generated priority order) that actually exists on the donor.

The cooked probe is intentionally conservative:
- ordinary affixes only;
- no Homing while the raycast resolver is rolled back;
- native Power Cells / tickets;
- existing AddEnchantedAffix replication chain;
- donor consumed only after target re-enumeration verifies the added row.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MERCHANT = ROOT / "Source/patches/foundry_merchant.json"
TRANSFER = ROOT / "Source/grafting/transfer_policy.json"
OUTPUT = ROOT / "Source/probes/ground_graft_ping_probe.json"

CORE_PRIORITY = [
    "Fragmentation",
    "AutoShotgun",
    "Bounce",
    "Pierce",
    "Ricochet",
    "Burn",
    "Ice",
    "Shock",
    "ExplosiveBlank",
    "FreeShot",
    "Firerate",
    "Impact",
    "MarkDamage",
    "AutoCritical",
]


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    merchant = load(MERCHANT)
    transfer = load(TRANSFER)

    merchant_rows = list(merchant["operations"][0]["values"])
    transfer_by_row = {
        row["row"]: row
        for row in transfer["transferable"]
        if row["kind"] == "affix"
    }

    ordered = [row for row in CORE_PRIORITY if row in merchant_rows]
    ordered.extend(row for row in merchant_rows if row not in ordered)

    candidates = []
    for row_id in ordered:
        entry = transfer_by_row.get(row_id)
        if entry is None:
            raise RuntimeError(f"merchant row is not transferable ordinary affix: {row_id}")
        candidates.append({
            "row": row_id,
            "base_cost": int(entry["cell_cost_base"]),
            "rarity": entry["rarity"],
            "core_composition": bool(entry.get("core_composition")),
        })

    payload = {
        "schema_version": 1,
        "name": "weapon-foundry-ground-graft-ping-probe",
        "status": "diagnostic_probe",
        "trigger": {
            "input": "existing ping action on a dropped weapon",
            "server_rpc": "BP_APlayer.OnServerPingActor(ActorRef, Location)",
            "donor_actor_type": "AInteractiveWeapon",
            "non_weapon_behavior": "fall through to vanilla ping",
        },
        "native_seams": {
            "donor_weapon": "AInteractiveWeapon.SpawnedWeapon",
            "donor_rows": "AAWeapon.GetAffixRowNames()",
            "target_weapon": "Character_Player.currentWeapon",
            "target_rows": "AAWeapon.GetAffixRowNames()",
            "mutation": "BP_APlayer.AddEnchantedAffix(RowName)",
            "currency_balance": "Character_Player.CurrentTicket",
            "currency_debit": "Character_Player.RemoveTicket(int)",
            "currency_refund": "Character_Player.AddTicket(int, false)",
            "donor_consume": "AActor.K2_DestroyActor() on the dropped AInteractiveWeapon",
        },
        "selection": {
            "mode": "first_supported_donor_row_by_priority",
            "final_ui_requirement": "replace automatic choice with explicit native-feeling donor-row selection",
            "candidates": candidates,
        },
        "validation_order": [
            "actor is AInteractiveWeapon",
            "SpawnedWeapon is valid and distinct from currentWeapon",
            "donor GetAffixRowNames contains a supported candidate",
            "target does not already contain selected row",
            "target quality is above common",
            "AffixAmount is below color + 2 quality cap",
            "CurrentTicket >= base cost + max(0, AffixAmount - 2)",
        ],
        "commit_order": [
            "RemoveTicket(total_cost)",
            "AddEnchantedAffix(selected_row) on server player",
            "re-read currentWeapon.GetAffixRowNames()",
            "if selected row absent: AddTicket(total_cost, false) and leave donor",
            "if selected row present: K2_DestroyActor(donor interactive) and suppress vanilla ping",
        ],
        "quality_caps": {"0": 0, "1": 3, "2": 4, "3": 5, "4": 6},
        "free_complexity_affixes": 2,
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT}: {len(candidates)} quick-GRAFT candidate rows; excluded {len(excluded_native_rows)} preset-bearing rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
