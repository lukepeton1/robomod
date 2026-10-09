#include "momentum_core.hpp"
#include <algorithm>
#include <cmath>

namespace momentum {

Vec3 accelerate_horizontal(Vec3 v, Vec3 wish, double wish_speed, double accel, double dt) noexcept {
    const Vec3 d = wish.normalized2();
    if (d.horizontal_speed() <= 1e-12 || wish_speed <= 0.0 || accel <= 0.0 || dt <= 0.0) return v;
    const double add = wish_speed - v.dot2(d);
    if (add <= 0.0) return v;
    const double amount = std::min(add, accel * wish_speed * dt);
    v.x += d.x * amount;
    v.y += d.y * amount;
    return v;
}

Vec3 air_accelerate_source(Vec3 v, Vec3 wish, double full_wish_speed,
                            double projection_cap, double accel, double dt) noexcept {
    if (full_wish_speed <= 0.0 || projection_cap <= 0.0 ||
        accel <= 0.0 || dt <= 0.0) return v;
    const Vec3 d = wish.normalized2();
    if (d.horizontal_speed() <= 1e-12) return v;

    // Source's crucial distinction: the requested speed may be 1050 cm/s
    // while the allowable projected component is much smaller (e.g. 320).
    const double allowed_projection = std::min(full_wish_speed, projection_cap);
    const double add = allowed_projection - v.dot2(d);
    if (add <= 0.0) return v;

    const double impulse = std::min(add, accel * full_wish_speed * dt);
    v.x += d.x * impulse;
    v.y += d.y * impulse;
    return v;
}

double friction_speed(double speed, double friction, double stop, double dt) noexcept {
    if (speed <= 0.0) return 0.0;
    if (friction <= 0.0 || dt <= 0.0) return speed;
    if (speed > stop && stop > 0.0) {
        const double t = std::log(speed / stop) / friction;
        if (dt <= t) return speed * std::exp(-friction * dt);
        dt -= t;
        speed = stop;
    }
    return std::max(0.0, speed - friction * stop * dt);
}

Vec3 apply_ground_friction(Vec3 v, double friction, double stop, double dt) noexcept {
    const double s = v.horizontal_speed();
    if (s <= 1e-12) { v.x = 0.0; v.y = 0.0; return v; }
    const double ns = friction_speed(s, friction, stop, dt);
    const double k = ns / s;
    v.x *= k;
    v.y *= k;
    return v;
}

Vec3 apply_slide_friction(Vec3 v, double friction, double dt) noexcept {
    if (friction <= 0.0 || dt <= 0.0) return v;
    const double k = std::exp(-friction * dt);
    v.x *= k; v.y *= k;
    return v;
}

Vec3 soft_high_speed_damping(Vec3 v, double threshold, double damping, double dt) noexcept {
    const double s = v.horizontal_speed();
    if (s <= threshold || damping <= 0.0 || dt <= 0.0) return v;
    const double ns = threshold + (s - threshold) * std::exp(-damping * dt);
    const double k = ns / s;
    v.x *= k; v.y *= k;
    return v;
}

Vec3 safety_clamp(Vec3 v, double limit) noexcept {
    const double s = v.speed();
    if (limit <= 0.0 || s <= limit || s <= 1e-12) return v;
    return v * (limit / s);
}

Vec3 compose_impulse(Vec3 v, Vec3 impulse, double preserve, bool replace_z) noexcept {
    Vec3 out{v.x * preserve + impulse.x, v.y * preserve + impulse.y, v.z};
    out.z = replace_z ? impulse.z : v.z * preserve + impulse.z;
    return out;
}

void BunnyhopChainState::reset() noexcept {
    previously_airborne = false;
    grace_remaining = 0.0;
    last_air_velocity = {};
    landings = 0;
}

double BunnyhopChainState::begin_ground_step(Vec3& velocity, double dt,
                                             double landing_grace_seconds) noexcept {
    if (dt <= 0.0) return 0.0;

    if (previously_airborne) {
        previously_airborne = false;
        ++landings;
        grace_remaining = std::max(0.0, landing_grace_seconds);

        // The game may clamp horizontal speed on the landing transition
        // BEFORE CalcVelocity. Restore only when its direction is still almost
        // identical to the last air velocity; wall/obstacle impacts are NOT
        // eligible. Never fabricate additional speed beyond what was earned.
        const double air_speed = last_air_velocity.horizontal_speed();
        const double landed_speed = velocity.horizontal_speed();
        if (air_speed > 0.0 && landed_speed > 1.0 &&
            air_speed > landed_speed &&
            velocity.dot2(last_air_velocity) / (landed_speed * air_speed) > 0.985) {
            const double ratio = air_speed / landed_speed;
            velocity.x *= ratio;
            velocity.y *= ratio;
        }
    }

    // Framerate-independent grace: any fractional remainder beyond the grace
    // on this step still takes friction. Missing the window costs actual speed.
    const double protected_time = std::min(std::max(0.0, grace_remaining), dt);
    grace_remaining = std::max(0.0, grace_remaining - dt);
    return dt - protected_time;
}

void BunnyhopChainState::record_air_step(Vec3 velocity) noexcept {
    previously_airborne = true;
    last_air_velocity = velocity;
    grace_remaining = 0.0;
}

}
