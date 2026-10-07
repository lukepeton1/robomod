#include <cassert>
#include <cmath>
#include <iostream>
#include "../../Source/runtime/momentum_core.hpp"
static bool near(double a,double b,double t=1e-9){return std::abs(a-b)<=t;}
int main(){using namespace momentum;
 {Vec3 v{1050,0,0};for(int i=0;i<120;++i)v=accelerate_horizontal(v,{1,0,0},320,12,1.0/120.0);assert(near(v.horizontal_speed(),1050));}
 {Vec3 v{1050,0,0};for(int i=0;i<120;++i){double a=1.5707963267948966+(75.0*3.14159265358979323846/180.0)*((i+0.5)/120.0);v=accelerate_horizontal(v,{std::cos(a),std::sin(a),0},320,12,1.0/120.0);}assert(v.horizontal_speed()>1260);}
 {Vec3 in{1800,0,0};assert(apply_slide_friction(in,1.15,.25).horizontal_speed()>apply_ground_friction(in,7,220,.25).horizontal_speed());}
 {Vec3 d=compose_impulse({1500,250,100},{2600,0,0},1,false);assert(near.d.x,4100)&&near(d.y,250)&&near(d.z,100));}
 {Vec3 c=safety_clamp({50000,0,0},12000);assert(near.c.speed(),12000,1e-6));}
 std::cout<<"Momentum C++ core tests passed\n";}
