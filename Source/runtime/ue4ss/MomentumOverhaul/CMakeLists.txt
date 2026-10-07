cmake_minimum_required(VERSION 3.22)
set(TARGET MomentumOverhaul)
project(${TARGET})

add_library(${TARGET} SHARED
    src/MomentumOverhaul.cpp
    ../../momentum_core.cpp
)

target_include_directories(${TARGET} PRIVATE
    include
    ../..
)

target_compile_features(${TARGET} PRIVATE cxx_std_23)
target_link_libraries(${TARGET} PRIVATE UE4SS)
set_target_properties(${TARGET} PROPERTIES OUTPUT_NAME "MomentumOverhaul")
