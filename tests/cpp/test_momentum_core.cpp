#include <cassert>
#include <cmath>
#include <iostream>
#include "../../Source/runtime/momentum_core.hpp"

static bool near(double a, double b, double t = 1e-9) {
    return std::abs(a - b) <= t;
}

int main() {
    using namespace momentum;
    const double dt = 1.0 / 120.0;

    // Existing projection, slide, impulse and emergency guards stay intact.
    {
        Vec3 v{1050, 0, 0};
        for (int i = 0; i < 120; ++i)
            v = accelerate_horizontal(v, {1, 0, 0}, 320, 12, dt);
        assert(near(v.horizontal_speed(), 1050));
    }
    {
        Vec3 v{1050, 0, 0};
        for (int i = 0; i < 120; ++i) {
            const double angle = 1.5707963267948966
                + (75.0 * 3.14159265358979323846 / 180.0) * ((i + 0.5) / 120.0);
            v = accelerate_horizontal(v, {std::cos(angle), std::sin(angle), 0}, 320, 12, dt);
        }
        assert(v.horizontal_speed() > 1260);
    }
    {
        Vec3 in{1800, 0, 0};
        assert(apply_slide_friction(in, 1.15, .25).horizontal_speed()
               > apply_ground_friction(in, 7, 220, .25).horizontal_speed());
    }
    {
        Vec3 d = compose_impulse({1500, 250, 100}, {2600, 0, 0}, 1, false);
        assert(near(d.x, 4100) && near(d.y, 250) && near(d.z, 100));
    }
    {
        Vec3 c = safety_clamp({50000, 0, 0}, 30000);
        assert(near(c.speed(), 30000, 1e-6));
    }

    // Pure forward holding does NOT make free speed; strafing must create it.
    {
        Vec3 v{1050, 0, 0};
        for (int i = 0; i < 120; ++i)
            v = air_accelerate_source(v, {1, 0, 0}, 1050, 320, 9, dt);
        assert(near(v.horizontal_speed(), 1050));
        Vec3 zero = air_accelerate_source(v, {}, 1050, 320, 9, dt);
        assert(near(zero.horizontal_speed(), 1050));
    }

    // Key CS-like behavior: dynamically coordinated A/D + mouse strafe
    // increases total speed during each hop. Repeat eight times, never
    // clamping to MaxWalkSpeed=1050 between jumps.
    {
        BunnyhopChainState state;
        Vec3 v{1050, 0, 0};
        double prevHopSpeed = v.horizontal_speed();

        for (int hop = 0; hop < 8; ++hop) {
            // Simulate 0.35 sec of skillful air strafing, constantly adjusting
            // to keep wish direction mostly perpendicular to actual velocity.
            for (int frame = 0; frame < 42; ++frame) {
                const double speed = v.horizontal_speed();
                const Vec3 forward = v.normalized2();
                const double cosAngle = std::min(0.3, 160.0 / speed);
                const double sinAngle = std::sqrt(1.0 - cosAngle * cosAngle);
                const Vec3 strafe{
                    cosAngle * forward.x - sinAngle * forward.y,
                    cosAngle * forward.y + sinAngle * forward.x,
                    0
                };
                v = air_accelerate_source(v, strafe, 1050, 320, 9, dt);
                state.record_air_step(v);
            }
            const double airborneSpeed = v.horizontal_speed();
            assert(airborneSpeed > prevHopSpeed + 10.0);

            // Clean landing / rapid jump within 90 ms cannot apply friction.
            for (int groundFrame = 0; groundFrame < 8; ++groundFrame) {
                const double frictionDt = state.begin_ground_step(v, dt, 0.09);
                v = apply_ground_friction(v, 7, 220, frictionDt);
            }
            assert(near(v.horizontal_speed(), airborneSpeed, 1e-6));
            prevHopSpeed = v.horizontal_speed();
        }
        assert(v.horizontal_speed() > 3000.0);
        assert(state.landings == 8);
    }

    // Miss the hop window and friction must resume, so timing is meaningful.
    {
        BunnyhopChainState state;
        state.record_air_step({2000, 0, -300});
        Vec3 v{2000, 0, 0};
        double elapsed = 0.0;
        for (int i = 0; i < 30; ++i) {
            const double frictionDt = state.begin_ground_step(v, dt, 0.09);
            v = apply_ground_friction(v, 7, 220, frictionDt);
            elapsed += frictionDt;
        }
        assert(elapsed > 0.15);
        assert(v.horizontal_speed() < 1000.0);
    }

    // The engine can clip horizontal velocity on landing. Restore it only if
    // direction is substantially unchanged; never undo a wall collision.
    {
        BunnyhopChainState state;
        state.record_air_step({2500, 0, 0});
        Vec3 v{1700, 0, 0};
        (void)state.begin_ground_step(v, dt, 0.09);
        assert(near(v.horizontal_speed(), 2500));
    }
    {
        BunnyhopChainState state;
        state.record_air_step({2500, 0, 0});
        Vec3 v{0, 950, 0};
        (void)state.begin_ground_step(v, dt, 0.09);
        assert(near(v.horizontal_speed(), 950));
    }

    // Repeated D->A->D->A air-strafe reversals with matching mouse turns.
    // Switching strafe sign must NOT reset velocity. The wish direction
    // remains mostly perpendicular to the accumulated momentum.
    {
        Vec3 v{1050, 0, 0};
        for (int frame = 0; frame < 120; ++frame) {
            const double priorSpeed = v.horizontal_speed();
            const int strafeSign = ((frame / 30) % 2 == 0) ? 1 : -1;
            const Vec3 direction = v.normalized2();
            const double forwardPart = std::min(0.3, 160.0 / priorSpeed);
            const double sidewaysPart = std::sqrt(1.0 - forwardPart * forwardPart);
            const Vec3 alternatingWish{
                forwardPart * direction.x - strafeSign * sidewaysPart * direction.y,
                forwardPart * direction.y + strafeSign * sidewaysPart * direction.x,
                0.0
            };
            v = air_accelerate_source(v, alternatingWish, 1050, 320, 9, dt);
            assert(v.horizontal_speed() + 1e-8 >= priorSpeed);
        }
        assert(v.horizontal_speed() > 2100.0);
    }

    std::cout << "Momentum C++ core + 8-hop + alternating-strafe tests passed\n";
}
