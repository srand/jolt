cmake_minimum_required(VERSION 4.2)
project(lib)
enable_language(CXX)

configure_file(
    lib.pc.in
    lib.pc
    @ONLY
)

add_library(${PROJECT_NAME} lib.cpp)
set_target_properties(${PROJECT_NAME} PROPERTIES PUBLIC_HEADER "lib.hpp")
set_target_properties(${PROJECT_NAME} PROPERTIES MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
install(
    TARGETS ${PROJECT_NAME}
    LIBRARY DESTINATION lib
    PUBLIC_HEADER DESTINATION include
)
install(
    FILES "${CMAKE_CURRENT_BINARY_DIR}/lib.pc"
    DESTINATION lib/pkgconfig
)
