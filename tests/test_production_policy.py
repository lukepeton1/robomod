import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


class ProductionPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.core = load("Source/patches/weapon_foundry_core.json")
        cls.mods = load("Source/patches/weapon_foundry_mods.json")
        cls.transfer = load("Source/grafting/transfer_policy.json")
        cls.merchant = load("Source/patches/foundry_merchant.json")

    def test_core_weapon_counts(self):
        policy = self.core["policy"]
        self.assertEqual(policy["standard_weapon_count"], 74)
        self.assertEqual(policy["projectile_weapon_count"], 39)
        self.assertEqual(policy["seeker_resolved_weapon_count"], 74)

    def test_seeker_uses_full_standard_pool_after_resolver(self):
        ops = self.core["operations"]
        seeker = next(
            op for op in ops
            if op["op"] == "replace_name_array" and op["row"] == "Homing"
        )
        baseline = next(
            op for op in ops
            if op["op"] == "replace_name_array" and op["row"] == "Fragmentation"
        )
        self.assertEqual(seeker["values"], baseline["values"])
        self.assertEqual(len(seeker["values"]), 74)
        self.assertIn("JunkColt", seeker["values"])  # native Raycast
        self.assertIn("BlastGun", seeker["values"])  # native Projectile

    def test_production_mod_pool_is_curated_and_broad(self):
        self.assertEqual(self.mods["policy"]["resolved_alt_fire_count"], 15)
        self.assertEqual(len(self.mods["operations"]), 15)
        for op in self.mods["operations"]:
            self.assertEqual(op["op"], "replace_name_array")
            self.assertEqual(op["field"], "Weapons")
            self.assertEqual(len(op["values"]), 74)

    def test_transfer_catalog_summary(self):
        summary = self.transfer["summary"]
        self.assertEqual(summary["transferable_affixes"], 49)
        self.assertEqual(summary["transferable_alt_fires"], 15)

    def test_foundry_merchant_exactly_uses_transferable_ordinary_affixes(self):
        expected = [
            row["row"]
            for row in self.transfer["transferable"]
            if row["kind"] == "affix"
        ]
        values = self.merchant["operations"][0]["values"]
        self.assertEqual(values, expected)
        self.assertEqual(len(values), 49)

        enchanted = {
            row["row"]
            for row in self.transfer["locked"]
            if row["kind"] == "affix"
            and row["reason"] == "enchanted_slot_reserved"
        }
        self.assertTrue(enchanted)
        self.assertTrue(enchanted.isdisjoint(values))

    def test_no_diagnostic_weapon_or_skill_patch_in_production_specs(self):
        production_targets = {
            self.core["target"],
            self.mods["target"],
            self.merchant["target"],
        }
        self.assertNotIn("Data/DT_Weapons", production_targets)
        self.assertNotIn("Data/DT_PlayerSkills", production_targets)


if __name__ == "__main__":
    unittest.main()
