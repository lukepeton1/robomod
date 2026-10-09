import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

from kismet_layout import script_size
from test_ground_graft_gate_probe import fixture, spec
from patch_ground_graft_rows_probe import (
    patch, verify, COUNT, DONOR_ROWS, ROW_NAMES, MESSAGE,
    MISSING_DONOR, MISSING_TARGET, ZERO_ROWS, SELF_OK, SELF_FAIL,
)


class GroundGraftRawRowInspectorTests(unittest.TestCase):
    def test_read_only_sample_and_probe_verification(self):
        old = fixture()
        original_export_names = [e["ObjectName"] for e in old["Exports"]]
        new, report = patch(old, spec())
        result = verify(new, spec())
        self.assertTrue(result["verified"])
        self.assertTrue(result["read_only"])
        self.assertEqual(result["sample_indices"], [0, 1, 2])
        self.assertTrue(result["array_self_check"])
        self.assertEqual(result["candidate_count"], 3)
        self.assertFalse(report["mutation"])
        self.assertFalse(report["debit"])
        self.assertFalse(report["donor_consumption"])
        self.assertEqual([e["ObjectName"] for e in new["Exports"]], original_export_names)
        self.assertEqual(old, fixture(), "patch() must not modify source asset")
        for fn in new["Exports"]:
            self.assertEqual(fn["ScriptBytecodeSize"], script_size(fn["ScriptBytecode"]))

    def test_typed_name_output_and_static_failures(self):
        new, _ = patch(fixture(), spec())
        fn = next(e for e in new["Exports"] if e["ObjectName"] == "GetErrorText")
        props = {p["Name"]: p for p in fn["LoadedProperties"]}
        self.assertEqual(props[DONOR_ROWS]["SerializedType"], "ArrayProperty")
        self.assertEqual(props[DONOR_ROWS]["Inner"]["SerializedType"], "NameProperty")
        self.assertEqual(props[COUNT]["SerializedType"], "IntProperty")
        self.assertEqual(props[MESSAGE]["SerializedType"], "StrProperty")
        for name in ROW_NAMES:
            self.assertEqual(props[name]["SerializedType"], "NameProperty")
        code = str(fn["ScriptBytecode"])
        for stage in (MISSING_DONOR, MISSING_TARGET, ZERO_ROWS,
                      SELF_OK, SELF_FAIL, "gate=NO_MATCH"):
            self.assertIn(stage, code)

    def test_extracted_first_row_is_self_compared(self):
        new, _ = patch(fixture(), spec())
        self.assertTrue(verify(new, spec())["array_self_check"])
        fn = next(e for e in new["Exports"] if e["ObjectName"] == "GetErrorText")
        calls = str(fn["ScriptBytecode"])
        self.assertIn("Array_Get", str(new["Imports"]))
        self.assertIn("Array_Contains", str(new["Imports"]))
        self.assertIn(ROW_NAMES[0], calls)

    def test_mutations_are_absent(self):
        new, _ = patch(fixture(), spec())
        content = str(new["Exports"])
        for forbidden in ("AddEnchantedAffix", "OnServerAddEnchantedAffix",
                          "K2_DestroyActor", "RemoveTicket", "AddTicket"):
            self.assertNotIn(forbidden, content)

    def test_bad_specs_and_unpatched_assets_fail_closed(self):
        with self.assertRaises(Exception):
            patch(fixture(), {"selection": {"candidates": []}})
        with self.assertRaises(Exception):
            patch(fixture(), {"selection": {"candidates": [
                {"row": "Bounce"}, {"row": "Bounce"},
            ]}})
        with self.assertRaises(Exception):
            verify(fixture(), spec())

    def test_invalid_sample_guard_fails_verification(self):
        new, _ = patch(fixture(), spec())
        corrupt = copy.deepcopy(new)
        fn = next(e for e in corrupt["Exports"] if e["ObjectName"] == "GetErrorText")
        # The first sample has a count > 0 conditional immediately before it.
        for i, expr in enumerate(fn["ScriptBytecode"]):
            if "Array_Get" in str(expr) and i:
                fn["ScriptBytecode"][i - 1]["$type"] = (
                    "UAssetAPI.Kismet.Bytecode.Expressions.EX_Nothing, UAssetAPI"
                )
                break
        with self.assertRaises(Exception):
            verify(corrupt, spec())


if __name__ == "__main__":
    unittest.main()
