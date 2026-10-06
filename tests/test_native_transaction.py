import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class NativeTransactionContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data = json.loads(
            (ROOT / "research/generated/runtime_seams.json").read_text(encoding="utf-8")
        )
        player = next(
            asset
            for asset in data["assets"]
            if asset["path"] == "Blueprint/Player/BP_APlayer.json"
        )
        cls.functions = {fn["name"]: fn for fn in player["functions"]}

    def test_add_affix_entrypoint_exists(self):
        fn = self.functions["AddEnchantedAffix"]
        self.assertIn("FUNC_BlueprintCallable", fn["flags"])
        self.assertEqual(
            [(p["name"], p["type"]) for p in fn["params"]],
            [("RowName", "NameProperty")],
        )

    def test_server_affix_rpc_is_reliable_and_authoritative(self):
        fn = self.functions["OnServerAddEnchantedAffix"]
        for flag in ("FUNC_Net", "FUNC_NetReliable", "FUNC_NetServer"):
            self.assertIn(flag, fn["flags"])
        self.assertEqual(
            [(p["name"], p["type"]) for p in fn["params"]],
            [("RowName", "NameProperty"), ("Weapon", "ObjectProperty")],
        )

    def test_multicast_affix_rpc_is_reliable(self):
        fn = self.functions["OnMulticastAddEnchantedAffix"]
        for flag in ("FUNC_Net", "FUNC_NetReliable", "FUNC_NetMulticast"):
            self.assertIn(flag, fn["flags"])
        self.assertEqual(
            [(p["name"], p["type"]) for p in fn["params"]],
            [("RowName", "NameProperty"), ("Weapon", "ObjectProperty")],
        )


if __name__ == "__main__":
    unittest.main()
