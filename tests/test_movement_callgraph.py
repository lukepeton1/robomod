from __future__ import annotations

import unittest

from tools import extract_movement_callgraph as callgraph


class MovementCallGraphTests(unittest.TestCase):
    def test_resolver_handles_import_and_export_indices(self) -> None:
        asset = {
            "Exports": [{"ObjectName": "LocalFunction", "OuterIndex": 0}],
            "Imports": [
                {"ObjectName": "/Script/RoboQuest", "OuterIndex": 0},
                {"ObjectName": "Character_Player", "OuterIndex": -1},
                {"ObjectName": "OnStartDash", "OuterIndex": -2},
            ],
        }
        r = callgraph.Resolver(asset)
        self.assertEqual(r.full_name(1), "LocalFunction")
        self.assertEqual(
            r.full_name(-3),
            "/Script/RoboQuest.Character_Player.OnStartDash",
        )

    def test_virtual_function_name_is_captured(self) -> None:
        fn = {
            "ScriptBytecode": [{
                "$type": "UAssetAPI.Kismet.Bytecode.Expressions.EX_VirtualFunction, UAssetAPI",
                "VirtualFunctionName": "OnPressedJump",
                "Parameters": [],
            }]
        }
        calls = callgraph.function_calls(fn, callgraph.Resolver({"Exports": [], "Imports": []}))
        self.assertEqual(calls[0]["target"], "OnPressedJump")


if __name__ == "__main__":
    unittest.main()
