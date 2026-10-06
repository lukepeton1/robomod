from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools import analyze_movement_seams as movement


class MovementAnalyzerTests(unittest.TestCase):
    def test_classification_and_scoring(self) -> None:
        text = "RoboquestMovementComponent PowerSlide Dash AirControl Velocity"
        categories = movement.classify_text(text)
        self.assertIn("core_player", categories)
        self.assertIn("power_slide", categories)
        self.assertIn("dash", categories)
        self.assertIn("movement_physics", categories)
        self.assertGreater(movement.score_text(text), 50)

    def test_fmodel_player_component_is_detected(self) -> None:
        payload = [
            {
                "Type": "BlueprintGeneratedClass",
                "Name": "BP_APlayer_C",
                "Super": {
                    "ObjectName": "Class'Character_Player'",
                    "ObjectPath": "/Script/RoboQuest",
                },
            },
            {
                "Type": "BP_APlayer_C",
                "Name": "Default__BP_APlayer_C",
                "Flags": "RF_ClassDefaultObject",
                "Properties": {
                    "bMovementPredict": True,
                    "bReplicateMovement": False,
                    "DashDuration": 0.15,
                },
            },
            {
                "Type": "RoboquestMovementComponent",
                "Name": "CharMoveComp",
                "Class": "UScriptClass'RoboquestMovementComponent'",
                "Properties": {
                    "GravityScale": 0,
                    "JumpZVelocity": 0,
                    "MaxWalkSpeed": 0,
                    "MaxAcceleration": 0,
                    "AirControl": 0,
                    "MaxCustomMovementSpeed": 5000,
                },
            },
            {
                "Type": "Function",
                "Name": "OnBlueprintLanded",
            },
        ]

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = root / "Blueprint" / "Player" / "BP_APlayer.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(payload), encoding="utf-8")
            report = movement.analyze_fmodel(path, root)

        self.assertEqual(report["package"], "Blueprint/Player/BP_APlayer")
        self.assertEqual(report["parent"], "Class'Character_Player'")
        self.assertTrue(report["movement_components"])
        props = report["movement_components"][0]["properties"]
        self.assertEqual(props["MaxWalkSpeed"], 0)
        self.assertIn("OnBlueprintLanded", report["functions"])

    def test_manifest_reader_ignores_comments(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "manifest.txt"
            path.write_text("# header\nBlueprint/Player/BP_APlayer\n\nData/DT_PlayerSkills\n", encoding="utf-8")
            self.assertEqual(
                movement.read_manifest(path),
                ["Blueprint/Player/BP_APlayer", "Data/DT_PlayerSkills"],
            )


if __name__ == "__main__":
    unittest.main()
