import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from kismet_layout import script_size  # noqa: E402
from patch_donor_rowname_probe import (  # noqa: E402
    LOCAL_ROWS,
    POSITIVE_TEXT,
    ZERO_TEXT,
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
            "ObjectName": "KismetMathLibrary",
            "OuterIndex": -2,
            "ClassPackage": "/Script/CoreUObject",
            "ClassName": "Class",
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

    error_owner = 1
    error_code = [
        return_stmt(error_owner),
        {"$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_EndOfScript, UAssetAPI"},
    ]
    error_fn = {
        "$type": "UAssetAPI.ExportTypes.FunctionExport, UAssetAPI",
        "ObjectName": "GetErrorText",
        "LoadedProperties": [
            {
                "$type": "UAssetAPI.FieldTypes.FGenericProperty, UAssetAPI",
                "ArrayDim": "TArray",
                "ElementSize": 24,
                "PropertyFlags": "CPF_Parm, CPF_OutParm, CPF_ReturnParm",
                "RepIndex": 0,
                "RepNotifyFunc": "None",
                "BlueprintReplicationCondition": "COND_None",
                "RawValue": None,
                "SerializedType": "TextProperty",
                "Name": "ReturnValue",
                "Flags": "RF_Public",
                "MetaDataMap": None,
            }
        ],
        "ScriptBytecode": error_code,
        "ScriptBytecodeRaw": None,
        "ScriptBytecodeSize": script_size(error_code),
    }

    interact_owner = 2
    interact_code = [
        return_stmt(interact_owner),
        {"$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_EndOfScript, UAssetAPI"},
    ]
    interact_fn = {
        "$type": "UAssetAPI.ExportTypes.FunctionExport, UAssetAPI",
        "ObjectName": "CanInteract",
        "LoadedProperties": [
            {
                "$type": "UAssetAPI.FieldTypes.FBoolProperty, UAssetAPI",
                "FieldSize": 1,
                "ByteOffset": 0,
                "ByteMask": 1,
                "FieldMask": 255,
                "NativeBool": True,
                "Value": True,
                "ArrayDim": "TArray",
                "ElementSize": 1,
                "PropertyFlags": "CPF_Parm, CPF_OutParm, CPF_ReturnParm",
                "RepIndex": 0,
                "RepNotifyFunc": "None",
                "BlueprintReplicationCondition": "COND_None",
                "RawValue": None,
                "SerializedType": "BoolProperty",
                "Name": "ReturnValue",
                "Flags": "RF_Public",
                "MetaDataMap": None,
            }
        ],
        "ScriptBytecode": interact_code,
        "ScriptBytecodeRaw": None,
        "ScriptBytecodeSize": script_size(interact_code),
    }

    return {
        "NameMap": [
            "/Script/CoreUObject",
            "/Script/Engine",
            "/Script/RoboQuest",
            "KismetMathLibrary",
            "AInteractiveWeapon",
            "AWeapon",
            "GetErrorText",
            "CanInteract",
        ],
        "NamesReferencedFromExportDataCount": 8,
        "Imports": imports,
        "Exports": [error_fn, interact_fn],
    }


class DonorRowNameProbeTests(unittest.TestCase):
    def test_probe_calls_native_getter_on_spawned_weapon(self):
        patched, report = patch(fixture())
        result = verify(patched)

        self.assertTrue(result["verified"])
        self.assertEqual(result["native_getter"], "AAWeapon.GetAffixRowNames")
        self.assertEqual(result["target_object"], "SpawnedWeapon")
        self.assertEqual(result["row_array_type"], "TArray<FName>")
        self.assertEqual(result["positive_text"], POSITIVE_TEXT)
        self.assertEqual(result["zero_text"], ZERO_TEXT)
        self.assertTrue(result["interaction_temporarily_disabled"])
        self.assertEqual(report["probe"], "native AAWeapon.GetAffixRowNames()")

        for fn in patched["Exports"]:
            self.assertEqual(script_size(fn["ScriptBytecode"]), fn["ScriptBytecodeSize"])

    def test_probe_adds_name_array_local(self):
        patched, _ = patch(fixture())
        fn = next(x for x in patched["Exports"] if x["ObjectName"] == "GetErrorText")
        props = {p["Name"]: p for p in fn["LoadedProperties"]}

        rows = props[LOCAL_ROWS]
        self.assertEqual(rows["SerializedType"], "ArrayProperty")
        self.assertEqual(rows["Inner"]["SerializedType"], "NameProperty")
        self.assertEqual(rows["Inner"]["ElementSize"], 12)

    def test_native_getter_import_is_owned_by_aweapon(self):
        patched, _ = patch(fixture())
        imports = patched["Imports"]
        getter_index = next(
            i for i, imp in enumerate(imports, start=1)
            if imp["ObjectName"] == "GetAffixRowNames"
        )
        getter = imports[getter_index - 1]
        owner = imports[-getter["OuterIndex"] - 1]
        self.assertEqual(owner["ObjectName"], "AWeapon")

    def test_can_interact_is_short_circuited_false(self):
        patched, _ = patch(fixture())
        fn = next(x for x in patched["Exports"] if x["ObjectName"] == "CanInteract")
        self.assertTrue(
            str(fn["ScriptBytecode"][0]["$type"]).endswith("EX_LetBool, UAssetAPI")
        )
        self.assertTrue(
            str(fn["ScriptBytecode"][0]["AssignmentExpression"]["$type"]).endswith(
                "EX_False, UAssetAPI"
            )
        )
        self.assertTrue(
            str(fn["ScriptBytecode"][1]["$type"]).endswith("EX_Return, UAssetAPI")
        )

    def test_unpatched_asset_fails_verification(self):
        with self.assertRaises(Exception):
            verify(fixture())


if __name__ == "__main__":
    unittest.main()
