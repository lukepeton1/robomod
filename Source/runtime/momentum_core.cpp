#include "momentum_core.hpp"
namespace momentum {
Vec3 accelerate_horizontal(Vec3 v, Vec3 wish, double wish_speed, double accel, double dt) noexcept {
    const Vec3 d=wish.normalized2();
    if(d.horizontal_speed()<=1e-12||wish_speed<=0.0||dt<=0.0) return v;
    const double add=wish_speed-v.dot2(d); if(add<=0.0) return v;
    const double amount=std::min(add,accel*wish_speed*dt); v.x+=d.x*amount; v.y+=d.y*amount; return v;
}
double friction_speed(double speed,double friction,double stop,double dt) noexcept {
    if(speed<=0.0) return 0.0; if(friction<=0.0||dt<=0.0) return speed;
    if(speed>stop&&stop>0.0){ const double t=std::log(speed/stop)/friction; if(dt<=t) return speed*std::exp(-friction*dt); dt-=t; speed=stop; }
    return std::max(0.0,speed-friction*stop*dt);
}
Vec3 apply_ground_friction(Vec3 v,double friction,double stop,double dt) noexcept {
    const double s=v.horizontal_speed(); if(s<=1e-12){v.x=0;v.y=0;return v;} const double ns=friction_speed(s,friction,stop,dt); const double k=ns/s; v.x*=k;v.y*=k;return v;
}
Vec3 apply_slide_friction(Vec3 v,double friction,double dt) noexcept { if(friction<=0||dt<=0)return v; const double k=std::exp(-friction*dt);v.x*=k;v.y*=k;return v; }
Vec3 soft_high_speed_damping(Vec3 v,double threshold,double damping,double dt) noexcept { const double s=v.horizontal_speed(); if(s<=threshold||damping<=0||dt<=0)return v; const double ns=threshold+(s-threshold)*std::exp(-damping*dt); const double k=ns/s;v.x*=k;v.y*=k;return v; }
Vec3 safety_clamp(Vec3 v,double limit) noexcept { const double s=v.speed(); if(limit<=0||s<=limit||s<=1e-12)return v; return v*(limit/s); }
Vec3 compose_impulse(Vec3 v,Vec3 impulse,double preserve,bool replace_z) noexcept { Vec3 out{v.x*preserve+impulse.x,v.y*preserve+impulse.y,v.z}; out.z=replace_z?impulse.z:v.z*preserve+impulse.z; return out; }
}
