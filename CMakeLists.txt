cmake_minimum_required(VERSION 3.25)
project(Augment VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_CXX_VISIBILITY_PRESET hidden)
set(CMAKE_VISIBILITY_INLINES_HIDDEN ON)

# == OPTIONS ==
option(AUGMENT_TESTS            "Build the test suite"              OFF)
option(AUGMENT_INSTALL          "Enable install targets"            OFF)
option(AUGMENT_BUILD_EXAMPLES   "Build Augment examples"            OFF)
option(BUILD_SHARED_LIBS        "Build Augment as a shared library" OFF)
option(AUGMENT_USE_FETCHCONTENT "Build Augment using FetchContent"  ON )
option(AUGMENT_FFI              "Build libffi closure/call support" ON )

# == DEPENDENCIES ==
set(DOBBY_BUILD_SHARED OFF CACHE BOOL "" FORCE)
set(DOBBY_BUILD_STATIC ON CACHE BOOL "" FORCE)

if(WIN32)
    find_package(minhook CONFIG REQUIRED)
else() 
    add_subdirectory(vendor/dobby)
endif()

if(AUGMENT_FFI)
    include(${CMAKE_CURRENT_SOURCE_DIR}/cmake/libffi.cmake)
endif()

# == TARGETS ==
add_library(augment)
add_library(augment::augment ALIAS augment)

target_sources(augment PRIVATE
    src/runtime/registry.cpp
    src/runtime/chain.cpp
    src/runtime/conflict.cpp
    src/runtime/manifest.cpp
    src/runtime/introspect.cpp
    src/platform/hook_backend.cpp
    src/platform/selftest_probe_target.cpp
    src/platform/selftest_probe_replacement.cpp
    src/platform/sym_resolve.cpp
)

if(AUGMENT_FFI)
    target_sources(augment PRIVATE src/runtime/closure.cpp)
endif()

include(GenerateExportHeader)
generate_export_header(augment
    EXPORT_FILE_NAME include/augment/augment_export.h
    EXPORT_MACRO_NAME AUGMENT_API
)

target_include_directories(augment
    PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
        $<BUILD_INTERFACE:${CMAKE_CURRENT_BINARY_DIR}/include>
        $<INSTALL_INTERFACE:include>
        ${CMAKE_CURRENT_SOURCE_DIR}/vendor/dobby/include
    PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}/src
)

if(WIN32)
    target_link_libraries(augment PRIVATE minhook::minhook)
else()
    target_link_libraries(augment PUBLIC dobby)
endif()

if(AUGMENT_FFI)
    target_link_libraries(augment PUBLIC ffi)
    target_compile_definitions(augment PUBLIC AUGMENT_FFI=1)
else()
    target_compile_definitions(augment PUBLIC AUGMENT_FFI=0)
endif()

# == Codegen Helper Function ==
include(cmake/AugmentCodegen.cmake)
include(cmake/AugmentManifest.cmake)

# == Examples ==
if(AUGMENT_BUILD_EXAMPLES)
    add_subdirectory(examples)
endif()

# == Testing ==
if(AUGMENT_TESTS)
    enable_testing()
    add_subdirectory(tests)
endif()

# == Installation ==
if(AUGMENT_INSTALL)
    include(GNUInstallDirs)
    include(CMakePackageConfigHelpers)

    install(TARGETS augment
        EXPORT AugmentTargets
        ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}
        LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
        RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}
    )
    install(DIRECTORY include/augment
        DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}
    )
    install(EXPORT AugmentTargets
        FILE      AugmentTargets.cmake
        NAMESPACE augment::
        DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/Augment
    )
    write_basic_package_version_file(
        "${CMAKE_CURRENT_BINARY_DIR}/AugmentConfigVersion.cmake"
        VERSION       ${PROJECT_VERSION}
        COMPATIBILITY SameMajorVersion
    )
    configure_package_config_file(
        cmake/AugmentConfig.cmake.in
        "${CMAKE_CURRENT_BINARY_DIR}/AugmentConfig.cmake"
        INSTALL_DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/Augment
    )
    install(FILES
        "${CMAKE_CURRENT_BINARY_DIR}/AugmentConfig.cmake"
        "${CMAKE_CURRENT_BINARY_DIR}/AugmentConfigVersion.cmake"
        DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/Augment
    )
endif()