#!/usr/bin/env python3
"""Analyze a UE4SS JMAP for Roboquest Momentum runtime hook seams."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

BASE = "/Script/Engine.CharacterMovementComponent"
CLIENT = "/Script/RoboQuest.ClientAuthorativeCMC"
ROBO = "/Script/RoboQuest.RoboquestMovementComponent"
ARCHVIS = "/Script/ArchVisCharacter.ArchVisCharMovementComponent"
CALC = "/Script/Engine.CharacterMovementComponent:CalcVelocity"


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def pointer_rva(value: str | None, image_base: int) -> int | None:
    if not value:
        return None
    return int(value, 16) - image_base


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("jmap", type=Path)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    raw = args.jmap.read_bytes()
    data = json.loads(raw.decode("utf-8-sig"))
    objects = data.get("objects", {})
    vtables = data.get("vtables", {})
    image_base = int(data["image_base_address"], 16)

    missing = [name for name in (BASE, CLIENT, ROBO, CALC) if name not in objects]
    if missing:
        raise SystemExit(f"JMAP missing required movement records: {missing}")

    def class_row(name: str) -> dict[str, Any]:
        row = objects[name]
        vtable = row.get("instance_vtable")
        return {
            "path": name,
            "super_struct": row.get("super_struct"),
            "properties_size": row.get("properties_size"),
            "min_alignment": row.get("min_alignment"),
            "children_count": len(row.get("children", [])),
            "children": row.get("children", []),
            "instance_vtable": vtable,
            "instance_vtable_rva": pointer_rva(vtable, image_base),
            "vtable_entry_count": len(vtables.get(vtable, [])) if vtable else 0,
        }

    base = class_row(BASE)
    client = class_row(CLIENT)
    robo = class_row(ROBO)
    arch = class_row(ARCHVIS) if ARCHVIS in objects else None

    calc = objects[CALC]
    calc_func = calc.get("func")

    arch_differences: list[dict[str, Any]] = []
    if arch:
        base_entries = vtables.get(base["instance_vtable"], [])
        arch_entries = vtables.get(arch["instance_vtable"], [])
        for index, (lhs, rhs) in enumerate(zip(base_entries, arch_entries)):
            if lhs != rhs:
                arch_differences.append({
                    "slot": index,
                    "base": lhs,
                    "archvis": rhs,
                })

    same_vtable = (
        base["instance_vtable"]
        == client["instance_vtable"]
        == robo["instance_vtable"]
    )
    same_size = (
        base["properties_size"]
        == client["properties_size"]
        == robo["properties_size"]
    )

    output = {
        "schema_version": 1,
        "source": {
            "filename": args.jmap.name,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "metadata": data.get("metadata"),
            "image_base_address": data.get("image_base_address"),
        },
        "classes": {
            "character_movement_component": base,
            "client_authorative_cmc": client,
            "roboquest_movement_component": robo,
            "archvis_reference_subclass": arch,
        },
        "calc_velocity": {
            "ufunction_path": CALC,
            "function_flags": calc.get("function_flags"),
            "exec_thunk_va": calc_func,
            "exec_thunk_rva": pointer_rva(calc_func, image_base),
            "properties_size": calc.get("properties_size"),
            "parameters": [
                {
                    "name": p.get("name"),
                    "offset": p.get("offset"),
                    "size": p.get("size"),
                    "type": p.get("type"),
                }
                for p in calc.get("properties", [])
            ],
        },
        "vtable_comparison": {
            "base_client_roboquest_same_instance_vtable": same_vtable,
            "base_client_roboquest_same_properties_size": same_size,
            "archvis_has_distinct_instance_vtable": bool(
                arch and arch["instance_vtable"] != base["instance_vtable"]
            ),
            "archvis_changed_slots_vs_base": arch_differences,
        },
        "conclusion": {
            "roboquest_has_distinct_movement_vtable": not same_vtable,
            "evidence_supports_guarded_base_calcvelocity_detour": bool(same_vtable and same_size),
            "note": (
                "JMAP shows ClientAuthorativeCMC and RoboquestMovementComponent sharing the exact "
                "UCharacterMovementComponent instance-vtable pointer and reflected object size. "
                "A known overriding subclass (ArchVisCharMovementComponent) has a distinct vtable. "
                "This strongly supports a guarded base CalcVelocity detour, but the exact vtable "
                "slot/function entry must still be resolved from the native exec thunk."
            ),
        },
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(json.dumps({
        "jmap": args.jmap.name,
        "same_vtable": same_vtable,
        "same_size": same_size,
        "calc_velocity_exec_thunk_rva": output["calc_velocity"]["exec_thunk_rva"],
        "archvis_changed_slots": [x["slot"] for x in arch_differences],
        "output": str(args.output),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
