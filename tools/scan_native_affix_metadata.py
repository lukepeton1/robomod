#!/usr/bin/env python3
"""Extract narrow Roboquest native-affix metadata strings from shipping binaries.

Purpose
-------
Cooked Blueprint bytecode proves AWeaponAffix is used as a non-world UObject
reference, but the collected assets do not reference the native AWeapon field
that owns the live affix instances. Unreal reflection names and UFUNCTION/
UPROPERTY identifiers are commonly present as strings in the shipping binary.

This tool deliberately does NOT copy or dump executable bytes. It emits only a
small, filtered set of printable strings and nearby identifier-like strings
around Weapon Foundry ownership terms.

The output is safe to hand back as a small JSON research artifact.
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ASCII_RE = re.compile(rb"[\x20-\x7e]{4,}")
UTF16_RE = re.compile(rb"(?:[\x20-\x7e]\x00){4,}")

ANCHOR_RE = re.compile(
    r"(?:"
    r"AWeaponAffix|WeaponAffix|Affix|"
    r"WeaponStatManager|WeaponSkillManager|"
    r"CurrentAffixBundle|AffixAmount|WeaponRef|"
    r"Enchanted|RerollRandomAffixes|"
    r"WeaponAffixRowHandle|WeaponAffixBundleRowHandle|"
    r"LoadedAffix|PickedAffixes|RandomAffixes"
    r")",
    re.IGNORECASE,
)

IDENTIFIER_RE = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_:$<>./-]{2,159}$"
)

HIGH_VALUE_EXACT = {
    "Affix",
    "Affixes",
    "AffixAmount",
    "AffixRow",
    "AffixRows",
    "AppliedAffixes",
    "CurrentAffixBundle",
    "EnchantedAffix",
    "EnchantedAffixes",
    "GetAffix",
    "GetAffixes",
    "GetCurrentEnchantedAffixRowName",
    "LoadedAffix",
    "PickedAffixes",
    "RandomAffixes",
    "WeaponAffix",
    "WeaponAffixes",
    "WeaponAffixRowHandle",
    "WeaponAffixBundleRowHandle",
    "WeaponRef",
    "WeaponSkillManager",
    "WeaponStatManager",
}


@dataclass(frozen=True)
class FoundString:
    offset: int
    encoding: str
    value: str


def printable_strings(data: bytes) -> list[FoundString]:
    found: list[FoundString] = []
    for match in ASCII_RE.finditer(data):
        try:
            value = match.group().decode("ascii")
        except UnicodeDecodeError:
            continue
        found.append(FoundString(match.start(), "ascii", value))

    for match in UTF16_RE.finditer(data):
        try:
            value = match.group().decode("utf-16le")
        except UnicodeDecodeError:
            continue
        found.append(FoundString(match.start(), "utf16le", value))

    found.sort(key=lambda row: (row.offset, row.encoding, row.value))
    return found


def candidate_binaries(root: Path) -> list[Path]:
    if root.is_file():
        return [root]

    preferred = sorted(root.rglob("RoboQuest-Win64-Shipping.exe"))
    preferred += sorted(root.rglob("RoboQuest.exe"))
    preferred += sorted(root.rglob("*RoboQuest*.dll"))

    unique: list[Path] = []
    seen: set[Path] = set()
    for path in preferred:
        resolved = path.resolve()
        if resolved not in seen and path.is_file():
            unique.append(path)
            seen.add(resolved)
    return unique


def context_identifiers(
    strings: list[FoundString],
    index: int,
    radius: int,
) -> list[dict]:
    start = max(0, index - radius)
    end = min(len(strings), index + radius + 1)
    out = []
    for row in strings[start:end]:
        value = row.value.strip()
        if (
            IDENTIFIER_RE.fullmatch(value)
            or ANCHOR_RE.search(value)
        ):
            out.append({
                "offset": row.offset,
                "encoding": row.encoding,
                "value": value,
            })
    return out


def scan_file(path: Path, radius: int) -> dict:
    data = path.read_bytes()
    strings = printable_strings(data)

    hits = []
    exact_hits: dict[str, list[dict]] = {}
    for index, row in enumerate(strings):
        value = row.value.strip()
        if not ANCHOR_RE.search(value):
            continue

        record = {
            "offset": row.offset,
            "encoding": row.encoding,
            "value": value,
            "context": context_identifiers(strings, index, radius),
        }
        hits.append(record)

        if value in HIGH_VALUE_EXACT:
            exact_hits.setdefault(value, []).append({
                "offset": row.offset,
                "encoding": row.encoding,
            })

    unique_values = sorted({
        row.value.strip()
        for row in strings
        if ANCHOR_RE.search(row.value)
        and len(row.value.strip()) <= 200
    })

    return {
        "path": str(path),
        "bytes": len(data),
        "printable_string_count": len(strings),
        "anchor_hit_count": len(hits),
        "high_value_exact_hits": exact_hits,
        "unique_anchor_values": unique_values,
        "hits": hits,
    }


def summarize(files: Iterable[dict]) -> dict:
    exact: dict[str, int] = {}
    unique: set[str] = set()
    for file in files:
        unique.update(file["unique_anchor_values"])
        for name, rows in file["high_value_exact_hits"].items():
            exact[name] = exact.get(name, 0) + len(rows)

    return {
        "files_scanned": len(list(files)) if not isinstance(files, list) else len(files),
        "high_value_exact_counts": dict(sorted(exact.items())),
        "unique_anchor_value_count": len(unique),
        "notable_affix_identifiers": sorted(
            value
            for value in unique
            if (
                "affix" in value.lower()
                or value in {"WeaponStatManager", "WeaponSkillManager", "WeaponRef"}
            )
            and len(value) <= 120
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "binary_root",
        type=Path,
        help="Roboquest Binaries/Win64 directory or a specific shipping binary",
    )
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--context-radius", type=int, default=12)
    args = ap.parse_args()

    paths = candidate_binaries(args.binary_root)
    if not paths:
        raise SystemExit(
            f"No Roboquest shipping executable/DLL found below: {args.binary_root}"
        )

    results = [scan_file(path, max(1, args.context_radius)) for path in paths]
    payload = {
        "schema_version": 1,
        "name": "weapon-foundry-native-affix-metadata",
        "purpose": "discover exact native AWeapon/AWeaponAffix owner/container identifiers without sharing executable bytes",
        "binary_root": str(args.binary_root),
        "summary": summarize(results),
        "files": results,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(payload["summary"], indent=2, ensure_ascii=False))
    print()
    print(f"Wrote: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
