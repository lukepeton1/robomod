import copy
import json
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from patch_uassetapi_datatable import PatchError, apply  # noqa: E402
from verify_uassetapi_patch import semantic_scalar  # noqa: E402
from disassemble_uassetapi import PackageResolver, function_summary, inline  # noqa: E402
from patch_fragmentation_bytecode import patch as patch_fragmentation, verify as verify_fragmentation  # noqa: E402


def row_handle(field: str, row_name: str) -> dict:
    return {
        "$type": "UAssetAPI.PropertyTypes.Structs.StructPropertyData, UAssetAPI",
        "StructType": "WeaponAffixRowHandle",
        "Name": field,
        "Value": [
            {"$type": "ObjectPropertyData", "Name": "DataTable", "Value": 1},
            {"$type": "NamePropertyData", "Name": "RowName", "Value": row_name},
        ],
    }


def affix_row(name: str, removed: list[str]) -> dict:
    return {
        "$type": "StructPropertyData",
        "Name": name,
        "Value": [{
            "$type": "StructPropertyData",
            "Name": "Affix",
            "Value": [{
                "$type": "ArrayPropertyData",
                "Name": "RemovedPool",
                "Value": [row_handle("RemovedPool", x) for x in removed],
            }],
        }],
    }



def affix_row_with_weapons(name: str, weapons: list[str]) -> dict:
    return {
        "$type": "StructPropertyData",
        "Name": name,
        "Value": [{
            "$type": "StructPropertyData",
            "Name": "Affix",
            "Value": [{
                "$type": "ArrayPropertyData",
                "Name": "Weapons",
                "ArrayType": "StructProperty",
                "Value": [row_handle("Weapons", x) for x in weapons],
            }],
        }],
    }

