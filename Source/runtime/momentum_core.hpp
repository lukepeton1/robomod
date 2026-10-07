#pragma once
#include <algorithm>
#include <cmath>
namespace momentum {
struct Vec3 {
    double x{}; double y{}; double z{};
    constexpr Vec3 operator+(const Vec3& o) const noexcept { return {x+o.x,y+o.y,z+o.z}; }
    constexpr Vec3 operator-(const Vec3& o) const noexcept { return {x-o.x,y-o.y,z-o.z}; }
    constexpr Vec3 operator*(double s) const noexcept { return {x*s,y*s,z*s}; }
    [[nodiscard]] double horizontal_speed() const noexcept { return std::hypot(x,y); }
    [[nodiscard]] double speed() const noexcept { return std::sqrt(x*x+y*y+z*z); }
    [[nodiscard]] double dot2(const Vec3& o) const noexcept { return x*o.x+y*o.y; }
    [[nodiscard]] Vec3 normalized2() const noexcept { const double m=horizontal_speed(); return m<=1e-12?Vec3{}:Vec3{x/m,y/m,0.0}; }
};
[[nodiscard]] Vec3 accelerate_horizontal(Vec3 velocity, Vec3 wish_direction, double wish_speed, double acceleration, double dt) noexcept;
[[nodiscard]] double friction_speed(double speed, double friction, double stop_speed, double dt) noexcept;
[[nodiscard]] Vec3 apply_ground_friction(Vec3 velocity, double friction, double stop_speed, double dt) noexcept;
[[nodiscard]] Vec3 apply_slide_friction(Vec3 velocity, double friction, double dt) noexcept;
[[nodiscard]] Vec3 soft_high_speed_damping(Vec3 velocity, double threshold, double damping, double dt) noexcept;
[[nodiscard]] Vec3 safety_clamp(Vec3 velocity, double absolute_speed) noexcept;
[[nodiscard]] Vec3 compose_impulse(Vec3 current_velocity, Vec3 impulse, double preservation, bool replace_z) noexcept;
}
