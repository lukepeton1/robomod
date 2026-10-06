import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


class GraftContractAlignmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.transaction = load("Source/grafting/graft_transaction.json")
        cls.ui = load("Source/grafting/ui_contract.json")
        cls.transfer = load("Source/grafting/transfer_policy.json")
        cls.matrix = load("Source/grafting/compatibility_matrix.json")
        cls.packager = (
            ROOT / "tools/windows/package-release.ps1"
        ).read_text(encoding="utf-8")

    def test_rule_engine_is_shared_by_transaction_and_ui(self):
        self.assertEqual(
            self.transaction["rule_engine"]["implementation"],
            "tools/evaluate_graft.py",
        )
        self.assertEqual(
            self.ui["shared"]["rule_engine"],
            "tools/evaluate_graft.py",
        )

    def test_quality_caps_match_every_contract(self):
        expected = {"0": 0, "1": 3, "2": 4, "3": 5, "4": 6}
        self.assertEqual(
            self.transaction["rule_engine"]["quality_caps"],
            expected,
        )
        self.assertEqual(
            self.ui["quality_display"]["color_byte_caps"],
            expected,
        )

    def test_single_alt_fire_slot_is_explicit(self):
        self.assertEqual(
            self.transaction["rule_engine"]["alt_fire_slots"],
            1,
        )
        self.assertIn(
            "single native secondary-fire slot",
            self.ui["smith"]["behavior"]["alt_fire"],
        )

    def test_transaction_base_costs_match_transfer_policy(self):
        base = self.transaction["cost"]["base_costs"]
        model = self.transfer["cost_model"]
        self.assertEqual(base["common_affix"], model["common_affix"])
        self.assertEqual(base["rare_affix"], model["rare_affix"])
        self.assertEqual(base["elite_alt_fire"], model["elite_alt_fire"])

    def test_compatibility_matrix_matches_transferable_catalog_size(self):
        summary = self.matrix["summary"]
        transfer = self.transfer["summary"]
        self.assertEqual(
            summary["transferable_affix_count"],
            transfer["transferable_affixes"],
        )
        self.assertEqual(
            summary["transferable_alt_fire_count"],
            transfer["transferable_alt_fires"],
        )
        self.assertEqual(
            summary["transferable_property_count"],
            transfer["transferable_affixes"] + transfer["transferable_alt_fires"],
        )

    def test_ui_reason_codes_cover_rule_engine_failures(self):
        expected = {
            "same_weapon",
            "invalid_ownership",
            "donor_missing_property",
            "locked_property",
            "property_kind_mismatch",
            "incompatible_target",
            "transferable_conflict",
            "duplicate_not_supported",
            "quality_locked",
            "complexity_cap",
            "alt_fire_slot_occupied",
            "insufficient_power_cells",
        }
        self.assertTrue(expected.issubset(set(self.ui["shared"]["reason_codes"])))

    def test_release_source_contains_rule_engine_and_generated_inputs(self):
        required = [
            "Source\\grafting\\compatibility_matrix.json",
            "Source\\grafting\\ui_contract.json",
            "Source\\composition\\alt_fire_skill_profiles.json",
            "tools\\evaluate_graft.py",
            "tools\\generate_graft_compatibility.py",
            "tools\\generate_alt_fire_profiles.py",
        ]
        for item in required:
            self.assertIn(item, self.packager)


if __name__ == "__main__":
    unittest.main()