class DataTablePatcherTests(unittest.TestCase):
    def test_remove_row_handles_preserves_other_values_and_order(self):
        asset = {
            "NameMap": ["Burn", "Ice", "Shock", "Impact"],
            "Exports": [{
                "$type": "UAssetAPI.ExportTypes.DataTableExport, UAssetAPI",
                "Table": {"Data": [affix_row("Burn", ["Ice", "Shock", "Impact"])]},
            }],
        }
        original = copy.deepcopy(asset)
        spec = {
            "name": "test",
            "operations": [{
                "op": "remove_row_handles",
                "row": "Burn",
                "field": "RemovedPool",
                "values": ["Ice", "Shock"],
                "reason": "test",
            }],
        }

        patched, report = apply(asset, spec)
        pool = patched["Exports"][0]["Table"]["Data"][0]["Value"][0]["Value"][0]["Value"]
        remaining = [
            next(x["Value"] for x in h["Value"] if x["Name"] == "RowName")
            for h in pool
        ]
        self.assertEqual(remaining, ["Impact"])
        self.assertEqual(report[0]["removed"], ["Ice", "Shock"])
        self.assertEqual(original["Exports"][0]["Table"]["Data"][0]["Value"][0]["Value"][0]["Value"][0]["Value"][1]["Value"], "Ice")


    def test_empty_struct_array_gets_dummy_struct_schema(self):
        asset = {
            "Exports": [{
                "$type": "UAssetAPI.ExportTypes.DataTableExport, UAssetAPI",
                "Table": {"Data": [affix_row("Bounce", ["Ricochet"])]},
            }],
        }
        spec = {
            "operations": [{
                "op": "remove_row_handles",
                "row": "Bounce",
                "field": "RemovedPool",
                "values": ["Ricochet"],
            }],
        }

        patched, report = apply(asset, spec)
        prop = patched["Exports"][0]["Table"]["Data"][0]["Value"][0]["Value"][0]
        self.assertEqual(prop["Value"], [])
        self.assertIn("DummyStruct", prop)
        self.assertEqual(prop["DummyStruct"]["StructType"], "WeaponAffixRowHandle")
        self.assertEqual(prop["DummyStruct"]["Value"], [])
        self.assertTrue(report[0]["dummy_struct_preserved"])


    def test_copy_row_handles_clones_native_eligibility_pool(self):
        asset = {
            "Exports": [{
                "$type": "UAssetAPI.ExportTypes.DataTableExport, UAssetAPI",
                "Table": {"Data": [
                    affix_row_with_weapons("Fragmentation", ["Boltgun"]),
                    affix_row_with_weapons("Burn", ["JunkColt", "BlastArbalete", "MineGun"]),
                ]},
            }],
        }
        spec = {
            "operations": [{
                "op": "copy_array",
                "row": "Fragmentation",
                "field": "Weapons",
                "source_row": "Burn",
                "source_field": "Weapons",
            }],
        }

        patched, report = apply(asset, spec)
        rows = patched["Exports"][0]["Table"]["Data"]
        target = rows[0]["Value"][0]["Value"][0]
        source = rows[1]["Value"][0]["Value"][0]
        target_names = [
            next(x["Value"] for x in h["Value"] if x["Name"] == "RowName")
            for h in target["Value"]
        ]
        self.assertEqual(target_names, ["JunkColt", "BlastArbalete", "MineGun"])
        self.assertEqual(report[0]["copied_count"], 3)
        self.assertEqual(report[0]["array_type"], "StructProperty")
        self.assertIsNot(target["Value"], source["Value"])


    def test_copy_name_property_array_preserves_native_shape(self):
        def weapons_row(name, values):
            return {
                "$type": "StructPropertyData",
                "Name": name,
                "Value": [{
                    "$type": "StructPropertyData",
                    "Name": "Affix",
                    "Value": [{
                        "$type": "UAssetAPI.PropertyTypes.Objects.ArrayPropertyData, UAssetAPI",
                        "ArrayType": "NameProperty",
                        "Name": "Weapons",
                        "Value": [
                            {
                                "$type": "UAssetAPI.PropertyTypes.Objects.NamePropertyData, UAssetAPI",
                                "Name": str(i),
                                "ArrayIndex": 0,
                                "Value": value,
                            }
                            for i, value in enumerate(values)
                        ],
                    }],
                }],
            }

        asset = {
            "Exports": [{
                "$type": "UAssetAPI.ExportTypes.DataTableExport, UAssetAPI",
                "Table": {"Data": [
                    weapons_row("Fragmentation", ["Boltgun"]),
                    weapons_row("Burn", ["JunkColt", "BlastArbalete", "MineGun"]),
                ]},
            }],
        }
        spec = {
            "operations": [{
                "op": "copy_array",
                "row": "Fragmentation",
                "field": "Weapons",
                "source_row": "Burn",
                "source_field": "Weapons",
            }],
        }

        patched, report = apply(asset, spec)
        rows = patched["Exports"][0]["Table"]["Data"]
        target = rows[0]["Value"][0]["Value"][0]
        self.assertEqual(target["ArrayType"], "NameProperty")
        self.assertEqual([x["Value"] for x in target["Value"]], ["JunkColt", "BlastArbalete", "MineGun"])
        self.assertEqual([x["Name"] for x in target["Value"]], ["0", "1", "2"])
        self.assertEqual(report[0]["array_type"], "NameProperty")



    def test_replace_name_array_registers_values(self):
        def weapons_row(name, values):
            return {
                "$type": "StructPropertyData",
                "Name": name,
                "Value": [{
                    "$type": "StructPropertyData",
                    "Name": "Affix",
                    "Value": [{
                        "$type": "UAssetAPI.PropertyTypes.Objects.ArrayPropertyData, UAssetAPI",
                        "ArrayType": "NameProperty",
                        "Name": "Weapons",
                        "Value": [
                            {
                                "$type": "UAssetAPI.PropertyTypes.Objects.NamePropertyData, UAssetAPI",
                                "Name": str(i),
                                "ArrayIndex": 0,
                                "Value": value,
                            }
                            for i, value in enumerate(values)
                        ],
                    }],
                }],
            }

        asset = {
            "NameMap": ["Boltgun"],
            "NamesReferencedFromExportDataCount": 1,
            "Exports": [{
                "$type": "UAssetAPI.ExportTypes.DataTableExport, UAssetAPI",
                "Table": {"Data": [weapons_row("Fragmentation", ["Boltgun"])]},
            }],
        }
        expected = ["BlastGun", "RocketLauncher", "Boltgun"]
        spec = {
            "operations": [{
                "op": "replace_name_array",
                "row": "Fragmentation",
                "field": "Weapons",
                "values": expected,
            }],
        }
        patched, report = apply(asset, spec)
        prop = patched["Exports"][0]["Table"]["Data"][0]["Value"][0]["Value"][0]
        self.assertEqual([x["Value"] for x in prop["Value"]], expected)
        self.assertEqual([x["Name"] for x in prop["Value"]], ["0", "1", "2"])
        self.assertEqual(report[0]["name_map_added"], ["BlastGun", "RocketLauncher"])
        self.assertEqual(patched["NamesReferencedFromExportDataCount"], 3)

    def test_set_value_works_through_player_skill_wrapper(self):
        asset = {
            "NameMap": ["EHitType::Raycast"],
            "NamesReferencedFromExportDataCount": 1,
            "Exports": [{
                "$type": "UAssetAPI.ExportTypes.DataTableExport, UAssetAPI",
                "Table": {"Data": [{
                    "$type": "StructPropertyData",
                    "Name": "PF_Handgun",
                    "Value": [{
                        "$type": "StructPropertyData",
                        "Name": "PlayerSkill",
                        "Value": [{
                            "$type": "EnumPropertyData",
                            "Name": "TargetDetection",
                            "Value": "EHitType::Raycast",
                        }],
                    }],
                }]},
            }],
        }
        spec = {
            "operations": [{
                "op": "set_value",
                "row": "PF_Handgun",
                "field": "TargetDetection",
                "value": "EHitType::Projectile",
            }],
        }
        patched, report = apply(asset, spec)
        prop = patched["Exports"][0]["Table"]["Data"][0]["Value"][0]["Value"][0]
        self.assertEqual(prop["Value"], "EHitType::Projectile")
        self.assertEqual(report[0]["before"], "EHitType::Raycast")
        self.assertEqual(report[0]["name_map_added"], ["EHitType::Projectile"])
        self.assertIn("EHitType::Projectile", patched["NameMap"])
        self.assertEqual(
            patched["NamesReferencedFromExportDataCount"],
            len(patched["NameMap"]),
        )

    def test_replace_row_handles_works_through_weapon_wrapper(self):
        asset = {
            "NameMap": [
                "OnKillReloadOtherWeapon",
                "ExplosiveBlank",
                "AutoShotgun",
            ],
            "NamesReferencedFromExportDataCount": 3,
            "Exports": [{
                "$type": "UAssetAPI.ExportTypes.DataTableExport, UAssetAPI",
                "Table": {"Data": [{
                    "$type": "StructPropertyData",
                    "Name": "HandGun",
                    "Value": [{
                        "$type": "StructPropertyData",
                        "Name": "Weapon",
                        "Value": [{
                            "$type": "ArrayPropertyData",
                            "ArrayType": "StructProperty",
                            "Name": "Affixes",
                            "Value": [row_handle("Affixes", "OnKillReloadOtherWeapon")],
                        }],
                    }],
                }]},
            }],
        }
        expected = ["Fragmentation", "Homing", "Burn", "ExplosiveBlank", "FreeShot", "AutoShotgun"]
        spec = {
            "operations": [{
                "op": "replace_row_handles",
                "row": "HandGun",
                "field": "Affixes",
                "values": expected,
            }],
        }
        patched, report = apply(asset, spec)
        prop = patched["Exports"][0]["Table"]["Data"][0]["Value"][0]["Value"][0]
        actual = [
            next(x["Value"] for x in h["Value"] if x["Name"] == "RowName")
            for h in prop["Value"]
        ]
        self.assertEqual(actual, expected)
        self.assertEqual(report[0]["replacement_count"], 6)
        self.assertEqual(
            report[0]["name_map_added"],
            ["Fragmentation", "Homing", "Burn", "FreeShot"],
        )
        self.assertEqual(
            patched["NamesReferencedFromExportDataCount"],
            len(patched["NameMap"]),
        )
        for name in expected:
            self.assertIn(name, patched["NameMap"])

        # The copied row-handle template keeps the source DataTable pointer.
        for handle in prop["Value"]:
            table = next(x["Value"] for x in handle["Value"] if x["Name"] == "DataTable")
            self.assertEqual(table, 1)

    def test_missing_requested_handle_fails_closed(self):
        asset = {
            "Exports": [{
                "$type": "UAssetAPI.ExportTypes.DataTableExport, UAssetAPI",
                "Table": {"Data": [affix_row("Bounce", ["Ricochet"])]},
            }],
        }
        spec = {
            "operations": [{
                "op": "remove_row_handles",
                "row": "Bounce",
                "field": "RemovedPool",
                "values": ["DoesNotExist"],
            }],
        }
        with self.assertRaises(PatchError):
            apply(asset, spec)



    def test_signed_zero_semantics(self):
        self.assertEqual(semantic_scalar("+0"), 0.0)
        self.assertEqual(semantic_scalar("-0"), 0.0)
        self.assertEqual(semantic_scalar(0), 0)
        self.assertEqual(semantic_scalar(1.25), 1.25)

