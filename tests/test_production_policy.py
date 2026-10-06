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
        cls.alt_profiles = load("Source/composition/alt_fire_skill_profiles.json")

    def test_core_weapon_counts(self):
        policy = self.core["policy"]
        self.assertEqual(policy["standard_weapon_count"], 74)
        self.assertEqual(policy["projectile_weapon_count"], 39)
        self.assertFalse(policy["seeker_resolver_enabled"])
        self.assertEqual(policy["seeker_supported_weapon_count"], 7)

    def test_seeker_stays_on_vanilla_pool_while_resolver_is_disabled(self):
        ops = self.core["operations"]
        widened = [
            op for op in ops
            if op["op"] == "replace_name_array" and op["row"] == "Homing"
        ]
        self.assertEqual(widened, [])
        self.assertEqual(
            self.core["policy"]["seeker_supported_weapons"],
            [
                "MineGun",
                "BlastGun",
                "RocketLauncher",
                "BallGun",
                "BarrelCannon",
                "BlastArbalete",
                "DualTonfa",
            ],
        )

    def test_production_mod_pool_is_curated_and_broad(self):
        self.assertEqual(self.mods["policy"]["resolved_alt_fire_count"], 15)
        self.assertEqual(len(self.mods["operations"]), 15)
        for op in self.mods["operations"]:
            self.assertEqual(op["op"], "replace_name_array")
            self.assertEqual(op["field"], "Weapons")
            self.assertEqual(len(op["values"]), 74)

    def test_transfer_catalog_summary(self):
        summary = self.transfer["summary"]
        self.assertEqual(summary["transferable_affixes"], 50)
        self.assertEqual(summary["transferable_alt_fires"], 15)

    def test_foundry_merchant_uses_only_globally_safe_transferable_affixes(self):
        ordinary = {
            row["row"]: row
            for row in self.transfer["transferable"]
            if row["kind"] == "affix"
        }
        values = self.merchant["operations"][0]["values"]

        self.assertEqual(len(ordinary), 50)
        self.assertEqual(self.merchant["policy"]["full_transferable_affix_count"], 50)
        self.assertEqual(self.merchant["policy"]["global_merchant_affix_count"], 15)
        self.assertEqual(len(values), 15)
        self.assertTrue(set(values).issubset(ordinary))

        generalized = {
            op["row"]
            for op in self.core["operations"]
            if op["op"] == "replace_name_array"
        }
        coverage = self.core["policy"]["standard_weapon_count"]
        unsafe = [
            row
            for row in values
            if ordinary[row].get("vanilla_weapons", 0) < coverage
            and row not in generalized
        ]
        self.assertEqual(unsafe, [])

        enchanted = {
            row["row"]
            for row in self.transfer["locked"]
            if row["kind"] == "affix"
            and row["reason"] == "enchanted_slot_reserved"
        }
        self.assertTrue(enchanted)
        self.assertTrue(enchanted.isdisjoint(values))

        # Target-specific rows remain available for the future donor GRAFT flow,
        # but must not leak into the global random merchant.
        target_specific = set(ordinary) - set(values)
        self.assertGreater(len(target_specific), 0)

        matrix = load("Source/grafting/compatibility_matrix.json")
        by_row = {row["row"]: row for row in matrix["properties"]}
        pairwise_conflicts = {
            (row, conflict)
            for row in values
            for conflict in by_row[row]["transferable_conflicts"]
            if conflict in values
        }
        self.assertEqual(pairwise_conflicts, set())
        self.assertEqual(
            set(self.merchant["policy"]["excluded_global_conflict_rows"]),
            {"BossDamage", "FlyDamage", "TurretDamage"},
        )


    def test_every_transferable_alt_fire_has_profile(self):
        expected = {
            row["row"]
            for row in self.transfer["transferable"]
            if row["kind"] == "weapon_mod"
        }
        profiles = {row["row"]: row for row in self.alt_profiles["profiles"]}
        self.assertEqual(set(profiles), expected)
        self.assertEqual(self.alt_profiles["production_alt_fire_count"], 15)

        for row, profile in profiles.items():
            self.assertTrue(profile["secondary_skill_row"].startswith("WS_"))
            self.assertIn(
                profile["target_detection"],
                {"EHitType::Projectile", "EHitType::Raycast", "EHitType::None"},
            )
            self.assertTrue(profile["behavior"])
            self.assertIn(
                profile["validation_priority"],
                {
                    "high_projectile_inheritance",
                    "high_raycast_inheritance",
                    "state_or_utility",
                },
            )

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
