import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class GroundGraftPackagingContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.probe = (
            ROOT / "tools/windows/build-ground-graft-ping-probe.ps1"
        ).read_text(encoding="utf-8")
        cls.production = (
            ROOT / "tools/windows/build-weapon-foundry.ps1"
        ).read_text(encoding="utf-8")

    def test_probe_uses_isolated_overlay_staging(self):
        self.assertIn('$probeStageRoot = Join-Path $OutputDir "probe-staging"', self.probe)
        self.assertIn(
            '$stageBase = Join-Path $probeStageRoot ("RoboQuest\\Content\\" + $relative)',
            self.probe,
        )
        self.assertIn("WeaponFoundry_GraftProbe_P.utoc", self.probe)
        self.assertIn("WeaponFoundry_GraftProbe_P.ucas", self.probe)
        self.assertIn("WeaponFoundry_GraftProbe_P.pak", self.probe)

    def test_probe_preserves_baseline_containers(self):
        self.assertIn('WeaponFoundry_P.utoc', self.probe)
        self.assertIn('Production baseline container missing after overlay build', self.probe)
        self.assertNotIn(
            'foreach ($name in @("WeaponFoundry_P.pak","WeaponFoundry_P.ucas","WeaponFoundry_P.utoc"))',
            self.probe,
        )

    def test_retoc_output_is_captured(self):
        self.assertIn('retoc-ground-graft-to-zen.log', self.probe)
        self.assertIn('& $RetocPath @retocArgs 2>&1', self.probe)
        self.assertIn('Tee-Object -FilePath $retocLog', self.probe)

    def test_production_restore_removes_probe_overlay(self):
        for name in (
            "WeaponFoundry_GraftProbe_P.pak",
            "WeaponFoundry_GraftProbe_P.ucas",
            "WeaponFoundry_GraftProbe_P.utoc",
            "WeaponFoundry_GraftSafeHost_P.pak",
            "WeaponFoundry_GraftSafeHost_P.ucas",
            "WeaponFoundry_GraftSafeHost_P.utoc",
            "WeaponFoundry_GraftGate_P.pak",
            "WeaponFoundry_GraftGate_P.ucas",
            "WeaponFoundry_GraftGate_P.utoc",
        ):
            self.assertIn(name, self.production)
        self.assertIn("Remove-Item -Force $diagnosticPath", self.production)

    def test_new_gate_uses_proven_interactive_host(self):
        script = (
            ROOT / "tools/windows/build-ground-graft-gate-probe.ps1"
        ).read_text(encoding="utf-8")
        self.assertIn('BP_Interactive_Weapon', script)
        self.assertIn('patch_ground_graft_rows_probe.py', script)
        self.assertIn('WeaponFoundry_GraftGate_P.utoc', script)
        self.assertIn('retoc-ground-graft-gate.log', script)
        self.assertIn('WeaponFoundry_GraftSafeHost_P.pak', script)
        self.assertNotIn('BP_APlayer.uasset', script)


if __name__ == "__main__":
    unittest.main()
