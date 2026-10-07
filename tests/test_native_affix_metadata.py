import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from scan_native_affix_metadata import (  # noqa: E402
    candidate_binaries,
    printable_strings,
    scan_file,
)


class NativeAffixMetadataScannerTests(unittest.TestCase):
    def test_printable_strings_extract_ascii_and_utf16(self):
        payload = (
            b"prefix\x00"
            b"AWeaponAffix\x00\x00\x00"
            + "WeaponStatManager".encode("utf-16le")
            + b"\x00\x00tail"
        )
        values = {(row.encoding, row.value) for row in printable_strings(payload)}
        self.assertIn(("ascii", "AWeaponAffix"), values)
        self.assertIn(("utf16le", "WeaponStatManager"), values)

    def test_scan_file_keeps_narrow_affix_identifiers(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "RoboQuest-Win64-Shipping.exe"
            path.write_bytes(
                b"AlphaSymbol\x00"
                b"Affixes\x00"
                b"AWeaponAffix\x00"
                b"WeaponRef\x00"
                b"WeaponStatManager\x00"
                b"UnrelatedSymbol\x00"
            )

            result = scan_file(path, radius=2)
            self.assertEqual(result["high_value_exact_hits"]["Affixes"][0]["encoding"], "ascii")
            self.assertIn("AWeaponAffix", result["unique_anchor_values"])
            self.assertIn("WeaponRef", result["unique_anchor_values"])
            self.assertIn("WeaponStatManager", result["unique_anchor_values"])
            self.assertNotIn("UnrelatedSymbol", result["unique_anchor_values"])

    def test_candidate_binaries_prioritize_roboquest_shipping_binary(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            shipping = root / "RoboQuest-Win64-Shipping.exe"
            other = root / "Other.exe"
            shipping.write_bytes(b"x")
            other.write_bytes(b"x")

            found = candidate_binaries(root)
            self.assertEqual(found, [shipping])


if __name__ == "__main__":
    unittest.main()
