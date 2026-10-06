import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from kismet_layout import expression_size, script_size  # noqa: E402
from patch_donor_identity_probe import patch, verify  # noqa: E402


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
            "ObjectName": "GameplayStatics",
            "OuterIndex": -2,
            "ClassPackage": "/Script/CoreUObject",
            "ClassName": "Class",
            "PackageName": None,
            "bImportOptional": False,
        },
        {
            "$type": "UAssetAPI.Import, UAssetAPI",
            "ObjectName": "KismetSystemLibrary",
            "OuterIndex": -2,
            "ClassPackage": "/Script/CoreUObject",
            "ClassName": "Class",
            "PackageName": None,
            "bImportOptional": False,
        },
    ]
    code = [
        {
            "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_Jump, UAssetAPI",
            "CodeOffset": 5,
        },
        {
            "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_EndOfScript, UAssetAPI",
        },
    ]
    fn = {
        "$type": "UAssetAPI.ExportTypes.FunctionExport, UAssetAPI",
        "ObjectName": "GetInteractSound",
        "LoadedProperties": [],
        "ScriptBytecode": code,
        "ScriptBytecodeRaw": None,
        "ScriptBytecodeSize": script_size(code),
    }
    return {
        "NameMap": [
            "/Script/CoreUObject",
            "/Script/Engine",
            "/Script/RoboQuest",
            "GameplayStatics",
            "KismetSystemLibrary",
            "GetInteractSound",
        ],
        "NamesReferencedFromExportDataCount": 6,
        "Imports": imports,
        "Exports": [fn],
    }


class DonorIdentityProbeTests(unittest.TestCase):
    def test_probe_inserts_enumeration_and_preserves_layout(self):
        original = fixture()
        old_jump = original["Exports"][0]["ScriptBytecode"][0]["CodeOffset"]
        patched, report = patch(original)

        result = verify(patched)
        self.assertTrue(result["verified"])
        self.assertEqual(result["target_class"], "AWeaponAffix")
        self.assertEqual(report["inserted_statement_count"], 6)
        self.assertGreater(report["inserted_byte_count"], 0)
        self.assertGreaterEqual(report["rebased_absolute_targets"], 1)

        fn = patched["Exports"][0]
        self.assertEqual(script_size(fn["ScriptBytecode"]), fn["ScriptBytecodeSize"])
        original_jump = fn["ScriptBytecode"][6]
        self.assertEqual(
            original_jump["CodeOffset"],
            old_jump + report["inserted_byte_count"],
        )

    def test_probe_adds_typed_runtime_locals(self):
        patched, _ = patch(fixture())
        fn = patched["Exports"][0]
        props = {p["Name"]: p for p in fn["LoadedProperties"]}
        self.assertEqual(props["WF_AffixActors"]["SerializedType"], "ArrayProperty")
        inner_class = props["WF_AffixActors"]["Inner"]["PropertyClass"]
        self.assertEqual(
            patched["Imports"][-inner_class - 1]["ObjectName"],
            "AWeaponAffix",
        )
        self.assertEqual(props["WF_AffixActorCount"]["SerializedType"], "IntProperty")
        self.assertEqual(props["WF_AffixActorCountText"]["SerializedType"], "StrProperty")

    def test_unpatched_asset_fails_verification(self):
        with self.assertRaises(Exception):
            verify(fixture())


if __name__ == "__main__":
    unittest.main()
