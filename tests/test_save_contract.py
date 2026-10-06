import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SaveContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data = json.loads(
            (ROOT / "research/generated/runtime_seams.json").read_text(encoding="utf-8")
        )
        cls.save_profile = next(
            asset
            for asset in data["assets"]
            if asset["path"] == "Blueprint/GameSystem/SaveGame/BP_SaveGame_Profile.json"
        )

    def test_player_run_save_contains_weapons_and_power_cells(self):
        saved = self.save_profile["cdo_properties"]["Saved_PlayerData"]
        self.assertIn("Weapons", saved)
        self.assertIsInstance(saved["Weapons"], list)
        self.assertIn("Powercells", saved)
        self.assertIn("InRunPowercells", saved)

    def test_saved_player_data_is_native_roboquest_struct(self):
        prop = next(
            p
            for p in self.save_profile["class_properties"]
            if p["name"] == "Saved_PlayerData"
        )
        self.assertEqual(prop["type"], "StructProperty")
        self.assertEqual(prop["struct"], "/Script/RoboQuest")


if __name__ == "__main__":
    unittest.main()