class DisassemblerTests(unittest.TestCase):
    def test_resolves_import_stack_node(self):
        asset = {
            "Exports": [{
                "$type": "UAssetAPI.ExportTypes.FunctionExport, UAssetAPI",
                "ObjectName": "TestFunction",
                "ScriptBytecodeSize": 10,
                "ScriptBytecodeRaw": [],
                "ScriptBytecode": [{
                    "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_FinalFunction, UAssetAPI",
                    "StackNode": -1,
                    "Parameters": [{
                        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_NameConst, UAssetAPI",
                        "Value": "DamageRatio",
                    }],
                }],
            }],
            "Imports": [{
                "$type": "UAssetAPI.Import, UAssetAPI",
                "ObjectName": "GetCustomFloatProperties",
                "OuterIndex": 0,
            }],
        }
        resolver = PackageResolver(asset)
        expression = asset["Exports"][0]["ScriptBytecode"][0]
        self.assertIn("GetCustomFloatProperties", inline(expression, resolver))
        summary = function_summary(asset["Exports"][0], resolver)
        self.assertIn("GetCustomFloatProperties", summary["calls"])
        self.assertIn("DamageRatio", summary["name_constants"])



def kismet_local(name: str) -> dict:
    return {
        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_LocalVariable, UAssetAPI",
        "Variable": {
            "$type": "UAssetAPI.Kismet.Bytecode.KismetPropertyPointer, UAssetAPI",
            "New": {
                "$type": "UAssetAPI.UnrealTypes.FFieldPath, UAssetAPI",
                "Path": [name],
                "ResolvedOwner": 1,
            },
        },
    }


