if(NOT TARGET ffi)

    find_package(libffi CONFIG QUIET)

    if(libffi_FOUND)
        add_library(ffi INTERFACE)
        target_link_libraries(ffi INTERFACE libffi)
    else()
        message(FATAL_ERROR "libffi not found (install vcpkg libffi or system libffi-dev)")
    endif()

endif()