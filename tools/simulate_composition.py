#!/usr/bin/env python3
"""Reference structural simulator for Weapon Foundry composition semantics.

This is deliberately not a damage simulator. It validates provenance, inheritance,
hit-model resolution and child-event topology before the same rules are implemented in
cooked Roboquest assets.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable

DEFAULT_RULES = Path("Source/composition/composition_rules.json")


@dataclass(frozen=True)
class Modifier:
    effect: str
    row: str
    instance_id: str


@dataclass
class Event:
    id: int
    parent_id: int | None
    kind: str
    depth: int
    source_modifier: str | None
    consumed: tuple[str, ...]
    active_effects: tuple[str, ...]
    hit_type: str
    seed: int


def load_rules(path: Path = DEFAULT_RULES) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def row_to_effect(rules: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for effect, cfg in rules["effects"].items():
        for row in cfg.get("row_ids", []):
            out[row] = effect
    return out


def make_modifiers(rows: Iterable[str], rules: dict) -> list[Modifier]:
    lookup = row_to_effect(rules)
    counts: dict[str, int] = {}
    result: list[Modifier] = []
    for row in rows:
        if row not in lookup:
            raise ValueError(f"Unknown composition row: {row}")
        effect = lookup[row]
        ordinal = counts.get(row, 0)
        counts[row] = ordinal + 1
        result.append(Modifier(effect=effect, row=row, instance_id=f"{row}#{ordinal}"))
    return result


def stable_seed(*parts: object) -> int:
    blob = "|".join(str(x) for x in parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(blob).digest()[:8], "little")


def resolve_hit_type(base_hit_type: str, modifiers: list[Modifier], rules: dict) -> tuple[str, list[str]]:
    effects = {m.effect for m in modifiers}
    hit_type = base_hit_type
    conversions: list[str] = []
    for conv in rules.get("hit_model_resolver", {}).get("conversions", []):
        when = conv.get("when", {})
        if hit_type == when.get("source_hit_type") and when.get("requires_effect") in effects:
            target = conv["target_hit_type"]
            conversions.append(f"{hit_type}->{target} for {when.get('requires_effect')}")
            hit_type = target
    # Explicit shipped Hitscan remains an intentional projectile -> raycast conversion.
    if "Hitscan" in effects and hit_type == "EHitType::Projectile":
        conversions.append("EHitType::Projectile->EHitType::Raycast for Hitscan")
        hit_type = "EHitType::Raycast"
    # If both are present, Seeker has physical meaning only with travel time. The
    # composition resolver gives that requirement precedence over the optional Hitscan
    # conversion instead of silently leaving Seeker inert.
    if "Homing" in effects and hit_type == "EHitType::Raycast":
        conversions.append("EHitType::Raycast->EHitType::Projectile to preserve Seeker")
        hit_type = "EHitType::Projectile"
    return hit_type, conversions


def buckshot_pellet_count(modifiers: list[Modifier], rules: dict) -> int:
    instances = [m for m in modifiers if m.effect == "Buckshot"]
    if not instances:
        return 1
    cfg = rules["effects"]["Buckshot"]
    extra = int(cfg.get("simulator_extra_pellets_per_instance", 2))
    return 1 + extra * len(instances)


def simulate(
    rows: list[str],
    *,
    base_hit_type: str = "EHitType::Projectile",
    root_seed: int = 1,
    rules: dict | None = None,
) -> dict:
    rules = rules or load_rules()
    mods = make_modifiers(rows, rules)
    hit_type, conversions = resolve_hit_type(base_hit_type, mods, rules)
    max_depth = int(rules["guards"]["max_generation_depth"])
    max_events = int(rules["guards"]["max_events_per_root_trigger"])
    pellet_count = buckshot_pellet_count(mods, rules)
    all_effects = tuple(m.effect for m in mods)

    events: list[Event] = []
    queue: list[tuple[int | None, str, int, frozenset[str], str | None, int]] = [
        (None, "trigger_pull", 0, frozenset(), None, root_seed)
    ]

    def available(effect: str, consumed: frozenset[str]) -> list[Modifier]:
        return [m for m in mods if m.effect == effect and m.instance_id not in consumed]

    def enqueue(
        parent: Event,
        kind: str,
        consumed: frozenset[str],
        source: Modifier | None,
        child_index: int,
    ) -> None:
        if parent.depth >= max_depth or len(events) + len(queue) >= max_events:
            return
        seed = stable_seed(parent.seed, source.instance_id if source else "native", child_index, kind)
        queue.append((parent.id, kind, parent.depth + 1, consumed, source.instance_id if source else None, seed))

    while queue and len(events) < max_events:
        parent_id, kind, depth, consumed, source_modifier, seed = queue.pop(0)
        ev = Event(
            id=len(events),
            parent_id=parent_id,
            kind=kind,
            depth=depth,
            source_modifier=source_modifier,
            consumed=tuple(sorted(consumed)),
            active_effects=all_effects,
            hit_type=hit_type,
            seed=seed,
        )
        events.append(ev)

        if kind in {"trigger_pull", "duplicate_shot"}:
            # Each Freewheel instance can independently duplicate a complete shot, but
            # the instance that made a branch cannot make itself again in that ancestry.
            for i, m in enumerate(available("Freewheel", consumed)):
                enqueue(ev, "duplicate_shot", consumed | {m.instance_id}, m, i)

            # Buckshot is a resolved shot-shape transformation, not a recursive proc.
            if pellet_count > 1:
                for i in range(pellet_count):
                    enqueue(ev, "pellet", consumed, None, i)
            else:
                enqueue(ev, "projectile_or_raycast", consumed, None, 0)

        elif kind in {"pellet", "projectile_or_raycast", "fragment"}:
            impact_kind = "fragment_impact" if kind == "fragment" else "impact"
            enqueue(ev, impact_kind, consumed, None, 0)

        elif kind in {"impact", "pierce_hit", "ricochet_hit", "fragment_impact"}:
            for i, m in enumerate(available("Explosive", consumed)):
                enqueue(ev, "explosion", consumed | {m.instance_id}, m, i)

            for i, m in enumerate(available("Fragmentation", consumed)):
                cfg = rules["effects"]["Fragmentation"]
                if kind not in cfg.get("trigger_event_kinds", []):
                    continue
                count = int(cfg.get("simulator_children_per_proc", 3))
                for child in range(count):
                    enqueue(ev, "fragment", consumed | {m.instance_id}, m, i * count + child)

            for i, m in enumerate(available("Ricochet", consumed)):
                cfg = rules["effects"]["Ricochet"]
                if kind in cfg.get("trigger_event_kinds", []):
                    enqueue(ev, "ricochet_hit", consumed | {m.instance_id}, m, i)

    truncated = bool(queue)
    return {
        "build_rows": rows,
        "modifiers": [asdict(x) for x in mods],
        "base_hit_type": base_hit_type,
        "resolved_hit_type": hit_type,
        "conversions": conversions,
        "resolved_pellet_count": pellet_count,
        "event_count": len(events),
        "truncated_by_guard": truncated,
        "events": [asdict(x) for x in events],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", required=True, help="Comma-separated DT_WeaponAffix row IDs")
    ap.add_argument("--hit-type", default="EHitType::Projectile")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--rules", type=Path, default=DEFAULT_RULES)
    ap.add_argument("--summary", action="store_true")
    args = ap.parse_args()
    rows = [x.strip() for x in args.build.split(",") if x.strip()]
    result = simulate(rows, base_hit_type=args.hit_type, root_seed=args.seed, rules=load_rules(args.rules))
    if args.summary:
        kinds: dict[str, int] = {}
        for e in result["events"]:
            kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
        print(json.dumps({
            k: result[k] for k in (
                "build_rows", "base_hit_type", "resolved_hit_type", "conversions",
                "resolved_pellet_count", "event_count", "truncated_by_guard"
            )
        } | {"event_kinds": kinds}, indent=2))
    else:
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
