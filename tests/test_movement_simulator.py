from __future__ import annotations

import unittest
from pathlib import Path

from tools import simulate_movement as sim

ROOT = Path(__file__).resolve().parents[1]
CFG = sim.load_config(ROOT / "Source" / "movement" / "movement_config.json")


class MovementSimulatorTests(unittest.TestCase):
    def test_forward_air_does_not_create_free_speed(self) -> None:
        state = sim.scenario_forward_air(CFG, 120)
        self.assertAlmostEqual(state.vel.horizontal_speed(), CFG["ground"]["wish_speed"], places=6)

    def test_air_strafe_can_build_horizontal_speed(self) -> None:
        state = sim.scenario_air_strafe(CFG, 120)
        self.assertGreater(state.vel.horizontal_speed(), CFG["ground"]["wish_speed"] * 1.2)

    def test_slide_hop_preserves_earned_speed(self) -> None:
        state = sim.scenario_slide_hop(CFG, 120)
        self.assertGreater(state.vel.horizontal_speed(), CFG["ground"]["wish_speed"])

    def test_frame_invariance_at_60_to_240_hz(self) -> None:
        for name in sim.SCENARIOS:
            report = sim.frame_invariance(CFG, name, [60, 120, 144, 240])
            error = report["errors"]["60"]
            self.assertLess(
                error["relative_position_error"], 0.015,
                f"{name} position is too frame-rate dependent",
            )
            self.assertLess(
                error["relative_velocity_error"], 0.015,
                f"{name} velocity is too frame-rate dependent",
            )

    def test_emergency_cap_is_not_a_normal_speed_target(self) -> None:
        state = sim.State(sim.Vec3(), sim.Vec3(50000, 0, 0), False)
        sim.safety_clamp(state, CFG)
        self.assertAlmostEqual(state.vel.speed(), CFG["safety"]["absolute_speed"], places=6)
        self.assertGreater(CFG["safety"]["absolute_speed"], CFG["ground"]["wish_speed"] * 5)


if __name__ == "__main__":
    unittest.main()
