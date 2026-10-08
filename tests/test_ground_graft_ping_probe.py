import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from kismet_layout import script_size  # noqa: E402
from patch_ground_graft_ping_probe import patch, verify  # noqa: E402


def imp(name, outer=-3, class_name="Object"):
    return {
        "$type": "UAssetAPI.Import, UAssetAPI",
        "ObjectName": name,
        "OuterIndex": outer,
        "ClassPackage": "/Script/CoreUObject",
        "ClassName": class_name,
        "PackageName": None,
        "bImportOptional": False,
    }


def ptr(owner, name):
    return {
        "$type": "UAssetAPI.Kismet.Bytecode.KismetPropertyPointer, UAssetAPI",
        "New": {
            "$type": "UAssetAPI.UnrealTypes.FFieldPath, UAssetAPI",
            "Path": [name],
            "ResolvedOwner": owner,
        },
    }


def local(owner, name):
    return {
        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_LocalVariable, UAssetAPI",
        "Variable": ptr(owner, name),
    }


def fixture():
    # Three package imports first so ordinary Roboquest class/function imports can
    # use /Script/RoboQuest as their outer in a shape matching cooked assets.
    imports = [
        imp("/Script/CoreUObject", outer=0, class_name="Package"),
        imp("/Script/Engine", outer=0, class_name="Package"),
        imp("/Script/RoboQuest", outer=0, class_name="Package"),
    ]
    imports.extend([
        imp("AInteractiveWeapon", class_name="Class"),
        imp("AWeapon", class_name="Class"),
        imp("Character_Player", class_name="Class"),
        imp("Actor", outer=-2, class_name="Class"),
        imp("KismetArrayLibrary", outer=-2, class_name="Class"),
        imp("Default__KismetArrayLibrary", outer=-2, class_name="KismetArrayLibrary"),
        imp("KismetMathLibrary", outer=-2, class_name="Class"),
        imp("Array_Contains", outer=-8),
        imp("Less_IntInt", outer=-10),
        imp("Conv_ByteToInt", outer=-10),
        imp("Add_IntInt", outer=-10),
        imp("Subtract_IntInt", outer=-10),
        imp("GreaterEqual_IntInt", outer=-10),
        imp("NotEqual_ObjectObject", outer=-10),
        imp("RemoveTicket", outer=-6),
        imp("AddTicket", outer=-6),
    ])

    uber_code = [
        {"$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_EndOfScript, UAssetAPI"}
    ]
    uber = {
        "$type": "UAssetAPI.ExportTypes.FunctionExport, UAssetAPI",
        "ObjectName": "ExecuteUbergraph_BP_APlayer",
        "LoadedProperties": [],
        "ScriptBytecode": uber_code,
        "ScriptBytecodeRaw": None,
        "ScriptBytecodeSize": script_size(uber_code),
    }

    owner = 2
    ping_code = [
        {
            "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_LetValueOnPersistentFrame, UAssetAPI",
            "DestinationProperty": ptr(owner, "ActorRef"),
            "AssignmentExpression": local(owner, "ActorRef"),
        },
        {
            "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_LetValueOnPersistentFrame, UAssetAPI",
            "DestinationProperty": ptr(owner, "Location"),
            "AssignmentExpression": local(owner, "Location"),
        },
        {
            "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_LocalFinalFunction, UAssetAPI",
            "StackNode": 1,
            "Parameters": [
                {
                    "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_IntConst, UAssetAPI",
                    "Value": 58450,
                }
            ],
        },
        {
            "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_EndOfScript, UAssetAPI",
        },
    ]
    ping = {
        "$type": "UAssetAPI.ExportTypes.FunctionExport, UAssetAPI",
        "ObjectName": "OnServerPingActor",
        "LoadedProperties": [
            {
                "$type": "UAssetAPI.FieldTypes.FObjectProperty, UAssetAPI",
                "PropertyClass": -7,
                "ArrayDim": "TArray",
                "ElementSize": 8,
                "PropertyFlags": "CPF_Parm",
                "RepIndex": 0,
                "RepNotifyFunc": "None",
                "BlueprintReplicationCondition": "COND_None",
                "RawValue": None,
                "SerializedType": "ObjectProperty",
                "Name": "ActorRef",
                "Flags": "RF_Public",
                "MetaDataMap": None,
            },
            {
                "$type": "UAssetAPI.FieldTypes.FGenericProperty, UAssetAPI",
                "ArrayDim": "TArray",
                "ElementSize": 12,
                "PropertyFlags": "CPF_Parm",
                "RepIndex": 0,
                "RepNotifyFunc": "None",
                "BlueprintReplicationCondition": "COND_None",
                "RawValue": None,
                "SerializedType": "StructProperty",
                "Name": "Location",
                "Flags": "RF_Public",
                "MetaDataMap": None,
            },
        ],
        "ScriptBytecode": ping_code,
        "ScriptBytecodeRaw": None,
        "ScriptBytecodeSize": script_size(ping_code),
    }

    return {
        "NameMap": [entry["ObjectName"] for entry in imports]
        + ["ExecuteUbergraph_BP_APlayer", "OnServerPingActor", "ActorRef", "Location"],
        "NamesReferencedFromExportDataCount": len(imports) + 4,
        "Imports": imports,
        "Exports": [uber, ping],
    }


