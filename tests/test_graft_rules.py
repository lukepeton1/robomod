import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from evaluate_graft import GraftRules  # noqa: E402


class GraftRuleEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = GraftRules.from_repo()

    def codes(self, result):
        return {reason["code"] for reason in result["reasons"]}

    def test_core_explosive_graft_allowed_and_costed(self):
        result = self.rules.evaluate(
            target_weapon="JunkColt",
            row_id="ExplosiveBlank",
            existing_affix_rows=["Burn", "Firerate"],
            current_affix_count=2,
            quality_color=4,
            available_power_cells=10,
            donor_weapon="AssaultRifle",
            donor_rows=["ExplosiveBlank", "Accuracy"],
        )
        self.assertTrue(result["allowed"], result)
        self.assertEqual(result["cost"]["base"], 4)
        self.assertEqual(result["cost"]["complexity_surcharge"], 0)
        self.assertEqual(result["cost"]["total"], 4)
        self.assertEqual(result["quality_cap"], 6)

    def test_cost_scales_after_two_affixes(self):
        result = self.rules.evaluate(
            target_weapon="JunkColt",
            row_id="Burn",
            existing_affix_rows=["Firerate", "Impact", "Bounce", "Pierce"],
            current_affix_count=4,
            quality_color=4,
            available_power_cells=20,
            donor_weapon="AssaultRifle",
            donor_rows=["Burn"],
        )
        self.assertTrue(result["allowed"], result)
        self.assertEqual(result["cost"]["base"], 4)
        self.assertEqual(result["cost"]["complexity_surcharge"], 2)
        self.assertEqual(result["cost"]["total"], 6)

    def test_common_quality_is_locked(self):
        result = self.rules.evaluate(
            target_weapon="JunkColt",
            row_id="Burn",
            current_affix_count=0,
            quality_color=0,
            available_power_cells=99,
            donor_weapon="AssaultRifle",
            donor_rows=["Burn"],
        )
        self.assertFalse(result["allowed"])
        self.assertIn("quality_locked", self.codes(result))
        self.assertEqual(result["quality_cap"], 0)

    def test_quality_complexity_cap_blocks_next_affix(self):
        result = self.rules.evaluate(
            target_weapon="JunkColt",
            row_id="Burn",
            existing_affix_rows=["Firerate", "Impact", "Bounce"],
            current_affix_count=3,
            quality_color=1,
            available_power_cells=99,
            donor_weapon="AssaultRifle",
            donor_rows=["Burn"],
        )
        self.assertFalse(result["allowed"])
        self.assertIn("complexity_cap", self.codes(result))
        self.assertEqual(result["quality_cap"], 3)

    def test_target_incompatibility_is_explicit(self):
        result = self.rules.evaluate(
            target_weapon="RocketLauncher",
            row_id="Accuracy",
            current_affix_count=1,
            quality_color=3,
            available_power_cells=99,
            donor_weapon="AssaultRifle",
            donor_rows=["Accuracy"],
        )
        self.assertFalse(result["allowed"])
        self.assertIn("incompatible_target", self.codes(result))

    def test_conflict_is_rejected(self):
        result = self.rules.evaluate(
            target_weapon="JunkColt",
            row_id="Homing",
            existing_affix_rows=["ProjectileRaycast"],
            current_affix_count=1,
            quality_color=4,
            available_power_cells=99,
            donor_weapon="AssaultRifle",
            donor_rows=["Homing"],
        )
        self.assertFalse(result["allowed"])
        self.assertIn("transferable_conflict", self.codes(result))

    def test_duplicate_spawn_affix_is_rejected_until_provenance_exists(self):
        result = self.rules.evaluate(
            target_weapon="JunkColt",
            row_id="Fragmentation",
            existing_affix_rows=["Fragmentation"],
            current_affix_count=1,
            quality_color=4,
            available_power_cells=99,
            donor_weapon="AssaultRifle",
            donor_rows=["Fragmentation"],
        )
        self.assertFalse(result["allowed"])
        self.assertIn("duplicate_not_supported", self.codes(result))

    def test_donor_must_actually_contain_selected_row(self):
        result = self.rules.evaluate(
            target_weapon="JunkColt",
            row_id="Burn",
            current_affix_count=1,
            quality_color=4,
            available_power_cells=99,
            donor_weapon="AssaultRifle",
            donor_rows=["Shock"],
        )
        self.assertFalse(result["allowed"])
        self.assertIn("donor_missing_property", self.codes(result))

    def test_power_cells_are_server_computed(self):
        result = self.rules.evaluate(
            target_weapon="JunkColt",
            row_id="Burn",
            current_affix_count=4,
            quality_color=4,
            available_power_cells=5,
            donor_weapon="AssaultRifle",
            donor_rows=["Burn"],
        )
        self.assertFalse(result["allowed"])
        self.assertIn("insufficient_power_cells", self.codes(result))
        self.assertEqual(result["cost"]["total"], 6)

    def test_one_native_alt_fire_slot_until_multi_mod_is_verified(self):
        allowed = self.rules.evaluate(
            target_weapon="JunkColt",
            row_id="Barrier",
            existing_affix_rows=["Burn", "Bounce", "Firerate"],
            existing_weapon_mod_rows=[],
            current_affix_count=3,
            quality_color=3,
            available_power_cells=99,
            donor_weapon="AssaultRifle",
            donor_rows=["Barrier"],
        )
        self.assertTrue(allowed["allowed"], allowed)
        self.assertEqual(allowed["cost"]["total"], 8)

        blocked = self.rules.evaluate(
            target_weapon="JunkColt",
            row_id="Barrier",
            existing_affix_rows=["Burn", "Bounce", "Firerate"],
            existing_weapon_mod_rows=["RocketJump"],
            current_affix_count=3,
            quality_color=3,
            available_power_cells=99,
            donor_weapon="AssaultRifle",
            donor_rows=["Barrier"],
        )
        self.assertFalse(blocked["allowed"])
        self.assertIn("alt_fire_slot_occupied", self.codes(blocked))


    def test_donor_planner_surfaces_allowed_and_blocked_choices(self):
        plan = self.rules.plan_donor(
            target_weapon="JunkColt",
            donor_weapon="AssaultRifle",
            donor_rows=["Burn", "ExplosiveBlank", "ProjectileRaycast", "Barrier"],
            existing_affix_rows=["Homing", "Firerate"],
            existing_weapon_mod_rows=[],
            current_affix_count=2,
            quality_color=4,
            available_power_cells=20,
        )
        by_row = {choice["row_id"]: choice for choice in plan["choices"]}

        self.assertTrue(by_row["Burn"]["allowed"])
        self.assertTrue(by_row["ExplosiveBlank"]["allowed"])
        self.assertFalse(by_row["ProjectileRaycast"]["allowed"])
        self.assertIn(
            "transferable_conflict",
            {r["code"] for r in by_row["ProjectileRaycast"]["reasons"]},
        )
        self.assertTrue(by_row["Barrier"]["allowed"])
        self.assertEqual(plan["allowed_count"], 3)
        self.assertEqual(plan["blocked_count"], 1)

    def test_smith_planner_uses_same_rule_engine(self):
        plan = self.rules.plan_smith(
            target_weapon="JunkColt",
            existing_affix_rows=["Burn", "Bounce"],
            existing_weapon_mod_rows=["Barrier"],
            current_affix_count=2,
            quality_color=2,
            available_power_cells=5,
        )
        self.assertEqual(
            plan["allowed_count"] + plan["blocked_count"],
            len(self.rules.transferable),
        )

        by_row = {choice["row_id"]: choice for choice in plan["choices"]}
        self.assertFalse(by_row["Burn"]["allowed"])
        self.assertIn(
            "duplicate_not_supported",
            {r["code"] for r in by_row["Burn"]["reasons"]},
        )
        self.assertFalse(by_row["RocketJump"]["allowed"])
        self.assertIn(
            "alt_fire_slot_occupied",
            {r["code"] for r in by_row["RocketJump"]["reasons"]},
        )
        self.assertTrue(by_row["ExplosiveBlank"]["allowed"])

    def test_igniter_runtime_rows_are_innate_not_graftable(self):
        # October 9 cooked in-game probe on an Igniter Gun:
        # n=2, 0=BurnBlank, 1=HomingBlank, self=OK, gate=NO_MATCH.
        plan = self.rules.plan_donor(
            donor_weapon="FireGun", target_weapon="HandGun",
            donor_rows=["BurnBlank", "HomingBlank"],
            existing_affix_rows=["OnKillReloadOtherWeapon"],
            quality_color=0, available_power_cells=8,
        )
        self.assertEqual(plan["allowed_count"], 0)
        self.assertEqual(plan["blocked_count"], 2)
        by_row = {choice["row_id"]: choice for choice in plan["choices"]}
        for row in ("BurnBlank", "HomingBlank"):
            self.assertIn("locked_property", self.codes(by_row[row]))
            self.assertIn("donor_native_preset", self.codes(by_row[row]))

    def test_transferable_row_is_still_blocked_when_innate_to_donor(self):
        # Native Tommy Gun AutoShotgun must not be harvested merely because
        # the ordinary AutoShotgun row is transferable in other contexts.
        result = self.rules.evaluate(
            target_weapon="JunkColt", donor_weapon="TommyGun",
            donor_rows=["AutoShotgun"], row_id="AutoShotgun",
            quality_color=4, available_power_cells=50,
        )
        self.assertFalse(result["allowed"])
        self.assertIn("donor_native_preset", self.codes(result))
        self.assertIn("AutoShotgun", self.rules.transferable)

    def test_absent_unknown_donor_chassis_fails_closed(self):
        for chassis in (None, "UnknownFakeWeapon"):
            with self.subTest(chassis=chassis):
                result = self.rules.evaluate(
                    target_weapon="JunkColt", row_id="Burn",
                    donor_rows=["Burn"], donor_weapon=chassis,
                    quality_color=4, available_power_cells=50,
                )
                self.assertFalse(result["allowed"])
                self.assertIn("donor_identity_unverified", self.codes(result))

    def test_independently_rolled_row_remains_transferable(self):
        result = self.rules.evaluate(
            target_weapon="JunkColt", donor_weapon="AssaultRifle",
            donor_rows=["Burn"], row_id="Burn",
            quality_color=4, available_power_cells=50,
        )
        self.assertTrue(result["allowed"], result)
        self.assertNotIn("donor_native_preset", self.codes(result))

    def test_kind_mismatch_fails_closed(self):
        result = self.rules.evaluate(
            target_weapon="JunkColt",
            row_id="Barrier",
            requested_kind="affix",
            quality_color=4,
            available_power_cells=99,
            donor_weapon="AssaultRifle",
            donor_rows=["Barrier"],
        )
        self.assertFalse(result["allowed"])
        self.assertIn("property_kind_mismatch", self.codes(result))


if __name__ == "__main__":
    unittest.main()