def fragmentation_fixture() -> dict:
    imports = [
        {"$type": "UAssetAPI.Import, UAssetAPI", "ObjectName": "CheckFlagToBitmask", "OuterIndex": 0},
        {"$type": "UAssetAPI.Import, UAssetAPI", "ObjectName": "LessEqual_IntInt", "OuterIndex": 0},
        {"$type": "UAssetAPI.Import, UAssetAPI", "ObjectName": "IsValid", "OuterIndex": 0},
        {"$type": "UAssetAPI.Import, UAssetAPI", "ObjectName": "ASkill", "OuterIndex": 0},
        {"$type": "UAssetAPI.Import, UAssetAPI", "ObjectName": "AProjectile", "OuterIndex": 0},
    ]
    child_gameplay_tags = {
        "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_Context, UAssetAPI",
        "ObjectExpression": kismet_local("CallFunc_Array_Get_Item_2"),
        "Offset": 9,
        "PropertyType": 0,
        "RValuePointer": {
            "$type": "UAssetAPI.Kismet.Bytecode.KismetPropertyPointer, UAssetAPI",
            "New": {"$type": "UAssetAPI.UnrealTypes.FFieldPath, UAssetAPI", "Path": ["GameplayTags"], "ResolvedOwner": -5},
        },
        "ContextExpression": {
            "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_InstanceVariable, UAssetAPI",
            "Variable": {
                "$type": "UAssetAPI.Kismet.Bytecode.KismetPropertyPointer, UAssetAPI",
                "New": {"$type": "UAssetAPI.UnrealTypes.FFieldPath, UAssetAPI", "Path": ["GameplayTags"], "ResolvedOwner": -5},
            },
        },
    }
    source_gameplay_tags = copy.deepcopy(child_gameplay_tags)
    source_gameplay_tags["ObjectExpression"] = kismet_local("K2Node_CustomEvent_Projectile")

    code = [
        {
            "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_LetBool, UAssetAPI",
            "VariableExpression": kismet_local("CallFunc_IsValid_ReturnValue_1"),
            "AssignmentExpression": {
                "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_CallMath, UAssetAPI",
                "StackNode": -3,
                "Parameters": [kismet_local("K2Node_CustomEvent_Projectile")],
            },
        },
        {
            "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_Let, UAssetAPI",
            "Value": copy.deepcopy(child_gameplay_tags["RValuePointer"]),
            "Variable": child_gameplay_tags,
            "Expression": source_gameplay_tags,
        },
        {
            "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_LetBool, UAssetAPI",
            "VariableExpression": kismet_local("CallFunc_CheckFlagToBitmask_ReturnValue"),
            "AssignmentExpression": {
                "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_CallMath, UAssetAPI",
                "StackNode": -1,
                "Parameters": [
                    kismet_local("CallFunc_MakeLiteralByte_ReturnValue"),
                    kismet_local("CallFunc_GetGameplayTags_ReturnValue"),
                ],
            },
        },
    ]
    return {
        "Imports": imports,
        "Exports": [{
            "$type": "UAssetAPI.ExportTypes.FunctionExport, UAssetAPI",
            "ObjectName": "ExecuteUbergraph_BP_WA_Fragmentation",
            "ScriptBytecodeSize": 3486,
            "ScriptBytecodeRaw": [],
            "ScriptBytecode": code,
        }],
    }


