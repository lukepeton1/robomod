#!/usr/bin/env python3
"""Generate Phase 4 raycast-Seeker eligibility from the production core policy."""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "Source/patches/weapon_foundry_core.json"
OUTPUT = ROOT / "Source/probes/raycast_seeker_eligibility.json"

def main():
    core = json.loads(CORE.read_text(encoding="utf-8"))
    standard = next(
        op["values"] for op in core["operations"]
        if op["op"] == "replace_name_array" and op["row"] == "Fragmentation"
    )
    payload = {
        "schema_version": 1,
        "name": "phase4-raycast-seeker-eligibility",
        "target": "Data/DT_WeaponAffix",
        "status": "diagnostic_probe",
        "purpose": (
            "Temporarily expand Homing/Seeker from the production projectile-only set "
            "to every standard Projectile/Raycast chassis while BP_WA_Homing is patched "
            "with the live hit-model resolver."
        ),
        "operations": [{
            "op": "replace_name_array",
            "row": "Homing",
            "field": "Weapons",
            "values": standard,
            "reason": (
                "Phase 4 probe only: permit native raycast skills to receive Seeker so "
                "the inserted HitType/Speed/CollisionSize resolver can be game-tested."
            ),
        }],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT}: {len(standard)} Seeker candidates")

if __name__ == "__main__":
    main()
