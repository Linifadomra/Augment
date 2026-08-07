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
            if(NOT APPLE)
                if(EXISTS "/usr/include/ffi.h")
                    set(FFI_INCLUDE_DIR "/usr/include")
                else()
                    find_path(FFI_INCLUDE_DIR NAMES ffi.h PATHS /usr/include /usr/local/include /usr/include/ffi /usr/local/include/ffi NO_CMAKE_FIND_ROOT_PATH)
                endif()
                if(EXISTS "/usr/lib/libffi.so")
                    set(FFI_LIBRARY "/usr/lib/libffi.so")
                else()
                    find_library(FFI_LIBRARY NAMES ffi libffi PATHS /usr/lib /usr/lib64 /usr/local/lib NO_CMAKE_FIND_ROOT_PATH)
                endif()
            else()
                find_path(FFI_INCLUDE_DIR NAMES ffi.h PATH_SUFFIXES ffi
                    HINTS
                        /opt/homebrew/opt/libffi/include
                        /usr/local/opt/libffi/include
                    NO_CMAKE_FIND_ROOT_PATH)
                find_library(FFI_LIBRARY NAMES ffi libffi
                    HINTS
                        /opt/homebrew/opt/libffi/lib
                        /usr/local/opt/libffi/lib
                    NO_CMAKE_FIND_ROOT_PATH)

                foreach(_pfx /opt/homebrew/opt/libffi /usr/local/opt/libffi)
                    if(NOT FFI_INCLUDE_DIR AND EXISTS "${_pfx}/include/ffi.h")
                        set(FFI_INCLUDE_DIR "${_pfx}/include")
                    endif()
                    if(NOT FFI_LIBRARY AND EXISTS "${_pfx}/lib/libffi.dylib")
                        set(FFI_LIBRARY "${_pfx}/lib/libffi.dylib")
                    endif()
                endforeach()
            else()
                find_path(FFI_INCLUDE_DIR NAMES ffi.h PATH_SUFFIXES ffi)
                find_library(FFI_LIBRARY NAMES ffi libffi)
            endif()

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