import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from reconcile_donor_affixes import (  # noqa: E402
    DonorIdentityError,
    DonorIdentityReconciler,
)


class DonorReconciliationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = DonorIdentityReconciler.from_repo()
        cls.by_row = cls.r.by_row

    def observation(self, row):
        identity = self.by_row[row]
        return {
            "class": identity["class"],
            "custom": dict(identity.get("custom") or {}),
        }

    def choice_rows(self, result):
        return {row["row"]: row["instances"] for row in result["choices"]}

    def test_exact_identity_survives_reconciliation(self):
        result = self.r.reconcile(
            [self.observation("Homing")],
            donor_weapon_row="HandGun",
        )
        self.assertEqual(self.choice_rows(result), {"Homing": 1})

    def test_same_class_transferables_use_custom_discriminator(self):
        result = self.r.reconcile(
            [
                self.observation("AutoCritical"),
                self.observation("AutoCriticalRare"),
            ],
            donor_weapon_row="HandGun",
        )
        self.assertEqual(
            self.choice_rows(result),
            {"AutoCritical": 1, "AutoCriticalRare": 1},
        )

    def test_winchester_native_explosive2_is_subtracted(self):
        # Explosive2 has the same runtime signature as transferable Explosive3.
        result = self.r.reconcile(
            [self.observation("Explosive3")],
            donor_weapon_row="Winchester",
        )
        self.assertEqual(self.choice_rows(result), {})
        self.assertEqual(result["subtractions"][0]["row"], "Explosive2")

    def test_real_explosive3_remains_after_native_copy_is_subtracted(self):
        result = self.r.reconcile(
            [self.observation("Explosive3"), self.observation("Explosive3")],
            donor_weapon_row="Winchester",
        )
        self.assertEqual(self.choice_rows(result), {"Explosive3": 1})

    def test_enchanted_lookalike_is_subtracted(self):
        result = self.r.reconcile(
            [self.observation("AreaSize")],
            donor_weapon_row="HandGun",
            current_enchanted_row="AreaSize_Enchanted",
        )
        self.assertEqual(self.choice_rows(result), {})
        self.assertEqual(
            result["subtractions"][0]["source"],
            "current_enchanted_row",
        )

    def test_ordinary_copy_remains_beside_enchanted_lookalike(self):
        result = self.r.reconcile(
            [self.observation("AreaSize"), self.observation("AreaSize")],
            donor_weapon_row="HandGun",
            current_enchanted_row="AreaSize_Enchanted",
        )
        self.assertEqual(self.choice_rows(result), {"AreaSize": 1})

    def test_unknown_affix_class_is_ignored(self):
        result = self.r.reconcile(
            [{"class": "/Game/Unknown.Unknown_C", "custom": {}}],
            donor_weapon_row="HandGun",
        )
        self.assertEqual(self.choice_rows(result), {})
        self.assertEqual(result["ignored_instance_count"], 1)

    def test_missing_expected_native_instance_fails_closed(self):
        with self.assertRaises(DonorIdentityError):
            self.r.reconcile([], donor_weapon_row="Winchester")


if __name__ == "__main__":
    unittest.main()
