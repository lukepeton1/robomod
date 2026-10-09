#pragma once
#include <algorithm>
#include <cmath>
#include <cstdint>

namespace momentum {

struct Vec3 {
    double x{};
    double y{};
    double z{};

    constexpr Vec3 operator+(const Vec3& o) const noexcept { return {x + o.x, y + o.y, z + o.z}; }
    constexpr Vec3 operator-(const Vec3& o) const noexcept { return {x - o.x, y - o.y, z - o.z}; }
    constexpr Vec3 operator*(double s) const noexcept { return {x * s, y * s, z * s}; }
    [[nodiscard]] double horizontal_speed() const noexcept { return std::hypot(x, y); }
    [[nodiscard]] double speed() const noexcept { return std::sqrt(x*x + y*y + z*z); }
    [[nodiscard]] double dot2(const Vec3& o) const noexcept { return x*o.x + y*o.y; }
    [[nodiscard]] Vec3 normalized2() const noexcept {
        const double m = horizontal_speed();
        return m <= 1e-12 ? Vec3{} : Vec3{x/m, y/m, 0.0};
    }
};

// Both air and ground acceleration work on the *projection* of velocity into
// the requested direction. Neither caps total horizontal velocity at run speed.
[[nodiscard]] Vec3 accelerate_horizontal(Vec3 velocity, Vec3 wish_direction, double wish_speed,
                                          double acceleration, double dt) noexcept;

// Source/Quake style: cap the directional projection for "add speed", BUT use
// full uncapped input wish speed to calculate acceleration impulse. Crucial for
// responsive strafing and accumulating speed over repeated airborne arcs.
[[nodiscard]] Vec3 air_accelerate_source(Vec3 velocity, Vec3 wish_direction,
                                        double full_wish_speed, double projection_cap,
                                        double air_acceleration, double dt) noexcept;

[[nodiscard]] double friction_speed(double speed, double friction, double stop_speed, double dt) noexcept;
[[nodiscard]] Vec3 apply_ground_friction(Vec3 velocity, double friction, double stop_speed, double dt) noexcept;
[[nodiscard]] Vec3 apply_slide_friction(Vec3 velocity, double friction, double dt) noexcept;
[[nodiscard]] Vec3 soft_high_speed_damping(Vec3 velocity, double threshold, double damping, double dt) noexcept;
[[nodiscard]] Vec3 safety_clamp(Vec3 velocity, double absolute_speed) noexcept;
[[nodiscard]] Vec3 compose_impulse(Vec3 current_velocity, Vec3 impulse,
                                   double preservation, bool replace_z) noexcept;

// One state per simulated player movement component; reset after unsupported
// movement verbs. This does NOT execute a jump or teleport any actor. It only
// avoids speed loss from 1-2 walking frames between successive jump inputs.
struct BunnyhopChainState {
    bool previously_airborne{false};
    double grace_remaining{0.0};
    Vec3 last_air_velocity{};
    std::uint64_t landings{0};

    void reset() noexcept;

    // Called AFTER the engine's own velocity calculation on a WALKING frame,
    // but receives the pre-engine input velocity. May restore a sudden *aligned*
    // landing speed drop, while never undoing a changed-direction wall impact.
    // Returns seconds of this ground step to which friction should apply.
    [[nodiscard]] double begin_ground_step(Vec3& velocity, double dt,
                                           double landing_grace_seconds) noexcept;

    // Record actually applied post-step velocity; do not record on bypass modes.
    void record_air_step(Vec3 velocity) noexcept;
};
}
