import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RCSmokeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.probe = json.loads(
            (ROOT / "Source/probes/rc_smoke_handgun.json").read_text(encoding="utf-8")
        )
        cls.skills = json.loads(
            (ROOT / "research/generated/player_skills.json").read_text(encoding="utf-8")
        )
        cls.production_manifest = json.loads(
            (ROOT / "Source/manifests/production_packages.json").read_text(encoding="utf-8")
        )

    def test_handgun_skill_is_native_raycast(self):
        skill = next(row for row in self.skills if row["row"] == "PF_Handgun")
        self.assertEqual(skill["target_detection"], "EHitType::Raycast")

    def test_smoke_probe_only_targets_weapon_table(self):
        self.assertEqual(self.probe["target"], "Data/DT_Weapons")
        self.assertNotIn(
            "RoboQuest/Content/Data/DT_PlayerSkills",
            {row["path"] for row in self.production_manifest["packages"]},
        )

    def test_smoke_probe_forces_expected_six_affixes(self):
        operation = self.probe["operations"][0]
        self.assertEqual(operation["op"], "replace_row_handles")
        self.assertEqual(operation["row"], "HandGun")
        self.assertEqual(operation["field"], "Affixes")
        self.assertEqual(
            operation["values"],
            [
                "Homing",
                "Bounce",
                "Fragmentation",
                "Burn",
                "ExplosiveBlank",
                "FreeShot",
            ],
        )

    def test_smoke_probe_does_not_static_convert_hit_model(self):
        serialized = json.dumps(self.probe)
        self.assertNotIn("TargetDetection", serialized)
        self.assertNotIn("EHitType::Projectile", serialized)
        self.assertIn("Raycast", self.probe["invariant"])


if __name__ == "__main__":
    unittest.main()
