#!/usr/bin/env python3
"""Resolve the CharacterMovementComponent::CalcVelocity virtual-call slot from a local executable.

This reads the UE4SS JMAP to locate the reflected execCalcVelocity thunk, maps that VA
back into RoboQuest-Win64-Shipping.exe, and inspects only a small bounded thunk window.
The output contains metadata and short candidate instruction snippets, never the game binary.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path
from typing import Any

CALC = "/Script/Engine.CharacterMovementComponent:CalcVelocity"
BASE = "/Script/Engine.CharacterMovementComponent"
ROBO = "/Script/RoboQuest.RoboquestMovementComponent"

REGS = (
    "rax", "rcx", "rdx", "rbx", "rsp", "rbp", "rsi", "rdi",
    "r8", "r9", "r10", "r11", "r12", "r13", "r14", "r15",
)


def read_pe_sections(data: bytes) -> tuple[int, list[dict[str, int | str]]]:
    if len(data) < 0x40 or data[:2] != b"MZ":
        raise ValueError("not a PE file")
    peoff = struct.unpack_from("<I", data, 0x3C)[0]
    if data[peoff:peoff + 4] != b"PE\0\0":
        raise ValueError("missing PE signature")
    number_of_sections = struct.unpack_from("<H", data, peoff + 6)[0]
    optional_header_size = struct.unpack_from("<H", data, peoff + 20)[0]
    optional = peoff + 24
    if optional + optional_header_size > len(data):
        raise ValueError("truncated PE optional header")
    magic = struct.unpack_from("<H", data, optional)[0]
    if magic == 0x20B:
        image_base = struct.unpack_from("<Q", data, optional + 24)[0]
    elif magic == 0x10B:
        image_base = struct.unpack_from("<I", data, optional + 28)[0]
    else:
        raise ValueError(f"unsupported PE optional-header magic: 0x{magic:x}")

    section_table = optional + optional_header_size
    sections: list[dict[str, int | str]] = []
    for i in range(number_of_sections):
        off = section_table + i * 40
        name = data[off:off + 8].split(b"\0", 1)[0].decode("ascii", "replace")
        virtual_size, virtual_address, raw_size, raw_pointer = struct.unpack_from(
            "<IIII", data, off + 8
        )
        sections.append({
            "name": name,
            "virtual_size": virtual_size,
            "virtual_address": virtual_address,
            "raw_size": raw_size,
            "raw_pointer": raw_pointer,
        })
    return image_base, sections


def rva_to_file_offset(rva: int, sections: list[dict[str, int | str]]) -> int:
    for section in sections:
        start = int(section["virtual_address"])
        span = max(int(section["virtual_size"]), int(section["raw_size"]))
        if start <= rva < start + span:
            delta = rva - start
            if delta >= int(section["raw_size"]):
                raise ValueError(
                    f"RVA 0x{rva:x} maps past raw bytes of section {section['name']}"
                )
            return int(section["raw_pointer"]) + delta
    raise ValueError(f"RVA 0x{rva:x} not mapped by a PE section")


def signed8(value: int) -> int:
    return struct.unpack("<b", bytes([value]))[0]


def signed32(data: bytes) -> int:
    return struct.unpack("<i", data)[0]


def scan_indirect_calls(code: bytes) -> list[dict[str, Any]]:
    """Find x86-64 FF /2 memory-indirect calls and decode their displacement.

    This is intentionally small, not a general disassembler. We only need to identify
    the virtual dispatch emitted by the generated exec thunk.
    """
    out: list[dict[str, Any]] = []
    i = 0
    while i < len(code) - 2:
        start = i
        rex = None
        if 0x40 <= code[i] <= 0x4F:
            rex = code[i]
            i += 1
            if i >= len(code) - 2:
                break

        if code[i] != 0xFF:
            i = start + 1
            continue

        modrm = code[i + 1]
        reg_field = (modrm >> 3) & 0x7
        if reg_field != 2:  # FF /2 = CALL r/m64
            i = start + 1
            continue

        mod = (modrm >> 6) & 0x3
        rm = modrm & 0x7
        if mod == 3:  # CALL register, not memory/vtable
            i = start + 1
            continue

        rex_b = (rex & 0x1) if rex is not None else 0
        cursor = i + 2
        base_reg: int | None = rm + (8 if rex_b else 0)
        index_reg: int | None = None
        scale = 1
        displacement = 0

        if rm == 4:
            if cursor >= len(code):
                break
            sib = code[cursor]
            cursor += 1
            scale = 1 << ((sib >> 6) & 0x3)
            index = (sib >> 3) & 0x7
            base = sib & 0x7
            rex_x = ((rex >> 1) & 0x1) if rex is not None else 0
            if index != 4 or rex_x:
                index_reg = index + (8 if rex_x else 0)
            base_reg = base + (8 if rex_b else 0)
            if mod == 0 and base == 5:
                base_reg = None
                if cursor + 4 > len(code):
                    break
                displacement = signed32(code[cursor:cursor + 4])
                cursor += 4

        if mod == 0:
            if rm == 5:
                base_reg = None
                if cursor + 4 > len(code):
                    break
                displacement = signed32(code[cursor:cursor + 4])
                cursor += 4
        elif mod == 1:
            if cursor >= len(code):
                break
            displacement = signed8(code[cursor])
            cursor += 1
        elif mod == 2:
            if cursor + 4 > len(code):
                break
            displacement = signed32(code[cursor:cursor + 4])
            cursor += 4

        length = cursor - start
        slot = (
            displacement // 8
            if base_reg is not None and index_reg is None
            and displacement >= 0 and displacement % 8 == 0
            else None
        )
        lo = max(0, start - 12)
        hi = min(len(code), cursor + 12)
        out.append({
            "offset_in_window": start,
            "instruction_length": length,
            "instruction_hex": code[start:cursor].hex(),
            "context_hex": code[lo:hi].hex(),
            "base_register": REGS[base_reg] if base_reg is not None else None,
            "index_register": REGS[index_reg] if index_reg is not None else None,
            "scale": scale,
            "displacement": displacement,
            "possible_vtable_slot": slot,
        })
        i = cursor
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("executable", type=Path)
    ap.add_argument("jmap", type=Path)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--window-bytes", type=int, default=768)
    args = ap.parse_args()

    exe = args.executable.resolve()
    jmap_path = args.jmap.resolve()
    if not exe.is_file():
        raise SystemExit(f"executable not found: {exe}")
    if not jmap_path.is_file():
        raise SystemExit(f"JMAP not found: {jmap_path}")

    jmap_bytes = jmap_path.read_bytes()
    jmap = json.loads(jmap_bytes.decode("utf-8-sig"))
    objects = jmap.get("objects", {})
    vtables = jmap.get("vtables", {})
    if CALC not in objects or BASE not in objects or ROBO not in objects:
        raise SystemExit("JMAP is missing required CharacterMovement/Roboquest records")

    jmap_image_base = int(jmap["image_base_address"], 16)
    calc_va = int(objects[CALC]["func"], 16)
    calc_rva = calc_va - jmap_image_base
    base_vtable = objects[BASE].get("instance_vtable")
    robo_vtable = objects[ROBO].get("instance_vtable")
    base_entries = vtables.get(base_vtable, [])

    data = exe.read_bytes()
    pe_image_base, sections = read_pe_sections(data)
    file_offset = rva_to_file_offset(calc_rva, sections)
    window = data[file_offset:file_offset + args.window_bytes]
    if not window:
        raise SystemExit("CalcVelocity exec thunk window is empty")

    candidates = scan_indirect_calls(window)
    for row in candidates:
        slot = row["possible_vtable_slot"]
        row["slot_within_jmap_vtable"] = (
            slot is not None and slot < len(base_entries)
        )
        row["slot_function_va"] = (
            base_entries[slot]
            if row["slot_within_jmap_vtable"]
            else None
        )
        row["slot_function_rva"] = (
            int(row["slot_function_va"], 16) - jmap_image_base
            if row["slot_function_va"]
            else None
        )

    aligned = [
        row for row in candidates
        if row["slot_within_jmap_vtable"]
        and row["base_register"] is not None
        and row["index_register"] is None
    ]
    probable = aligned[0] if len(aligned) == 1 else None

    output = {
        "schema_version": 1,
        "input": {
            "executable_filename": exe.name,
            "executable_bytes": len(data),
            "executable_sha256": hashlib.sha256(data).hexdigest(),
            "jmap_filename": jmap_path.name,
            "jmap_sha256": hashlib.sha256(jmap_bytes).hexdigest(),
            "pe_image_base": hex(pe_image_base),
            "jmap_runtime_image_base": hex(jmap_image_base),
        },
        "calc_velocity": {
            "ufunction_path": CALC,
            "exec_thunk_va": hex(calc_va),
            "exec_thunk_rva": calc_rva,
            "exec_thunk_file_offset": file_offset,
            "window_bytes_scanned": len(window),
            "window_sha256": hashlib.sha256(window).hexdigest(),
        },
        "movement_vtables": {
            "character_movement_component": base_vtable,
            "roboquest_movement_component": robo_vtable,
            "same_instance_vtable": base_vtable == robo_vtable,
            "entry_count": len(base_entries),
        },
        "indirect_call_candidates": candidates,
        "probable_virtual_dispatch": probable,
        "notes": [
            "Only short candidate instruction/context hex snippets are emitted; the executable is not copied.",
            "The generated execCalcVelocity thunk is expected to contain a virtual call to CalcVelocity.",
            "A probable slot is only auto-selected when exactly one aligned in-range memory-indirect call is found.",
            "The runtime hook must still verify the expected executable hash and movement-component class before modifying behavior.",
        ],
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(json.dumps({
        "exec_thunk_rva": calc_rva,
        "candidate_count": len(candidates),
        "aligned_in_range_count": len(aligned),
        "probable_vtable_slot": probable["possible_vtable_slot"] if probable else None,
        "probable_slot_function_rva": probable["slot_function_rva"] if probable else None,
        "output": str(args.output),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
