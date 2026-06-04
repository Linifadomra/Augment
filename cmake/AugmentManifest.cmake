if(NOT DEFINED AUGMENT_MANIFEST_SCRIPT)
    set(AUGMENT_MANIFEST_SCRIPT
        "${CMAKE_CURRENT_SOURCE_DIR}/tools/manifest/dwarf_manifest.py"
        CACHE FILEPATH "Path to dwarf_manifest.py")
endif()

function(augment_manifest)
    cmake_parse_arguments(AM "" "TARGET;OUTPUT" "" ${ARGN})
    if(NOT AM_TARGET OR NOT AM_OUTPUT)
        message(FATAL_ERROR "augment_manifest: TARGET and OUTPUT are required")
    endif()

    find_package(Python3 COMPONENTS Interpreter REQUIRED)

    if(MSVC)
        target_compile_options(${AM_TARGET} PRIVATE $<$<CONFIG:Release>:/Zi>)
        message(WARNING "augment_manifest: no PDB manifest generator yet; ${AM_OUTPUT} not produced")
        return()
    endif()

    if(APPLE)
        target_compile_options(${AM_TARGET} PRIVATE $<$<CONFIG:Release>:-g>)
        add_custom_command(TARGET ${AM_TARGET} POST_BUILD
            COMMAND dsymutil $<TARGET_FILE:${AM_TARGET}> -o $<TARGET_FILE:${AM_TARGET}>.dSYM
            COMMAND ${Python3_EXECUTABLE} ${AUGMENT_MANIFEST_SCRIPT}
                    $<TARGET_FILE:${AM_TARGET}>.dSYM ${AM_OUTPUT}
            VERBATIM)
    else()
        target_compile_options(${AM_TARGET} PRIVATE $<$<CONFIG:Release>:-g>)
        add_custom_command(TARGET ${AM_TARGET} POST_BUILD
            COMMAND ${Python3_EXECUTABLE} ${AUGMENT_MANIFEST_SCRIPT}
                    $<TARGET_FILE:${AM_TARGET}> ${AM_OUTPUT}
            VERBATIM)
        if(CMAKE_BUILD_TYPE STREQUAL "Release")
            add_custom_command(TARGET ${AM_TARGET} POST_BUILD
                COMMAND ${CMAKE_OBJCOPY} --strip-debug $<TARGET_FILE:${AM_TARGET}>
                VERBATIM)
        endif()
    endif()
endfunction()
