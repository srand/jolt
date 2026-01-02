cmake_minimum_required(VERSION 4.2)
project(app)
enable_language(CXX)

find_package(PkgConfig REQUIRED)
pkg_check_modules(LIB REQUIRED lib)

add_executable(${PROJECT_NAME} main.cpp)
set_target_properties(${PROJECT_NAME} PROPERTIES MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
target_include_directories(${PROJECT_NAME} PRIVATE ${LIB_INCLUDE_DIRS})
target_link_directories(${PROJECT_NAME} PRIVATE ${LIB_LIBRARY_DIRS})
target_link_libraries(${PROJECT_NAME} PRIVATE ${LIB_LIBRARIES})
install(TARGETS ${PROJECT_NAME} RUNTIME DESTINATION bin)
