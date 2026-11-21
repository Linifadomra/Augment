include(ExternalProject)

set(AUGMENT_LIBFFI_VERSION "3.8.1")
set(AUGMENT_LIBFFI_SHA256 "81e879c094cc5ec3186c48510c6385ac6b3e866192e8bc71a35245703757ee40")

find_program(AUGMENT_MAKE_EXECUTABLE NAMES gmake make REQUIRED)

set(_augment_ffi_prefix "${CMAKE_BINARY_DIR}/_deps/libffi")
set(_augment_ffi_include "${_augment_ffi_prefix}/include")
set(_augment_ffi_library "${_augment_ffi_prefix}/lib/libffi.a")

set(_augment_ffi_proc "${CMAKE_SYSTEM_PROCESSOR}")
if(CMAKE_SYSTEM_NAME STREQUAL "Android" AND CMAKE_ANDROID_ARCH_ABI)
    set(_augment_ffi_proc "${CMAKE_ANDROID_ARCH_ABI}")
elseif(APPLE AND CMAKE_OSX_ARCHITECTURES)
    list(GET CMAKE_OSX_ARCHITECTURES 0 _augment_ffi_proc)
endif()
if(_augment_ffi_proc MATCHES "^(arm64|arm64-v8a|ARM64)$")
    set(_augment_ffi_proc "aarch64")
elseif(_augment_ffi_proc MATCHES "^(armeabi-v7a|armv7.*)$")
    set(_augment_ffi_proc "arm")
elseif(_augment_ffi_proc MATCHES "^(x86|i[3-6]86)$")
    set(_augment_ffi_proc "i686")
elseif(_augment_ffi_proc MATCHES "^(x86_64|AMD64|amd64)$")
    set(_augment_ffi_proc "x86_64")
endif()

get_filename_component(_augment_ffi_cc_name "${CMAKE_C_COMPILER}" NAME_WE)
if(CMAKE_SYSTEM_NAME STREQUAL "Android")
    if(_augment_ffi_proc STREQUAL "arm")
        set(_augment_ffi_host "arm-linux-androideabi")
    else()
        set(_augment_ffi_host "${_augment_ffi_proc}-linux-android")
    endif()
elseif(APPLE)
    set(_augment_ffi_host "${_augment_ffi_proc}-apple-darwin")
elseif(_augment_ffi_cc_name MATCHES "^(.+)-(gcc|cc|clang)$")
    set(_augment_ffi_host "${CMAKE_MATCH_1}")
else()
    set(_augment_ffi_host "${_augment_ffi_proc}-unknown-linux-gnu")
endif()

string(TOUPPER "${CMAKE_BUILD_TYPE}" _augment_ffi_config)
set(_augment_ffi_cflags "${CMAKE_C_FLAGS} ${CMAKE_C_FLAGS_${_augment_ffi_config}}")
set(_augment_ffi_target_flags "")
if(CMAKE_C_COMPILER_TARGET)
    string(APPEND _augment_ffi_target_flags " --target=${CMAKE_C_COMPILER_TARGET}")
endif()
if(CMAKE_SYSROOT)
    string(APPEND _augment_ffi_target_flags " --sysroot=${CMAKE_SYSROOT}")
endif()
if(APPLE)
    if(CMAKE_OSX_SYSROOT)
        string(APPEND _augment_ffi_target_flags " -isysroot ${CMAKE_OSX_SYSROOT}")
    endif()
    foreach(_augment_ffi_arch IN LISTS CMAKE_OSX_ARCHITECTURES)
        string(APPEND _augment_ffi_target_flags " -arch ${_augment_ffi_arch}")
    endforeach()
    if(CMAKE_OSX_DEPLOYMENT_TARGET AND CMAKE_SYSTEM_NAME STREQUAL "iOS")
        string(APPEND _augment_ffi_target_flags " -miphoneos-version-min=${CMAKE_OSX_DEPLOYMENT_TARGET}")
    elseif(CMAKE_OSX_DEPLOYMENT_TARGET)
        string(APPEND _augment_ffi_target_flags " -mmacosx-version-min=${CMAKE_OSX_DEPLOYMENT_TARGET}")
    endif()
endif()

set(_augment_ffi_script "${_augment_ffi_prefix}/configure.sh")
file(WRITE "${_augment_ffi_script}"
"#!/bin/sh
set -e
export CC=\"${CMAKE_C_COMPILER}\"
export CFLAGS=\"${_augment_ffi_target_flags} ${_augment_ffi_cflags}\"
export LDFLAGS=\"${_augment_ffi_target_flags} ${CMAKE_EXE_LINKER_FLAGS}\"
export AR=\"${CMAKE_AR}\"
export RANLIB=\"${CMAKE_RANLIB}\"
exec \"$1/configure\" \\
    --host=${_augment_ffi_host} \\
    --prefix=\"${_augment_ffi_prefix}\" \\
    --enable-static \\
    --disable-shared \\
    --with-pic \\
    --disable-docs \\
    --disable-multi-os-directory
")

ExternalProject_Add(augment_libffi
    URL "https://github.com/libffi/libffi/releases/download/v${AUGMENT_LIBFFI_VERSION}/libffi-${AUGMENT_LIBFFI_VERSION}.tar.gz"
    URL_HASH "SHA256=${AUGMENT_LIBFFI_SHA256}"
    DOWNLOAD_EXTRACT_TIMESTAMP TRUE
    PREFIX "${_augment_ffi_prefix}/ep"
    CONFIGURE_COMMAND sh "${_augment_ffi_script}" <SOURCE_DIR>
    BUILD_COMMAND "${AUGMENT_MAKE_EXECUTABLE}"
    INSTALL_COMMAND "${AUGMENT_MAKE_EXECUTABLE}" install
    BUILD_BYPRODUCTS "${_augment_ffi_library}"
)

file(MAKE_DIRECTORY "${_augment_ffi_include}")
add_library(ffi STATIC IMPORTED)
set_target_properties(ffi PROPERTIES
    IMPORTED_LOCATION "${_augment_ffi_library}"
    INTERFACE_INCLUDE_DIRECTORIES "${_augment_ffi_include}")
add_dependencies(ffi augment_libffi)
