from __future__ import annotations

import hashlib
import struct
import unittest

from tools import analyze_native_movement_strings as native


class NativeMovementStringTests(unittest.TestCase):
    def test_string_scanner_finds_ascii_and_utf16(self) -> None:
        data = b"\x00RoboquestMovementComponent\x00" + "OnStartDash".encode("utf-16le") + b"\x00\x00"
        rows = native.strings_with_offsets(data)
        texts = {row["text"] for row in rows}
        self.assertIn("RoboquestMovementComponent", texts)
        self.assertIn("OnStartDash", texts)

    def test_pe_metadata_reads_basic_header(self) -> None:
        data = bytearray(512)
        data[0:2] = b"MZ"
        struct.pack_into("<I", data, 0x3C, 0x80)
        data[0x80:0x84] = b"PE\x00\x00"
        struct.pack_into("<HHIIIHH", data, 0x84, 0x8664, 7, 123456789, 0, 0, 0xF0, 0x2022)
        struct.pack_into("<I", data, 0x80 + 24 + 16, 0x1234)
        meta = native.pe_metadata(bytes(data))
        self.assertTrue(meta["valid_pe"])
        self.assertEqual(meta["machine"], 0x8664)
        self.assertEqual(meta["sections"], 7)
        self.assertEqual(meta["entrypoint_rva"], 0x1234)

    def test_output_hash_helper_is_stable(self) -> None:
        self.assertEqual(native.sha256_bytes(b"momentum"), hashlib.sha256(b"momentum").hexdigest())


if __name__ == "__main__":
    unittest.main()
