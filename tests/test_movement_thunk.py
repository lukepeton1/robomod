import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "analyze_calcvelocity_thunk.py"
SPEC = importlib.util.spec_from_file_location("analyze_calcvelocity_thunk", MODULE_PATH)
MOD = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MOD)


class CalcVelocityThunkTests(unittest.TestCase):
    def test_detects_aligned_vtable_call(self):
        code = b"\x90" * 8 + b"\xff\x90\x40\x01\x00\x00" + b"\x90" * 8
        rows = MOD.scan_indirect_calls(code)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["base_register"], "rax")
        self.assertEqual(rows[0]["displacement"], 0x140)
        self.assertEqual(rows[0]["possible_vtable_slot"], 40)

    def test_detects_rex_extended_base(self):
        code = b"\x41\xff\x50\x20"
        rows = MOD.scan_indirect_calls(code)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["base_register"], "r8")
        self.assertEqual(rows[0]["possible_vtable_slot"], 4)

    def test_ignores_register_indirect_call(self):
        self.assertEqual(MOD.scan_indirect_calls(b"\xff\xd0"), [])


if __name__ == "__main__":
    unittest.main()
