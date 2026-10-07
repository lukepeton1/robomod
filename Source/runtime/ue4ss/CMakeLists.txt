cmake_minimum_required(VERSION 3.22)
project(MomentumOverhaulRuntime)

if(NOT DEFINED UE4SS_SOURCE_DIR)
    message(FATAL_ERROR "UE4SS_SOURCE_DIR must point at the pinned RE-UE4SS source checkout")
endif()

add_subdirectory("${UE4SS_SOURCE_DIR}" "${CMAKE_BINARY_DIR}/RE-UE4SS")
add_subdirectory(MomentumOverhaul)
