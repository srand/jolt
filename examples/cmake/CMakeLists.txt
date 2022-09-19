cmake_minimum_required(VERSION 3.5)

project(helloworld LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
include_directories(include)
set(SOURCES src/main.cpp src/funcs.cpp)

add_executable(helloworld ${SOURCES})

install(TARGETS helloworld
        DESTINATION bin)