#!/usr/bin/env python3
"""Targeted, read-only native-string probe for Roboquest Momentum.

The scanner never copies the game executable. It emits only hashes, basic PE metadata,
identifier/string hits, and bounded string neighborhoods around movement anchors.
This gives the reverse-engineering pass native reflection/name evidence without
redistributing Roboquest binaries.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

ANCHORS = (
    "RoboquestMovementComponent",
    "Character_Player",
    "OnStartDash",
    "PowerSlide",
    "SetJetpackActivate",
    "OnTriggerRocketJump",
    "OnTakeJumpad",
    "OnPressedJump",
    "ResetJump",
    "OnStartGrapple",
    "OnStopGrapple",
)

TARGET_TERMS = (
    "RoboquestMovementComponent",
    "Character_Player",
    "CharacterMovementComponent",
    "PhysWalking",
    "PhysFalling",
    "CalcVelocity",
    "PerformMovement",
    "StartNewPhysics",
    "OnMovementUpdated",
    "MoveAutonomous",
    "ReplicateMoveToServer",
    "ClientUpdatePositionAfterServerUpdate",
    "GetPredictionData_Client",
    "GetPredictionData_Server",
    "FSavedMove",
    "NetworkPredictionData",
    "UpdateFromCompressedFlags",
    "GetCompressedFlags",
    "AddInputVector",
    "ConsumeInputVector",
    "Velocity",
    "Acceleration",
    "GroundFriction",
    "BrakingFriction",
    "BrakingDecelerationWalking",
    "BrakingDecelerationFalling",
    "GravityScale",
    "AirControl",
    "MaxWalkSpeed",
    "MaxAcceleration",
    "OnStartDash",
    "EndDash",
    "PowerSlide",
    "DelegatePowerSlide",
    "SetJetpackActivate",
    "OnTriggerRocketJump",
    "Jumpad",
    "OnTakeJumpad",
    "OnJump",
    "ResetJump",
    "OnPressedJump",
    "Grapple",
)

IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_:./<>~?$@-]{3,}$")
ASCII_RE = re.compile(rb"[\x20-\x7e]{4,}")
UTF16_RE = re.compile(rb"(?<![\x20-\x7e])(?:[\x20-\x7e]\x00){4,}")

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def pe_metadata(data: bytes) -> dict:
    result = {"valid_pe": False}
    if len(data) < 0x40 or data[:2] != b"MZ":
        return result
    peoff = struct.unpack_from("<I", data, 0x3C)[0]
    if peoff + 24 > len(data) or data[peoff:peoff + 4] != b"PE\x00\x00":
        return result
    machine, sections, timestamp, _, _, opt_size, characteristics = struct.unpack_from(
        "<HHIIIHH", data, peoff + 4
    )
    entry_rva = None
    if peoff + 24 + opt_size <= len(data) and opt_size >= 20:
        entry_rva = struct.unpack_from("<I", data, peoff + 24 + 16)[0]
    result.update({
        "valid_pe": True,
        "machine": machine,
        "sections": sections,
        "coff_timestamp": timestamp,
        "coff_timestamp_utc": datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
            if timestamp else None,
        "optional_header_size": opt_size,
        "characteristics": characteristics,
        "entrypoint_rva": entry_rva,
    })
    return result

def strings_with_offsets(data: bytes) -> list[dict]:
    rows = []
    for match in ASCII_RE.finditer(data):
        try:
            text = match.group().decode("ascii")
        except UnicodeDecodeError:
            continue
        rows.append({"offset": match.start(), "encoding": "ascii", "text": text})
    for match in UTF16_RE.finditer(data):
        try:
            text = match.group().decode("utf-16le")
        except UnicodeDecodeError:
            continue
        rows.append({"offset": match.start(), "encoding": "utf16le", "text": text})
    rows.sort(key=lambda row: (row["offset"], row["encoding"]))
    return rows

def term_score(text: str) -> int:
    lower = text.lower()
    score = 0
    for term in TARGET_TERMS:
        if term.lower() in lower:
            score += 12 if term in ANCHORS else 5
    if IDENTIFIER_RE.match(text):
        score += 2
    if "/Script/RoboQuest" in text or "RoboQuest" in text:
        score += 3
    return score

def truncate(text: str, limit: int = 600) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "…"

def dedupe(rows: Iterable[dict]) -> list[dict]:
    out = []
    seen = set()
    for row in rows:
        key = (row["offset"], row["encoding"], row["text"])
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("executable", type=Path)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--neighborhood-bytes", type=int, default=65536)
    ap.add_argument("--max-neighborhood-strings", type=int, default=250)
    args = ap.parse_args()

    exe = args.executable.resolve()
    if not exe.is_file():
        raise SystemExit(f"game executable not found: {exe}")

    data = exe.read_bytes()
    rows = strings_with_offsets(data)

    target_hits = []
    for row in rows:
        lower = row["text"].lower()
        matched = [term for term in TARGET_TERMS if term.lower() in lower]
        if not matched:
            continue
        target_hits.append({
            **row,
            "text": truncate(row["text"]),
            "matched_terms": matched,
            "score": term_score(row["text"]),
        })
    target_hits.sort(key=lambda row: (-row["score"], row["offset"]))

    anchor_hits = []
    for anchor in ANCHORS:
        candidates = [row for row in rows if anchor.lower() in row["text"].lower()]
        for hit in candidates:
            lo = max(0, hit["offset"] - args.neighborhood_bytes)
            hi = min(len(data), hit["offset"] + args.neighborhood_bytes)
            near = []
            for row in rows:
                if row["offset"] < lo:
                    continue
                if row["offset"] > hi:
                    break
                score = term_score(row["text"])
                if score <= 0 and not IDENTIFIER_RE.match(row["text"]):
                    continue
                near.append({
                    **row,
                    "text": truncate(row["text"]),
                    "relative_offset": row["offset"] - hit["offset"],
                    "score": score,
                })
            near.sort(key=lambda row: (-row["score"], abs(row["relative_offset"]), row["offset"]))
            anchor_hits.append({
                "anchor": anchor,
                "hit_offset": hit["offset"],
                "encoding": hit["encoding"],
                "hit_text": truncate(hit["text"]),
                "window_start": lo,
                "window_end": hi,
                "candidate_strings": dedupe(near)[:args.max_neighborhood_strings],
            })

    output = {
        "schema_version": 1,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "input": {
            "filename": exe.name,
            "bytes": len(data),
            "sha256": sha256_bytes(data),
            "pe": pe_metadata(data),
        },
        "scan": {
            "ascii_utf16_string_count": len(rows),
            "target_hit_count": len(target_hits),
            "anchor_hit_count": len(anchor_hits),
            "neighborhood_bytes": args.neighborhood_bytes,
        },
        "target_hits": target_hits,
        "anchor_hits": anchor_hits,
        "notes": [
            "No executable bytes are embedded in this report.",
            "String proximity is research evidence, not proof that two symbols share a function.",
            "Absence of a string does not prove absence of a native function because optimized shipping builds may strip names.",
        ],
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "filename": exe.name,
        "bytes": len(data),
        "sha256": output["input"]["sha256"],
        "target_hits": len(target_hits),
        "anchor_hits": len(anchor_hits),
        "output": str(args.output),
    }, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
