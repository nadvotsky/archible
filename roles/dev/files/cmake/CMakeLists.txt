cmake_minimum_required(VERSION 3.31)

project(cmake-template)
set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED True)

include_directories(src)
set(SOURCES src/util/util.cc)
set(TESTS test/util/util_test.cc)

add_executable(
    cmake-template
    src/main.cc
    ${SOURCES}
)
find_package(fmt)
target_link_libraries(cmake-template fmt::fmt)

enable_testing()
include(GoogleTest)
add_executable(
    cmake-template-test
    ${SOURCES}
    ${TESTS}
)
find_package(GTest REQUIRED)
target_link_libraries(
    cmake-template-test
    GTest::gtest_main
)
gtest_discover_tests(cmake-template-test)
