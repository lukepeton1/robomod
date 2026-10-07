import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from generate_donor_identity import build_from_repo  # noqa: E402


class DonorRuntimeIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.generated = build_from_repo()
        cls.tracked = json.loads(
            (ROOT / "Source/grafting/donor_identity_catalog.json").read_text(
                encoding="utf-8"
            )
        )

    def test_generated_catalog_is_current(self):
        self.assertEqual(self.generated, self.tracked)

    def test_all_transferable_rows_have_runtime_identity(self):
        summary = self.generated["summary"]
        self.assertEqual(summary["transferable_rows"], 65)
        self.assertEqual(
            summary["exact_signature_rows"] + summary["context_guarded_rows"],
            65,
        )

    def test_only_expected_context_guards_are_used(self):
        allowed = {
            "ignore_inactive_row",
            "current_enchanted_row",
            "chassis_or_internal_row",
        }
        for identity in self.generated["identities"]:
            for guard in identity["context_guards"]:
                self.assertIn(guard["type"], allowed)

    def test_transferable_rows_do_not_collide_with_each_other(self):
        transferable = {
            (identity["kind"], identity["row"])
            for identity in self.generated["identities"]
        }
        for identity in self.generated["identities"]:
            for collision in identity["signature_collisions"]:
                self.assertNotIn(
                    (collision["kind"], collision["row"]),
                    transferable,
                    msg=f"{identity['row']} collides with transferable {collision}",
                )

    def test_same_class_transferables_have_custom_discriminators(self):
        groups = self.generated["class_discriminators"]
        self.assertEqual(len(groups), 4)
        for group in groups:
            self.assertGreater(len(group["rows"]), 1)
            self.assertTrue(group["keys"])

    def test_identity_never_depends_on_display_text(self):
        blob = json.dumps(self.generated["runtime_model"]).lower()
        self.assertIn("never infer row identity from tooltip/display strings", blob)
        for identity in self.generated["identities"]:
            self.assertNotIn("name", identity)
            self.assertNotIn("description", identity)

    def test_actor_enumeration_is_explicitly_retired(self):
        runtime = self.generated["runtime_model"]
        self.assertIn("DISPROVEN", runtime["actor_enumeration"])
        self.assertIn("AAWeapon.GetAffixRowNames()", runtime["acquisition"])\n        self.assertIn("fallback", runtime["acquisition"])
        self.assertIn("WeaponRef", runtime["ownership_filter"])
        self.assertNotIn("GetAllActorsOfClass", runtime["acquisition"])


if __name__ == "__main__":
    unittest.main()
