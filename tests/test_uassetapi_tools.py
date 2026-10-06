import copy
import json
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from patch_uassetapi_datatable import PatchError, apply  # noqa: E402
from disassemble_uassetapi import PackageResolver, function_summary, inline  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