class FragmentationBytecodePatcherTests(unittest.TestCase):
    def test_same_shape_patch_universalizes_and_retargets_inheritance(self):
        asset = fragmentation_fixture()
        original = copy.deepcopy(asset)
        patched, report = patch_fragmentation(asset)

        self.assertTrue(report["same_shape_only"])
        self.assertFalse(report["absolute_flow_offsets_modified"])
        self.assertEqual(report["declared_script_bytecode_size"], 3486)
        self.assertEqual(len(report["changes"]), 3)
        self.assertTrue(verify_fragmentation(patched)["verified"])

        fn = patched["Exports"][0]
        gate = fn["ScriptBytecode"][2]["AssignmentExpression"]
        self.assertEqual(gate["StackNode"], -2)
        self.assertEqual(
            gate["Parameters"][0]["Variable"]["New"]["Path"],
            ["CallFunc_GetGameplayTags_ReturnValue"],
        )
        self.assertEqual(
            gate["Parameters"][1]["Variable"]["New"]["Path"],
            ["CallFunc_GetGameplayTags_ReturnValue"],
        )

        validity = fn["ScriptBytecode"][0]["AssignmentExpression"]["Parameters"][0]
        self.assertEqual(validity["Variable"]["New"]["Path"], ["CallFunc_Array_Get_Item_2"])

        source = fn["ScriptBytecode"][1]["Expression"]
        self.assertEqual(source["ObjectExpression"]["Variable"]["New"]["Path"], ["K2Node_CustomEvent_Skill"])
        self.assertEqual(source["RValuePointer"]["New"]["ResolvedOwner"], -4)
        self.assertEqual(
            source["ContextExpression"]["Variable"]["New"]["ResolvedOwner"],
            -4,
        )

        # patch() must not mutate the caller's input object.
        self.assertEqual(
            original["Exports"][0]["ScriptBytecode"][2]["AssignmentExpression"]["StackNode"],
            -1,
        )

    def test_fragmentation_verify_rejects_unpatched_asset(self):
        with self.assertRaises(Exception):
            verify_fragmentation(fragmentation_fixture())


if __name__ == "__main__":
    unittest.main()
