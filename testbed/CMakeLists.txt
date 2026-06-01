cmake_minimum_required(VERSION 3.10)
project(Testbed)

option(FEATURE_A "Enable Feature A" OFF)
option(FEATURE_B "Enable Feature B" OFF)
option(DEAD_FEATURE "A feature that is never reached" OFF)

add_executable(testbed main.cpp)

if(FEATURE_A)
    target_compile_definitions(testbed PRIVATE FEATURE_A)
endif()
if(FEATURE_B)
    target_compile_definitions(testbed PRIVATE FEATURE_B)
endif()
if(DEAD_FEATURE)
    target_compile_definitions(testbed PRIVATE DEAD_FEATURE)
endif()
