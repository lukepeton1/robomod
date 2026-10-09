import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

from test_donor_rowname_probe import fixture as rowname_fixture
from kismet_layout import script_size
from patch_ground_graft_gate_probe import (
    patch, verify, DONOR_ROWS, TARGET_WEAPON, TARGET_ROWS,
    READY_PREFIX, DUPLICATE_PREFIX, NO_SUPPORTED_ROW, MISSING_TARGET,
)


def fixture():
    asset = rowname_fixture()
    asset["Imports"].append({
        "$type": "UAssetAPI.Import, UAssetAPI",
        "ObjectName": "Character_Player",
        "OuterIndex": -3,
        "ClassPackage": "/Script/CoreUObject",
        "ClassName": "Class",
        "PackageName": None,
        "bImportOptional": False,
    })
    asset["NameMap"].append("Character_Player")
    asset["NamesReferencedFromExportDataCount"] = len(asset["NameMap"])
    fn = next(exp for exp in asset["Exports"] if exp["ObjectName"] == "GetErrorText")
    fn["LoadedProperties"].append({
        "$type": "UAssetAPI.FieldTypes.FObjectProperty, UAssetAPI",
        "PropertyClass": -6,
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
    })
    return asset


def spec():
    return {"selection":{"candidates":[
        {"row":"Fragmentation", "base_cost":4},
        {"row":"Burn", "base_cost":4},
        {"row":"Firerate", "base_cost":2},
    ]}}


class GroundGraftVisibleGateTests(unittest.TestCase):
    def test_read_only_gate_patches_only_interaction_functions(self):
        patched, report = patch(fixture(), spec())
        result = verify(patched, spec())
        self.assertTrue(result["verified"])
        self.assertTrue(result["read_only"])
        self.assertTrue(result["interaction_temporarily_disabled"])
        self.assertFalse(report["mutation"])
        self.assertFalse(report["debit"])
        self.assertFalse(report["donor_consumption"])
        for fn in patched["Exports"]:
            self.assertEqual(fn["ScriptBytecodeSize"], script_size(fn["ScriptBytecode"]))

    def test_expected_statuses_and_typed_locals(self):
        patched, _ = patch(fixture(), spec())
        fn = next(exp for exp in patched["Exports"] if exp["ObjectName"] == "GetErrorText")
        props = {p["Name"]:p for p in fn["LoadedProperties"]}
        self.assertEqual(props[DONOR_ROWS]["SerializedType"], "ArrayProperty")
        self.assertEqual(props[TARGET_ROWS]["SerializedType"], "ArrayProperty")
        self.assertEqual(props[TARGET_WEAPON]["SerializedType"], "ObjectProperty")
        self.assertEqual(props[DONOR_ROWS]["Inner"]["SerializedType"], "NameProperty")
        text = str(fn["ScriptBytecode"])
        for row in ("Fragmentation", "Burn", "Firerate"):
            self.assertIn(READY_PREFIX+row, text)
            self.assertIn(DUPLICATE_PREFIX+row, text)
        self.assertIn(NO_SUPPORTED_ROW, text)
        self.assertIn(MISSING_TARGET, text)

    def test_does_not_modify_original_function_defaults(self):
        original = fixture()
        old_names = {e["ObjectName"] for e in original["Exports"]}
        patched, _ = patch(original, spec())
        self.assertEqual({e["ObjectName"] for e in patched["Exports"]}, old_names)
        self.assertNotIn("AddEnchantedAffix", str(patched["Exports"]))
        self.assertNotIn("OnServerAddEnchantedAffix", str(patched["Exports"]))

    def test_unsupported_candidate_set_fails_closed(self):
        with self.assertRaises(Exception):
            patch(fixture(), {"selection":{"candidates":[]}})

    def test_original_unpatched_asset_fails_verification(self):
        with self.assertRaises(Exception):
            verify(fixture(), spec())


if __name__ == "__main__":
    unittest.main()
