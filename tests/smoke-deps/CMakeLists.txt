cmake_minimum_required(VERSION 3.27)
project(sdk_dependency_smoke LANGUAGES C CXX)
set(CMAKE_CXX_STANDARD 17)
find_package(ECM 6.24 REQUIRED NO_MODULE)
list(APPEND CMAKE_MODULE_PATH ${ECM_FIND_MODULE_DIR})
find_package(Qt6 REQUIRED COMPONENTS Widgets Svg Core5Compat PrintSupport Concurrent Xml Network Sql OpenGL OpenGLWidgets SvgWidgets Test Qml Quick QuickWidgets QuickControls2)
find_package(Qt6ShaderToolsPrivate REQUIRED)
find_package(KF6 REQUIRED COMPONENTS Config CoreAddons WidgetsAddons Completion GuiAddons I18n ItemViews ColorScheme)
find_package(PkgConfig REQUIRED)
# The SDK contains static libraries, including their private dependencies.
set(PKG_CONFIG_ARGN --static)
pkg_check_modules(Dependencies REQUIRED IMPORTED_TARGET zlib libpng lcms2 freetype2 harfbuzz fontconfig fribidi libunibreak)
find_package(exiv2 CONFIG REQUIRED)
find_package(QuaZip-Qt6 CONFIG REQUIRED)
find_package(Boost 1.69 CONFIG REQUIRED)
find_package(Eigen3 5 CONFIG REQUIRED)
find_package(Immer REQUIRED)
find_package(Zug REQUIRED)
find_package(Lager REQUIRED)
find_package(xsimd 14 CONFIG REQUIRED)
find_package(GSL REQUIRED)
qt_standard_project_setup()
qt_add_executable(sdk-deps main.cpp)
qt_add_qml_module(sdk-deps URI SdkDependencyProbe VERSION 1.0 RESOURCE_PREFIX /qt/qml QML_FILES Probe.qml)
target_compile_options(sdk-deps PRIVATE -fwasm-exceptions)
target_link_options(sdk-deps PRIVATE -fwasm-exceptions)
target_link_libraries(sdk-deps PRIVATE Qt6::Widgets Qt6::Svg Qt6::Core5Compat Qt6::PrintSupport Qt6::Qml Qt6::Quick Qt6::QuickWidgets Qt6::QuickControls2 Qt6::ShaderToolsPrivate
    KF6::ConfigCore KF6::CoreAddons KF6::WidgetsAddons KF6::Completion KF6::GuiAddons KF6::I18n KF6::ItemViews KF6::ColorScheme
    PkgConfig::Dependencies Exiv2::exiv2lib QuaZip::QuaZip Boost::headers Eigen3::Eigen immer zug lager xsimd GSL::gsl GSL::gslcblas)
set_target_properties(sdk-deps PROPERTIES QT_WASM_PTHREAD_POOL_SIZE 2)
target_link_options(sdk-deps PRIVATE -sASSERTIONS=1 --profiling-funcs
    "--preload-file=${SDK_TARGET}/share/krita-wasm-sdk/fonts@/fonts"
    "--preload-file=${SDK_TARGET}/etc/fonts@/etc/fonts"
    "--preload-file=${SDK_TARGET}/usr/share/fontconfig/conf.avail@/usr/share/fontconfig/conf.avail")
