import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from kismet_layout import script_size  # noqa: E402
from patch_ground_graft_safehost_probe import (  # noqa: E402
    LOCAL_CONTAINS,
    LOCAL_DONOR_ROWS,
    LOCAL_SELECTED_ROW,
    patch,
    verify,
)


def pointer(owner, name):
    return {
        "$type": "UAssetAPI.Kismet.Bytecode.KismetPropertyPointer, UAssetAPI",
        "New": {
            "$type": "UAssetAPI.UnrealTypes.FFieldPath, UAssetAPI",
            "Path": [name],
            "ResolvedOwner": owner,
        },
    }


def local_out(owner, name):
    return {
        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_LocalOutVariable, UAssetAPI",
        "Variable": pointer(owner, name),
    }


def return_stmt(owner):
    return {
        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_Return, UAssetAPI",
        "ReturnExpression": local_out(owner, "ReturnValue"),
    }


def fixture():
    imports = [
        {
            "$type": "UAssetAPI.Import, UAssetAPI",
            "ObjectName": "/Script/CoreUObject",
            "OuterIndex": 0,
            "ClassPackage": "/Script/CoreUObject",
            "ClassName": "Package",
            "PackageName": None,
            "bImportOptional": False,
        },
        {
            "$type": "UAssetAPI.Import, UAssetAPI",
            "ObjectName": "/Script/Engine",
            "OuterIndex": 0,
            "ClassPackage": "/Script/CoreUObject",
            "ClassName": "Package",
            "PackageName": None,
            "bImportOptional": False,
        },
        {
            "$type": "UAssetAPI.Import, UAssetAPI",
            "ObjectName": "/Script/RoboQuest",
            "OuterIndex": 0,
            "ClassPackage": "/Script/CoreUObject",
            "ClassName": "Package",
            "PackageName": None,
            "bImportOptional": False,
        },
        {
            "$type": "UAssetAPI.Import, UAssetAPI",
            "ObjectName": "AInteractiveWeapon",
            "OuterIndex": -3,
            "ClassPackage": "/Script/CoreUObject",
            "ClassName": "Class",
            "PackageName": None,
            "bImportOptional": False,
        },
        {
            "$type": "UAssetAPI.Import, UAssetAPI",
            "ObjectName": "AWeapon",
            "OuterIndex": -3,
            "ClassPackage": "/Script/CoreUObject",
            "ClassName": "Class",
            "PackageName": None,
            "bImportOptional": False,
        },
    ]

    owner = 1
    code = [
        return_stmt(owner),
        {"$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_EndOfScript, UAssetAPI"},
    ]
    fn = {
        "$type": "UAssetAPI.ExportTypes.FunctionExport, UAssetAPI",
        "ObjectName": "GetInteractSound",
        "LoadedProperties": [
            {
                "$type": "UAssetAPI.FieldTypes.FObjectProperty, UAssetAPI",
                "PropertyClass": -3,
                "ArrayDim": "TArray",
                "ElementSize": 8,
                "PropertyFlags": "CPF_Parm",
                "RepIndex": 0,
                "RepNotifyFunc": "None",
                "BlueprintReplicationCondition": "COND_None",
                "RawValue": None,
                "SerializedType": "ObjectProperty",
                "Name": "PlayerCharacter",
                "Flags": "RF_Public",
                "MetaDataMap": None,
            },
            {
                "$type": "UAssetAPI.FieldTypes.FObjectProperty, UAssetAPI",
                "PropertyClass": -3,
                "ArrayDim": "TArray",
                "ElementSize": 8,
                "PropertyFlags": "CPF_Parm, CPF_OutParm, CPF_ReturnParm",
                "RepIndex": 0,
                "RepNotifyFunc": "None",
                "BlueprintReplicationCondition": "COND_None",
                "RawValue": None,
                "SerializedType": "ObjectProperty",
                "Name": "ReturnValue",
                "Flags": "RF_Public",
                "MetaDataMap": None,
            },
        ],
        "ScriptBytecode": code,
        "ScriptBytecodeRaw": None,
        "ScriptBytecodeSize": script_size(code),
    }

    return {
        "NameMap": [
            "/Script/CoreUObject",
            "/Script/Engine",
            "/Script/RoboQuest",
            "AInteractiveWeapon",
            "AWeapon",
            "GetInteractSound",
            "PlayerCharacter",
            "ReturnValue",
        ],
        "NamesReferencedFromExportDataCount": 8,
        "Imports": imports,
        "Exports": [fn],
    }


def spec():
    return {
        "selection": {
            "candidates": [
                {"row": "Fragmentation", "base_cost": 4},
                {"row": "Bounce", "base_cost": 2},
                {"row": "Burn", "base_cost": 4},
            ]
        }
    }


class GroundGraftSafeHostProbeTests(unittest.TestCase):
    def test_patch_uses_safe_interactive_weapon_host(self):
        patched, report = patch(fixture(), spec())
        result = verify(patched, spec())

        self.assertTrue(result["verified"])
        self.assertTrue(result["safe_host"])
        self.assertFalse(result["bp_aplayer_modified"])
        self.assertEqual(report["asset"], "BP_Interactive_Weapon")
        self.assertEqual(report["function"], "GetInteractSound")
        self.assertEqual(
            result["authoritative_donor_rows"],
            "AAWeapon.GetAffixRowNames()",
        )
        self.assertEqual(
            result["mutation"],
            "PlayerCharacter.AddEnchantedAffix(RowName)",
        )

    def test_patch_adds_typed_probe_locals(self):
        patched, _ = patch(fixture(), spec())
        fn = patched["Exports"][0]
        props = {p["Name"]: p for p in fn["LoadedProperties"]}
        self.assertEqual(props[LOCAL_DONOR_ROWS]["SerializedType"], "ArrayProperty")
        self.assertEqual(
            props[LOCAL_DONOR_ROWS]["Inner"]["SerializedType"],
            "NameProperty",
        )
        self.assertEqual(props[LOCAL_CONTAINS]["SerializedType"], "BoolProperty")
        self.assertEqual(props[LOCAL_SELECTED_ROW]["SerializedType"], "NameProperty")

    def test_candidate_rows_and_virtual_mutation_are_registered(self):
        patched, _ = patch(fixture(), spec())
        names = set(patched["NameMap"])
        for row in ("Fragmentation", "Bounce", "Burn"):
            self.assertIn(row, names)
        self.assertIn("SpawnedWeapon", names)
        self.assertIn("AddEnchantedAffix", names)

    def test_original_function_body_survives_after_probe_block(self):
        original = fixture()
        old_size = original["Exports"][0]["ScriptBytecodeSize"]
        patched, report = patch(original, spec())
        fn = patched["Exports"][0]
        self.assertGreater(fn["ScriptBytecodeSize"], old_size)
        self.assertEqual(script_size(fn["ScriptBytecode"]), fn["ScriptBytecodeSize"])
        self.assertGreater(report["inserted_byte_count"], 0)

    def test_unpatched_asset_fails_verification(self):
        with self.assertRaises(Exception):
            verify(fixture(), spec())


if __name__ == "__main__":
    unittest.main()
