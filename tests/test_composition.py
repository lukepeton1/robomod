import json
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from simulate_composition import load_rules, simulate  # noqa: E402


class CompositionSimulatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = load_rules()

    def test_ray_cast_seeker_resolves_to_projectile(self):
        result = simulate(["Homing"], base_hit_type="EHitType::Raycast", rules=self.rules)
        self.assertEqual(result["resolved_hit_type"], "EHitType::Projectile")
        self.assertTrue(any("Homing" in x for x in result["conversions"]))

    def test_freewheel_duplicates_complete_buckshot_shape(self):
        result = simulate(["FreeShot", "AutoShotgun"], rules=self.rules)
        duplicates = [e for e in result["events"] if e["kind"] == "duplicate_shot"]
        self.assertTrue(duplicates)
        duplicate_id = duplicates[0]["id"]
        duplicate_pellets = [e for e in result["events"] if e["parent_id"] == duplicate_id and e["kind"] == "pellet"]
        self.assertEqual(len(duplicate_pellets), result["resolved_pellet_count"])
        self.assertIn("Buckshot", duplicates[0]["active_effects"])

    def test_fragment_children_keep_seeker_and_element(self):
        result = simulate(["Fragmentation", "Homing", "Ice"], rules=self.rules)
        fragments = [e for e in result["events"] if e["kind"] == "fragment"]
        self.assertTrue(fragments)
        for event in fragments:
            self.assertIn("Homing", event["active_effects"])
            self.assertIn("Cryo", event["active_effects"])

    def test_same_fragmentation_instance_does_not_self_recurse(self):
        result = simulate(["Fragmentation"], rules=self.rules)
        fragments = [e for e in result["events"] if e["kind"] == "fragment"]
        self.assertEqual(len(fragments), self.rules["effects"]["Fragmentation"]["simulator_children_per_proc"])
        for event in fragments:
            self.assertIn("Fragmentation#0", event["consumed"])

    def test_two_fragmentation_instances_can_form_a_second_generation(self):
        result = simulate(["Fragmentation", "Fragmentation"], rules=self.rules)
        fragments = [e for e in result["events"] if e["kind"] == "fragment"]
        self.assertGreater(len(fragments), self.rules["effects"]["Fragmentation"]["simulator_children_per_proc"])
        self.assertLessEqual(max(e["depth"] for e in result["events"]), self.rules["guards"]["max_generation_depth"])

    def test_ricochet_child_keeps_burn_and_cannot_reuse_same_instance(self):
        result = simulate(["Ricochet", "Burn"], rules=self.rules)
        ricochets = [e for e in result["events"] if e["kind"] == "ricochet_hit"]
        self.assertTrue(ricochets)
        for event in ricochets:
            self.assertIn("Burn", event["active_effects"])
            self.assertIn("Ricochet#0", event["consumed"])

    def test_explosive_pierce_semantics_keep_pierce_active(self):
        result = simulate(["Pierce", "ExplosiveBlank", "Shock"], rules=self.rules)
        explosions = [e for e in result["events"] if e["kind"] == "explosion"]
        self.assertTrue(explosions)
        for event in explosions:
            self.assertIn("Pierce", event["active_effects"])
            self.assertIn("Shock", event["active_effects"])

    def test_monster_build_terminates(self):
        rows = [
            "FreeShot", "AutoShotgun", "Homing", "Ricochet",
            "Burn", "Pierce", "Bounce", "Fragmentation", "ExplosiveBlank"
        ]
        result = simulate(rows, rules=self.rules)
        self.assertLessEqual(result["event_count"], self.rules["guards"]["max_events_per_root_trigger"])
        self.assertLessEqual(max(e["depth"] for e in result["events"]), self.rules["guards"]["max_generation_depth"])
        self.assertFalse(result["truncated_by_guard"], "reference monster build should terminate by provenance, not the hard fuse")


class CompositionRuleIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = json.loads(Path("Source/composition/composition_rules.json").read_text(encoding="utf-8"))
        cls.affixes = json.loads(Path("research/generated/affixes.json").read_text(encoding="utf-8"))
        cls.by_row = {a["row"]: a for a in cls.affixes}

    def test_all_configured_affix_rows_exist(self):
        missing = []
        for effect, cfg in self.rules["effects"].items():
            for row in cfg.get("row_ids", []):
                if row not in self.by_row:
                    missing.append((effect, row))
        self.assertEqual(missing, [])

    def test_configured_native_blueprints_match_catalog_when_direct(self):
        mismatches = []
        for effect, cfg in self.rules["effects"].items():
            blueprints = []
            if cfg.get("native_blueprint"):
                blueprints.append(cfg["native_blueprint"])
            blueprints += cfg.get("native_blueprints", [])
            if not blueprints:
                continue
            for row in cfg.get("row_ids", []):
                observed = self.by_row[row].get("class")
                if observed and observed not in blueprints:
                    # A grouped semantic may deliberately include several row IDs backed
                    # by the same family. Every observed class still must be named.
                    mismatches.append((effect, row, observed))
        self.assertEqual(mismatches, [])


if __name__ == "__main__":
    unittest.main()
