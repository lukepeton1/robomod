import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ReleaseManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(
            (ROOT / "Source/manifests/production_packages.json").read_text(encoding="utf-8")
        )
        cls.version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        cls.builder = (ROOT / "tools/windows/build-weapon-foundry.ps1").read_text(encoding="utf-8")

    def test_release_version_is_rc(self):
        self.assertRegex(self.version, r"^\d+\.\d+\.\d+-rc\d+$")

    def test_expected_six_production_packages(self):
        packages = self.manifest["packages"]
        self.assertEqual(len(packages), 6)
        paths = [p["path"] for p in packages]
        self.assertEqual(len(paths), len(set(paths)))

    def test_every_patch_source_exists(self):
        missing = [
            item["source"]
            for item in self.manifest["packages"]
            if not (ROOT / item["source"]).is_file()
        ]
        self.assertEqual(missing, [])

    def test_builder_mentions_every_production_package(self):
        missing = []
        for item in self.manifest["packages"]:
            relative = item["path"].replace("RoboQuest/Content/", "").replace("/", "\\")
            if relative not in self.builder:
                missing.append(item["path"])
        self.assertEqual(missing, [])

    def test_diagnostic_weapon_tables_are_excluded(self):
        prod = {p["path"] for p in self.manifest["packages"]}
        excluded = set(self.manifest["excluded_diagnostic_packages"])
        self.assertTrue(excluded.isdisjoint(prod))

    def test_manifest_affix_cap_matches_builder(self):
        cap = self.manifest["max_foundry_affixes"]
        self.assertIn(f'"{cap}"', self.builder)
        self.assertIn("foundryGuard", self.builder)


if __name__ == "__main__":
    unittest.main()
