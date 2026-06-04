find_path(FFI_INCLUDE_DIR
    NAMES ffi.h
    PATHS
        "${VCPKG_INSTALLED_DIR}/${VCPKG_TARGET_TRIPLET}/include"
        "C:/vcpkg/installed/x64-windows/include"
)

find_library(FFI_LIBRARY
    NAMES ffi libffi
    PATHS
        "${VCPKG_INSTALLED_DIR}/${VCPKG_TARGET_TRIPLET}/lib"
        "C:/vcpkg/installed/x64-windows/lib"
)


if(NOT TARGET ffi)
    find_package(unofficial-libffi CONFIG QUIET)
    if(TARGET unofficial::libffi::libffi)
        add_library(ffi INTERFACE)
        target_link_libraries(ffi INTERFACE unofficial::libffi::libffi)
    else()
        find_path(FFI_INCLUDE_DIR NAMES ffi.h PATH_SUFFIXES ffi)
        find_library(FFI_LIBRARY NAMES ffi)
        if(NOT FFI_INCLUDE_DIR OR NOT FFI_LIBRARY)
            message(FATAL_ERROR "libffi not found (vcpkg: libffi, apt: libffi-dev, brew: libffi)")
        endif()
        add_library(ffi UNKNOWN IMPORTED)
        set_target_properties(ffi PROPERTIES
            IMPORTED_LOCATION "${FFI_LIBRARY}"
            INTERFACE_INCLUDE_DIRECTORIES "${FFI_INCLUDE_DIR}")
    endif()
endif()

