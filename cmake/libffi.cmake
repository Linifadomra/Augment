if(NOT TARGET ffi)

    find_package(unofficial-libffi CONFIG QUIET)

    if(TARGET unofficial::libffi::libffi)
        add_library(ffi INTERFACE)
        target_link_libraries(ffi INTERFACE unofficial::libffi::libffi)

    else()

        find_package(libffi CONFIG QUIET)

        if(TARGET libffi::ffi)
            add_library(ffi INTERFACE)
            target_link_libraries(ffi INTERFACE libffi::ffi)

        elseif(TARGET libffi::libffi)
            add_library(ffi INTERFACE)
            target_link_libraries(ffi INTERFACE libffi::libffi)

        else()

            find_path(FFI_INCLUDE_DIR NAMES ffi.h PATH_SUFFIXES ffi)
            find_library(FFI_LIBRARY NAMES ffi libffi)

            if(NOT FFI_INCLUDE_DIR OR NOT FFI_LIBRARY)
                message(FATAL_ERROR
                    "libffi not found "
                    "(vcpkg: libffi, apt: libffi-dev, brew: libffi)")
            endif()

            add_library(ffi UNKNOWN IMPORTED)
            set_target_properties(ffi PROPERTIES
                IMPORTED_LOCATION "${FFI_LIBRARY}"
                INTERFACE_INCLUDE_DIRECTORIES "${FFI_INCLUDE_DIR}")
        endif()
    endif()
endif()