def spec():
    return {
        "selection": {
            "candidates": [
                {
                    "row": "Fragmentation",
                    "base_cost": 4,
                    "rarity": "EWeaponAffixRarity::Rare",
                    "core_composition": True,
                },
                {
                    "row": "Bounce",
                    "base_cost": 2,
                    "rarity": "EWeaponAffixRarity::Common",
                    "core_composition": True,
                },
            ]
        },
        "free_complexity_affixes": 2,
    }


class GroundGraftPingPatchTests(unittest.TestCase):
    def test_server_ping_patch_keeps_vanilla_fallthrough_and_transaction_order(self):
        patched, report = patch(fixture(), spec())
        result = verify(patched, spec())

        self.assertTrue(result["verified"])
        self.assertTrue(result["vanilla_ping_fallthrough"])
        self.assertEqual(result["candidate_rows"], ["Fragmentation", "Bounce"])
        self.assertEqual(result["authoritative_donor_rows"], "AAWeapon.GetAffixRowNames()")
        self.assertEqual(result["mutation"], "AddEnchantedAffix")
        self.assertEqual(result["currency"], "RemoveTicket/AddTicket")
        self.assertIn("K2_DestroyActor", result["donor_consume"])
        self.assertEqual(report["insertion_index"], 2)

        fn = next(x for x in patched["Exports"] if x["ObjectName"] == "OnServerPingActor")
        self.assertEqual(script_size(fn["ScriptBytecode"]), fn["ScriptBytecodeSize"])

    def test_patch_uses_typed_native_row_arrays(self):
        patched, _ = patch(fixture(), spec())
        fn = next(x for x in patched["Exports"] if x["ObjectName"] == "OnServerPingActor")
        props = {p["Name"]: p for p in fn["LoadedProperties"]}

        for name in ("WF_DonorRows", "WF_TargetRows"):
            self.assertEqual(props[name]["SerializedType"], "ArrayProperty")
            self.assertEqual(props[name]["Inner"]["SerializedType"], "NameProperty")

        self.assertEqual(props["WF_SelectedRow"]["SerializedType"], "NameProperty")
        self.assertEqual(props["WF_TotalCost"]["SerializedType"], "IntProperty")
        self.assertEqual(props["WF_TargetValid"]["SerializedType"], "BoolProperty")

    def test_injected_reflected_names_are_registered(self):
        patched, _ = patch(fixture(), spec())
        names = set(patched["NameMap"])
        for name in (
            "SpawnedWeapon",
            "currentWeapon",
            "CurrentAffixBundle",
            "AffixAmount",
            "CurrentTicket",
            "Color",
            "AddEnchantedAffix",
        ):
            self.assertIn(name, names)

    def test_all_kismet_field_path_names_are_registered(self):
        patched, _ = patch(fixture(), spec())
        names = set(patched["NameMap"])
        paths = set()

        def walk(value):
            if isinstance(value, dict):
                if value.get("$type", "").endswith("FFieldPath, UAssetAPI"):
                    for segment in value.get("Path") or []:
                        if isinstance(segment, str):
                            paths.add(segment)
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)

        fn = next(x for x in patched["Exports"] if x["ObjectName"] == "OnServerPingActor")
        walk(fn["ScriptBytecode"])
        self.assertFalse(paths - names, msg=f"unregistered FFieldPath names: {sorted(paths - names)}")

    def test_patch_keeps_normal_ping_for_non_weapon_or_validation_failure(self):
        patched, _ = patch(fixture(), spec())
        fn = next(x for x in patched["Exports"] if x["ObjectName"] == "OnServerPingActor")

        dispatches = [
            expr
            for expr in fn["ScriptBytecode"]
            if str(expr.get("$type", "")).endswith("EX_LocalFinalFunction, UAssetAPI")
            and expr.get("StackNode") == 1
        ]
        self.assertEqual(len(dispatches), 1)

        # The success branch must have an early return, but the original vanilla
        # ExecuteUbergraph dispatch remains reachable via rebased jump targets.
        self.assertTrue(
            any(
                str(expr.get("$type", "")).endswith("EX_Return, UAssetAPI")
                for expr in fn["ScriptBytecode"][2:]
            )
        )

    def test_probe_policy_excludes_shipping_chassis_presets(self):
        policy = json.loads(
            (ROOT / "Source/probes/ground_graft_ping_probe.json").read_text(
                encoding="utf-8"
            )
        )
        rows = [row["row"] for row in policy["selection"]["candidates"]]
        self.assertEqual(len(rows), 11)
        self.assertNotIn("AutoShotgun", rows)
        self.assertNotIn("AutoCritical", rows)
        self.assertNotIn("ExplosiveBlank", rows)

        excluded = policy["selection"]["excluded_chassis_preset_rows"]
        self.assertIn("TommyGun", excluded["AutoShotgun"])
        self.assertIn("Shuriken", excluded["AutoCritical"])
        self.assertIn("RocketLauncher", excluded["ExplosiveBlank"])

    def test_probe_policy_commit_order_never_consumes_donor_before_verification(self):
        policy = json.loads(
            (ROOT / "Source/probes/ground_graft_ping_probe.json").read_text(
                encoding="utf-8"
            )
        )
        commit = policy["commit_order"]
        verify_index = next(i for i, step in enumerate(commit) if "re-read" in step)
        consume_index = next(i for i, step in enumerate(commit) if "K2_DestroyActor" in step)
        self.assertLess(verify_index, consume_index)
        self.assertIn("AddTicket", commit[3])

    def test_empty_probe_candidate_set_fails_closed(self):
        with self.assertRaises(Exception):
            patch(fixture(), {"selection": {"candidates": []}, "free_complexity_affixes": 2})


if __name__ == "__main__":
    unittest.main()
