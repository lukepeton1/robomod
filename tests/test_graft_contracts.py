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
        cls.progression = load("Source/grafting/progression_policy.json")
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

    def test_quality_caps_match_central_progression_policy(self):
        expected = {"0": 0, "1": 3, "2": 4, "3": 5, "4": 6}
        self.assertEqual(self.progression["quality_color_caps"], expected)
        self.assertEqual(self.ui["quality_display"]["color_byte_caps"], expected)
        self.assertEqual(
            self.transaction["rule_engine"]["progression_policy"],
            "Source/grafting/progression_policy.json",
        )
        self.assertEqual(
            self.ui["shared"]["progression_policy"],
            "Source/grafting/progression_policy.json",
        )

    def test_single_alt_fire_slot_is_explicit(self):
        self.assertEqual(self.progression["native_alt_fire_slots"], 1)
        self.assertEqual(
            self.transaction["rule_engine"]["alt_fire_slots_source"],
            "Source/grafting/progression_policy.json",
        )
        self.assertIn(
            "single native secondary-fire slot",
            self.ui["smith"]["behavior"]["alt_fire"],
        )

    def test_complexity_surcharge_threshold_matches_progression_policy(self):
        free = self.progression["power_cell_economy"]["free_complexity_affixes"]
        self.assertEqual(free, 2)
        self.assertIn(
            "max(0, current_affix_count - 2)",
            self.transaction["cost"]["formula"],
        )
        self.assertEqual(
            self.transaction["cost"]["progression_policy"],
            "Source/grafting/progression_policy.json",
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

    def test_donor_preset_provenance_is_mandatory(self):
        stage = next(step for step in self.transaction["validation_order"]
                     if step["id"] == "donor_chassis_preset_provenance")
        self.assertIn("GetDataRowName()", stage["rule"])
        self.assertIn("preset_affixes", stage["rule"])
        self.assertIn("donor_native_preset", self.ui["shared"]["reason_codes"])
        self.assertIn("donor_identity_unverified", self.ui["shared"]["reason_codes"])
        self.assertEqual(self.transaction["rule_engine"]["donor_preset_source"],
                         "research/generated/weapons.json")

    def test_actor_enumeration_is_forbidden_by_contract(self):
        usage = self.transaction["rule_engine"]["donor_identity_usage"]
        self.assertIn("AAWeapon.GetAffixRowNames()", usage)
        self.assertIn("World-actor enumeration is forbidden", usage)
        self.assertIn("actor enumeration is invalid", self.ui["ground_graft"]["donor_enumeration"])
        self.assertEqual(
            self.transaction["rule_engine"]["donor_actor_enumeration"],
            "disproven by Source/probes/donor_runtime_probe_results.json",
        )

    def test_native_row_getter_candidate_is_aligned(self):
        tx = self.transaction["rule_engine"]
        ground = self.ui["ground_graft"]
        self.assertEqual(
            tx["candidate_donor_row_enumerator"],
            "AAWeapon.GetAffixRowNames()",
        )
        self.assertEqual(
            ground["candidate_donor_row_enumerator"],
            tx["candidate_donor_row_enumerator"],
        )
        self.assertEqual(
            tx["candidate_donor_row_enumerator_probe"],
            "tools/windows/run-donor-rowname-probe.cmd",
        )
        self.assertEqual(
            ground["candidate_donor_row_probe"],
            tx["candidate_donor_row_enumerator_probe"],
        )
        self.assertIn("runtime", tx["candidate_donor_row_enumerator_status"])

    def test_release_source_contains_rule_engine_and_generated_inputs(self):
        required = [
            "Source\\grafting\\compatibility_matrix.json",
            "Source\\grafting\\progression_policy.json",
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
