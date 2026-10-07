cmake_minimum_required(VERSION 3.22)
project(MomentumNative LANGUAGES CXX)

add_library(MomentumNative SHARED
    src/MomentumNative.cpp
    ../momentum_core.cpp
)

target_compile_features(MomentumNative PRIVATE cxx_std_20)
target_link_libraries(MomentumNative PRIVATE advapi32)
set_target_properties(MomentumNative PROPERTIES OUTPUT_NAME "MomentumNative")
