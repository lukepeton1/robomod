#!/usr/bin/env python3
"""Reference simulator for Roboquest Momentum velocity semantics.

It is intentionally engine-independent. The simulator exists to tune and regression-test
the movement equations before they are wired into Roboquest's native movement layer.
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "Source" / "movement" / "movement_config.json"

@dataclass
class Vec3:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def __add__(self, other: "Vec3") -> "Vec3":
        return Vec3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: "Vec3") -> "Vec3":
        return Vec3(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, scalar: float) -> "Vec3":
        return Vec3(self.x * scalar, self.y * scalar, self.z * scalar)

    __rmul__ = __mul__

    def horizontal_speed(self) -> float:
        return math.hypot(self.x, self.y)

    def speed(self) -> float:
        return math.sqrt(self.x * self.x + self.y * self.y + self.z * self.z)

    def dot2(self, other: "Vec3") -> float:
        return self.x * other.x + self.y * other.y

    def normalized2(self) -> "Vec3":
        mag = self.horizontal_speed()
        if mag <= 1e-12:
            return Vec3()
        return Vec3(self.x / mag, self.y / mag, 0.0)

@dataclass
class State:
    pos: Vec3
    vel: Vec3
    grounded: bool = True

def accelerate_horizontal(vel: Vec3, wish_dir: Vec3, wish_speed: float, accel: float, dt: float) -> Vec3:
    """Directional cap only: total horizontal speed is deliberately not hard-clamped."""
    d = wish_dir.normalized2()
    if d.horizontal_speed() <= 1e-12 or wish_speed <= 0:
        return vel
    current = vel.dot2(d)
    add = wish_speed - current
    if add <= 0:
        return vel
    amount = min(add, accel * wish_speed * dt)
    return Vec3(vel.x + d.x * amount, vel.y + d.y * amount, vel.z)

def friction_speed(speed: float, friction: float, stop_speed: float, dt: float) -> float:
    """Exact integration of Source-like ds/dt=-friction*max(speed, stop_speed)."""
    if speed <= 0.0:
        return 0.0
    if friction <= 0.0 or dt <= 0.0:
        return speed

    if speed > stop_speed:
        time_to_stop_band = math.log(speed / stop_speed) / friction
        if dt <= time_to_stop_band:
            return speed * math.exp(-friction * dt)
        dt -= time_to_stop_band
        speed = stop_speed

    return max(0.0, speed - friction * stop_speed * dt)

def apply_ground_friction(vel: Vec3, friction: float, stop_speed: float, dt: float) -> Vec3:
    speed = vel.horizontal_speed()
    if speed <= 1e-12:
        return Vec3(0.0, 0.0, vel.z)
    new_speed = friction_speed(speed, friction, stop_speed, dt)
    scale = new_speed / speed
    return Vec3(vel.x * scale, vel.y * scale, vel.z)

def apply_slide_friction(vel: Vec3, friction: float, dt: float) -> Vec3:
    scale = math.exp(-friction * dt)
    return Vec3(vel.x * scale, vel.y * scale, vel.z)

def soft_high_speed_damping(vel: Vec3, threshold: float, damping: float, dt: float) -> Vec3:
    speed = vel.horizontal_speed()
    if speed <= threshold or damping <= 0:
        return vel
    excess = speed - threshold
    new_speed = threshold + excess * math.exp(-damping * dt)
    scale = new_speed / speed
    return Vec3(vel.x * scale, vel.y * scale, vel.z)

def integrate_position(state: State, old_vel: Vec3, dt: float) -> None:
    state.pos = state.pos + (old_vel + state.vel) * (0.5 * dt)

def ground_step(state: State, wish_dir: Vec3, cfg: dict, dt: float, friction: bool = True) -> None:
    old = Vec3(state.vel.x, state.vel.y, state.vel.z)
    g = cfg["ground"]
    if friction:
        state.vel = apply_ground_friction(state.vel, g["friction"], g["stop_speed"], dt)
    state.vel = accelerate_horizontal(state.vel, wish_dir, g["wish_speed"], g["acceleration"], dt)
    state.vel.z = 0.0
    integrate_position(state, old, dt)
    state.pos.z = 0.0
    state.grounded = True

def air_step(state: State, wish_dir: Vec3, cfg: dict, dt: float) -> None:
    old = Vec3(state.vel.x, state.vel.y, state.vel.z)
    a = cfg["air"]
    wish_component = min(a["wish_speed"], a["directional_wish_cap"])
    state.vel = accelerate_horizontal(state.vel, wish_dir, wish_component, a["acceleration"], dt)
    state.vel = soft_high_speed_damping(state.vel, a["soft_speed_threshold"], a["soft_damping"], dt)
    state.vel.z -= cfg["jump"]["gravity"] * dt
    integrate_position(state, old, dt)
    state.grounded = False

def slide_step(state: State, wish_dir: Vec3, cfg: dict, dt: float) -> None:
    old = Vec3(state.vel.x, state.vel.y, state.vel.z)
    s = cfg["slide"]
    state.vel = apply_slide_friction(state.vel, s["friction"], dt)
    state.vel = accelerate_horizontal(
        state.vel, wish_dir, cfg["ground"]["wish_speed"], s["steering_acceleration"], dt
    )
    state.vel.z = 0.0
    integrate_position(state, old, dt)
    state.pos.z = 0.0
    state.grounded = True

def jump(state: State, cfg: dict) -> None:
    state.vel.z = cfg["jump"]["vertical_impulse"]
    state.grounded = False

def wallrun_step(state: State, tangent: Vec3, cfg: dict, dt: float) -> None:
    old = Vec3(state.vel.x, state.vel.y, state.vel.z)
    t = tangent.normalized2()
    along = state.vel.dot2(t)
    state.vel.x = t.x * along
    state.vel.y = t.y * along
    state.vel = accelerate_horizontal(
        state.vel, t, max(cfg["ground"]["wish_speed"], abs(along)),
        cfg["wallrun"]["tangent_acceleration"], dt,
    )
    state.vel.z -= cfg["jump"]["gravity"] * cfg["wallrun"]["gravity_scale"] * dt
    integrate_position(state, old, dt)
    state.grounded = False

def wall_kick(state: State, normal: Vec3, cfg: dict) -> None:
    n = normal.normalized2()
    w = cfg["wallrun"]
    state.vel.x += n.x * w["wall_jump_outward_impulse"]
    state.vel.y += n.y * w["wall_jump_outward_impulse"]
    state.vel.z = max(state.vel.z, w["wall_jump_upward_impulse"])
    state.grounded = False

def add_impulse(state: State, impulse: Vec3, preservation: float, replace_z: bool = False) -> None:
    state.vel.x = state.vel.x * preservation + impulse.x
    state.vel.y = state.vel.y * preservation + impulse.y
    if replace_z:
        state.vel.z = impulse.z
    else:
        state.vel.z = state.vel.z * preservation + impulse.z

def safety_clamp(state: State, cfg: dict) -> None:
    limit = cfg["safety"]["absolute_speed"]
    speed = state.vel.speed()
    if speed <= limit or speed <= 1e-12:
        return
    state.vel = state.vel * (limit / speed)

def run_for(duration: float, fps: int, fn: Callable[[float, float], None]) -> None:
    steps = max(1, int(round(duration * fps)))
    dt = duration / steps
    for i in range(steps):
        fn(dt, (i + 0.5) * dt)

def rotating_strafe_wish(t: float, degrees_per_second: float = 75.0) -> Vec3:
    angle = math.pi / 2.0 + math.radians(degrees_per_second) * t
    return Vec3(math.cos(angle), math.sin(angle), 0.0)

def scenario_forward_acceleration(cfg: dict, fps: int) -> State:
    s = State(Vec3(), Vec3())
    run_for(1.0, fps, lambda dt, t: ground_step(s, Vec3(1, 0), cfg, dt))
    return s

def scenario_braking(cfg: dict, fps: int) -> State:
    s = State(Vec3(), Vec3(cfg["ground"]["wish_speed"], 0, 0))
    run_for(0.5, fps, lambda dt, t: ground_step(s, Vec3(), cfg, dt))
    return s

def scenario_reversal(cfg: dict, fps: int) -> State:
    s = State(Vec3(), Vec3(cfg["ground"]["wish_speed"], 0, 0))
    run_for(0.6, fps, lambda dt, t: ground_step(s, Vec3(-1, 0), cfg, dt))
    return s

def scenario_forward_air(cfg: dict, fps: int) -> State:
    s = State(Vec3(0, 0, 1000), Vec3(cfg["ground"]["wish_speed"], 0, 0), False)
    run_for(1.0, fps, lambda dt, t: air_step(s, Vec3(1, 0), cfg, dt))
    return s

def scenario_air_strafe(cfg: dict, fps: int) -> State:
    s = State(Vec3(0, 0, 1000), Vec3(cfg["ground"]["wish_speed"], 0, 0), False)
    run_for(1.0, fps, lambda dt, t: air_step(s, rotating_strafe_wish(t), cfg, dt))
    return s

def scenario_slide(cfg: dict, fps: int) -> State:
    s = State(Vec3(), Vec3(1800, 0, 0))
    run_for(0.7, fps, lambda dt, t: slide_step(s, Vec3(1, 0), cfg, dt))
    return s

def scenario_slide_hop(cfg: dict, fps: int) -> State:
    s = State(Vec3(), Vec3(1800, 0, 0))
    run_for(0.25, fps, lambda dt, t: slide_step(s, Vec3(1, 0), cfg, dt))
    jump(s, cfg)
    run_for(0.55, fps, lambda dt, t: air_step(s, rotating_strafe_wish(t), cfg, dt))
    return s

def scenario_wallrun_kick(cfg: dict, fps: int) -> State:
    s = State(Vec3(0, 0, 500), Vec3(1600, 100, 200), False)
    run_for(0.5, fps, lambda dt, t: wallrun_step(s, Vec3(1, 0), cfg, dt))
    wall_kick(s, Vec3(0, 1), cfg)
    run_for(0.25, fps, lambda dt, t: air_step(s, rotating_strafe_wish(t), cfg, dt))
    return s

def scenario_dash(cfg: dict, fps: int) -> State:
    s = State(Vec3(), Vec3(1500, 250, 0), False)
    d = cfg["impulses"]["dash"]
    add_impulse(s, Vec3(d["horizontal"], 0, 0), d["preserve_incoming"])
    safety_clamp(s, cfg)
    run_for(0.25, fps, lambda dt, t: air_step(s, rotating_strafe_wish(t), cfg, dt))
    return s

def scenario_grapple_release(cfg: dict, fps: int) -> State:
    s = State(Vec3(), Vec3(1800, 700, 300), False)
    g = cfg["impulses"]["grapple_release"]
    add_impulse(s, Vec3(0, g["horizontal"], 250), g["preserve_incoming"])
    safety_clamp(s, cfg)
    run_for(0.4, fps, lambda dt, t: air_step(s, rotating_strafe_wish(t), cfg, dt))
    return s

def scenario_rocket_jump(cfg: dict, fps: int) -> State:
    s = State(Vec3(), Vec3(1300, 0, 0), False)
    r = cfg["impulses"]["rocket_jump"]
    add_impulse(s, Vec3(-0.35 * r["horizontal"], 0, r["vertical"]), r["preserve_incoming"])
    safety_clamp(s, cfg)
    run_for(0.6, fps, lambda dt, t: air_step(s, rotating_strafe_wish(t), cfg, dt))
    return s

SCENARIOS = {
    "forward_acceleration": scenario_forward_acceleration,
    "braking": scenario_braking,
    "reversal": scenario_reversal,
    "forward_air": scenario_forward_air,
    "air_strafe": scenario_air_strafe,
    "slide": scenario_slide,
    "slide_hop": scenario_slide_hop,
    "wallrun_kick": scenario_wallrun_kick,
    "dash": scenario_dash,
    "grapple_release": scenario_grapple_release,
    "rocket_jump": scenario_rocket_jump,
}

def summarize(s: State) -> dict:
    return {
        "position": [round(s.pos.x, 6), round(s.pos.y, 6), round(s.pos.z, 6)],
        "velocity": [round(s.vel.x, 6), round(s.vel.y, 6), round(s.vel.z, 6)],
        "horizontal_speed": round(s.vel.horizontal_speed(), 6),
        "speed": round(s.vel.speed(), 6),
        "grounded": s.grounded,
    }

def relative_vector_error(a: Vec3, b: Vec3) -> float:
    denom = max(b.speed(), 1.0)
    return (a - b).speed() / denom

def frame_invariance(cfg: dict, name: str, rates: list[int]) -> dict:
    states = {fps: SCENARIOS[name](cfg, fps) for fps in rates}
    reference = states[max(rates)]
    return {
        "scenario": name,
        "reference_fps": max(rates),
        "rates": {str(fps): summarize(s) for fps, s in states.items()},
        "errors": {
            str(fps): {
                "relative_position_error": relative_vector_error(s.pos, reference.pos),
                "relative_velocity_error": relative_vector_error(s.vel, reference.vel),
            }
            for fps, s in states.items()
        },
    }

def load_config(path: Path) -> dict:
    cfg = json.loads(path.read_text(encoding="utf-8"))
    if cfg.get("schema_version") != 1:
        raise ValueError("unsupported movement config schema")
    return cfg

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    ap.add_argument("--scenario", choices=sorted(SCENARIOS))
    ap.add_argument("--fps", type=int, default=120)
    ap.add_argument("--suite", action="store_true")
    ap.add_argument("--frame-invariance", action="store_true")
    args = ap.parse_args()

    cfg = load_config(args.config)
    if args.frame_invariance:
        names = [args.scenario] if args.scenario else list(SCENARIOS)
        result = [frame_invariance(cfg, name, [60, 120, 144, 240]) for name in names]
    elif args.suite:
        result = {name: summarize(fn(cfg, args.fps)) for name, fn in SCENARIOS.items()}
    else:
        name = args.scenario or "air_strafe"
        result = {name: summarize(SCENARIOS[name](cfg, args.fps))}
    print(json.dumps(result, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
