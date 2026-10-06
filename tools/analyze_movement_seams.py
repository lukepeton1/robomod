#!/usr/bin/env python3
"""Analyze Roboquest movement architecture from committed FModel JSON and raw handoff JSON.

The static vanilla-json corpus is intentionally scanned before asking for more local game
content. When a movement handoff is supplied, the same report is enriched with UAssetAPI
FunctionExport / native-import evidence so we can decide whether Momentum can remain a
cooked PAK patch or needs a minimal runtime extension.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VANILLA = REPO_ROOT / "vanilla-json" / "RoboQuest" / "Content"
DEFAULT_MANIFEST = REPO_ROOT / "Source" / "manifests" / "movement_patch_targets.txt"
DEFAULT_OUTPUT = REPO_ROOT / "research" / "generated" / "movement_seams.json"
DEFAULT_COMPAT = REPO_ROOT / "research" / "generated" / "movement_compatibility.json"

TOKEN_WEIGHTS = {
    "roboquestmovementcomponent": 30,
    "character_player": 16,
    "powerslide": 16,
    "rocketjump": 14,
    "grapple": 12,
    "jetpack": 12,
    "dash": 11,
    "jumpad": 10,
    "jump": 5,
    "crouch": 7,
    "sprint": 6,
    "movespeed": 8,
    "movement": 5,
    "velocity": 8,
    "aircontrol": 10,
    "gravity": 5,
    "falling": 5,
    "grounded": 6,
    "landed": 5,
    "impulse": 7,
    "launch": 5,
    "friction": 7,
    "acceleration": 8,
    "braking": 6,
    "walkablefloor": 8,
    "maxstepsheight": 4,
    "maxstepheight": 6,
    "predict": 6,
}

CATEGORY_TERMS = {
    "core_player": ("bp_aplayer", "roboquestmovementcomponent", "character_player"),
    "controller_input": ("playercontroller", "inputaction", "playeractions", "sprint"),
    "dash": ("dash",),
    "power_slide": ("powerslide", "slide"),
    "grapple": ("grapple",),
    "jetpack": ("jetpack",),
    "rocket_jump": ("rocketjump", "rocket jump"),
    "jump_pad": ("jumpad", "jump pad"),
    "jump_progression": ("triplejump", "addjump", "jumpmaxcount", "jumpzvelocity"),
    "speed_modifier": ("movespeed", "bonusmovespeed", "bonusspeed"),
    "ground_air_semantics": ("grounded", "airborne", "landed", "falling"),
    "movement_physics": ("velocity", "friction", "acceleration", "aircontrol", "gravity", "walkablefloor"),
    "camera_feedback": ("dashfov", "fov", "cameralag"),
    "network_prediction": ("predict", "replicatemovement", "replicatedmovement"),
}

CORE_PACKAGES = {
    "Blueprint/Player/BP_APlayer",
    "Blueprint/Player/BP_APlayerController",
    "Blueprint/Player/BP_AGamePlayerController",
    "Blueprint/Player/BP_IngamePlayerController",
    "Blueprint/Skill/Ability/BP_PS_Dash",
    "Blueprint/Item/Common/BP_PowerSlideSkill",
    "Blueprint/Upgrade/Artefact/BP_Grapple",
    "Blueprint/Upgrade/Artefact/BP_Jetpack",
    "Blueprint/Skill/Mod/BP_WS_RocketJump",
    "Blueprint/Interactive/Level/BP_Jumpad",
}

MOVEMENT_NAME_RE = re.compile(
    r"(move|movement|speed|dash|slide|power|grapple|jet|rocket|jump|crouch|sprint|"
    r"velocity|gravity|ground|fall|air|floor|step|walk|predict|impulse|launch|land|"
    r"friction|brak|acceler|control|capsule|wall|slope|headbonk|stomp)",
    re.IGNORECASE,
)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def walk(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def stringify(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def score_text(text: str) -> int:
    lower = text.lower()
    score = 0
    for token, weight in TOKEN_WEIGHTS.items():
        # Cap occurrence contribution so huge Blueprints do not dominate purely by size.
        score += min(lower.count(token), 5) * weight
    return score


def classify_text(text: str) -> list[str]:
    lower = text.lower()
    return [name for name, terms in CATEGORY_TERMS.items() if any(term in lower for term in terms)]


def package_from_fmodel(path: Path, root: Path) -> str:
    rel = path.relative_to(root).as_posix()
    return rel[:-5] if rel.endswith(".json") else rel


def find_parent(objects: list[dict[str, Any]]) -> str | None:
    for obj in objects:
        if obj.get("Type") != "BlueprintGeneratedClass":
            continue
        parent = obj.get("Super") or obj.get("SuperStruct")
        if isinstance(parent, dict):
            return parent.get("ObjectName") or parent.get("ObjectPath")
        if parent:
            return str(parent)
    return None


def find_cdo(objects: list[dict[str, Any]]) -> dict[str, Any] | None:
    for obj in objects:
        flags = str(obj.get("Flags", ""))
        name = str(obj.get("Name", ""))
        if "RF_ClassDefaultObject" in flags or name.startswith("Default__"):
            return obj
    return None


def relevant_properties(props: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in props.items():
        if MOVEMENT_NAME_RE.search(str(key)) or MOVEMENT_NAME_RE.search(stringify(value)):
            out[key] = value
    return out


def compact_object_ref(value: dict[str, Any]) -> str | None:
    name = value.get("ObjectName")
    path = value.get("ObjectPath")
    if name and path:
        return f"{name} @ {path}"
    return str(name or path) if (name or path) else None


def analyze_fmodel(path: Path, root: Path, raw_text: str | None = None) -> dict[str, Any]:
    text = raw_text if raw_text is not None else path.read_text(encoding="utf-8-sig")
    data = json.loads(text)
    objects = data if isinstance(data, list) else [data]
    flat = list(walk(data))

    functions = sorted({
        str(obj.get("Name"))
        for obj in flat
        if obj.get("Type") == "Function"
        and obj.get("Name")
        and MOVEMENT_NAME_RE.search(str(obj.get("Name")))
    })

    native_refs = []
    seen_refs = set()
    for obj in flat:
        path_value = str(obj.get("ObjectPath", ""))
        if not path_value.startswith("/Script/RoboQuest"):
            continue
        ref = compact_object_ref(obj)
        if ref and ref not in seen_refs:
            seen_refs.add(ref)
            native_refs.append(ref)

    cdo = find_cdo(objects)
    cdo_props = relevant_properties(cdo.get("Properties", {})) if cdo else {}

    movement_components = []
    for obj in flat:
        type_name = str(obj.get("Type", ""))
        class_name = str(obj.get("Class", ""))
        if "RoboquestMovementComponent" not in (type_name + " " + class_name):
            continue
        movement_components.append({
            "type": type_name,
            "name": obj.get("Name"),
            "class": obj.get("Class"),
            "properties": relevant_properties(obj.get("Properties", {})),
        })

    package = package_from_fmodel(path, root)
    score = score_text(text)
    if package in CORE_PACKAGES:
        score += 100

    return {
        "package": package,
        "score": score,
        "categories": classify_text(text + " " + package),
        "parent": find_parent(objects),
        "functions": functions,
        "cdo_movement_properties": cdo_props,
        "movement_components": movement_components,
        "native_roboquest_refs": native_refs[:100],
    }


def scan_vanilla(root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    reports: list[dict[str, Any]] = []
    errors: list[str] = []
    for path in sorted(root.rglob("*.json")):
        try:
            text = path.read_text(encoding="utf-8-sig")
        except Exception as exc:
            errors.append(f"{path}: read failed: {exc}")
            continue
        package = package_from_fmodel(path, root)
        rough_score = score_text(text)
        if rough_score < 8 and package not in CORE_PACKAGES:
            continue
        try:
            reports.append(analyze_fmodel(path, root, raw_text=text))
        except Exception as exc:
            errors.append(f"{path}: parse failed: {exc}")
    reports.sort(key=lambda item: (-int(item["score"]), str(item["package"])))
    return reports, errors


def read_manifest(path: Path) -> list[str]:
    result = []
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            result.append(line)
    return result


def symbol_names(value: Any) -> list[str]:
    names: list[str] = []
    for obj in walk(value):
        name = obj.get("Name")
        if isinstance(name, str) and MOVEMENT_NAME_RE.search(name):
            names.append(name)
        object_name = obj.get("ObjectName")
        if isinstance(object_name, str) and MOVEMENT_NAME_RE.search(object_name):
            names.append(object_name)
    return sorted(set(names))


def scan_handoff(handoff: Path) -> dict[str, Any]:
    json_root = handoff / "uassetapi-json" / "RoboQuest" / "Content"
    manifest_path = handoff / "handoff-manifest.json"
    result: dict[str, Any] = {
        "present": handoff.is_dir(),
        "json_root": str(json_root),
        "packages": [],
        "errors": [],
    }
    if not handoff.is_dir():
        return result

    if manifest_path.is_file():
        try:
            result["collector_manifest"] = load_json(manifest_path)
        except Exception as exc:
            result["errors"].append(f"invalid collector manifest: {exc}")

    if not json_root.is_dir():
        result["errors"].append("UAssetAPI JSON root missing")
        return result

    for path in sorted(json_root.rglob("*.json")):
        try:
            data = load_json(path)
        except Exception as exc:
            result["errors"].append(f"{path}: {exc}")
            continue
        rel = path.relative_to(json_root).as_posix()
        package = rel[:-5] if rel.endswith(".json") else rel
        function_exports = 0
        decoded = 0
        raw_fallback = 0
        native_refs = []
        for obj in walk(data):
            type_name = str(obj.get("$type", ""))
            if "FunctionExport" in type_name:
                function_exports += 1
                if isinstance(obj.get("ScriptBytecode"), list):
                    decoded += 1
                if obj.get("ScriptBytecodeRaw"):
                    raw_fallback += 1
            object_path = str(obj.get("ObjectPath", ""))
            if object_path.startswith("/Script/RoboQuest"):
                ref = compact_object_ref(obj)
                if ref:
                    native_refs.append(ref)

        result["packages"].append({
            "package": package,
            "function_exports": function_exports,
            "decoded_function_exports": decoded,
            "raw_fallback_function_exports": raw_fallback,
            "movement_symbols": symbol_names(data)[:200],
            "native_roboquest_refs": sorted(set(native_refs))[:200],
        })

    return result


def by_package(reports: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(item["package"]): item for item in reports}


def architecture_signals(reports: list[dict[str, Any]]) -> list[str]:
    lookup = by_package(reports)
    player = lookup.get("Blueprint/Player/BP_APlayer")
    signals: list[str] = []
    if not player:
        return ["BP_APlayer was not found in the static movement scan."]

    components = player.get("movement_components") or []
    if components:
        signals.append("BP_APlayer owns a native RoboquestMovementComponent (CharMoveComp).")
        props = components[0].get("properties") or {}
        zero_keys = [
            key for key in ("GravityScale", "JumpZVelocity", "MaxWalkSpeed", "MaxAcceleration", "AirControl")
            if props.get(key) == 0
        ]
        if zero_keys:
            signals.append(
                "Stock CharacterMovement tuning is not the primary integrator: "
                + ", ".join(zero_keys)
                + " are zero on the cooked player movement component."
            )
    cdo = player.get("cdo_movement_properties") or {}
    if cdo.get("bMovementPredict") is True:
        signals.append("BP_APlayer enables bMovementPredict; prediction/authority must be preserved.")
    if cdo.get("bReplicateMovement") is False:
        signals.append("BP_APlayer has bReplicateMovement=false; do not design around generic actor transform replication.")
    return signals


def build_reports(
    vanilla_root: Path,
    manifest_path: Path,
    handoff: Path | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    reports, errors = scan_vanilla(vanilla_root)
    targets = read_manifest(manifest_path)
    lookup = by_package(reports)
    handoff_report = scan_handoff(handoff) if handoff else {"present": False, "packages": [], "errors": []}
    collected = {str(item.get("package")) for item in handoff_report.get("packages", [])}

    missing_static = [target for target in targets if not (vanilla_root / f"{target}.json").is_file()]
    missing_handoff = [target for target in targets if target not in collected] if handoff else targets

    core = [lookup[p] for p in CORE_PACKAGES if p in lookup]
    core.sort(key=lambda item: item["package"])

    seams = {
        "schema_version": 1,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "vanilla_root": str(vanilla_root),
        "manifest": str(manifest_path),
        "movement_candidate_count": len(reports),
        "static_scan_errors": errors,
        "manifest_target_count": len(targets),
        "manifest_targets_missing_static_json": missing_static,
        "architecture_signals": architecture_signals(reports),
        "core_packages": core,
        "top_candidates": reports[:200],
        "handoff": handoff_report,
        "manifest_targets_missing_handoff_json": missing_handoff,
        "next_gate": (
            "Inspect UAssetAPI bytecode/native imports for BP_APlayer and CharMoveComp call sites, "
            "then decide PAK-only versus minimal runtime extension. Do not implement the full "
            "Source-style integrator until that seam is proven."
        ),
    }

    compatibility = {
        "schema_version": 1,
        "generated_utc": seams["generated_utc"],
        "asset_count": len(reports),
        "families": {
            category: sum(category in item["categories"] for item in reports)
            for category in CATEGORY_TERMS
        },
        "assets": reports,
    }
    return seams, compatibility


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vanilla-root", type=Path, default=DEFAULT_VANILLA)
    ap.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    ap.add_argument("--handoff", type=Path, default=None)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument("--compat-output", type=Path, default=DEFAULT_COMPAT)
    args = ap.parse_args()

    vanilla_root = args.vanilla_root.resolve()
    manifest = args.manifest.resolve()
    if not vanilla_root.is_dir():
        raise SystemExit(f"vanilla root not found: {vanilla_root}")
    if not manifest.is_file():
        raise SystemExit(f"movement manifest not found: {manifest}")

    seams, compatibility = build_reports(
        vanilla_root=vanilla_root,
        manifest_path=manifest,
        handoff=args.handoff.resolve() if args.handoff else None,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.compat_output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(seams, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    args.compat_output.write_text(
        json.dumps(compatibility, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(json.dumps({
        "movement_candidates": seams["movement_candidate_count"],
        "manifest_targets": seams["manifest_target_count"],
        "static_missing": seams["manifest_targets_missing_static_json"],
        "handoff_missing": len(seams["manifest_targets_missing_handoff_json"]),
        "architecture_signals": seams["architecture_signals"],
        "output": str(args.output),
        "compatibility_output": str(args.compat_output),
    }, indent=2))
    return 1 if seams["manifest_targets_missing_static_json"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
