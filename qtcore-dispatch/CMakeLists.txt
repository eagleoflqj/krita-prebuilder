cmake_minimum_required(VERSION 3.22)
project(qtcore_dispatch_correction LANGUAGES CXX)
find_package(Qt6 6.10.2 EXACT REQUIRED COMPONENTS Core CorePrivate)
add_library(dispatch OBJECT "${QT_SOURCE}/src/corelib/platform/wasm/qwasmsuspendresumecontrol.cpp")
target_link_libraries(dispatch PRIVATE Qt6::CorePrivate)
target_compile_features(dispatch PRIVATE cxx_std_17)
target_compile_definitions(dispatch PRIVATE QT_BUILD_CORE_LIB)
target_compile_options(dispatch PRIVATE -pthread -fwasm-exceptions
    "-ffile-prefix-map=${QT_SOURCE}=/qtbase" "-ffile-prefix-map=${BASE_SDK}=/sdk")
