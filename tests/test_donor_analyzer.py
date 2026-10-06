import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from analyze_donor_handoff import TARGET_PATH_HINTS, score_text  # noqa: E402


class DonorAnalyzerTests(unittest.TestCase):
    def test_native_affix_getter_and_row_struct_rank_highly(self):
        score, hits = score_text(
            "GetCurrentEnchantedAffixRowName WeaponAffixRow WeaponAffixTooltipWidget"
        )
        self.assertIn("currentenchantedaffixrowname", hits)
        self.assertIn("weaponaffixrow", hits)
        self.assertIn("weaponaffixtooltipwidget", hits)
        self.assertGreaterEqual(score, 38)

    def test_compendium_affix_widget_is_a_target_hint(self):
        self.assertGreaterEqual(
            TARGET_PATH_HINTS["WGT_WeaponCompendium_Affix"],
            10,
        )


if __name__ == "__main__":
    unittest.main()
