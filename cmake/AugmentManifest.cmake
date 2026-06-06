if(NOT DEFINED AUGMENT_EXTRACT_SCRIPT)
    set(AUGMENT_EXTRACT_SCRIPT "${CMAKE_CURRENT_SOURCE_DIR}/tools/manifest/extract.py"
        CACHE FILEPATH "Path to extract.py")
endif()
if(NOT DEFINED AUGMENT_PACK_SCRIPT)
    set(AUGMENT_PACK_SCRIPT "${CMAKE_CURRENT_SOURCE_DIR}/tools/manifest/pack.py"
        CACHE FILEPATH "Path to pack.py")
endif()

function(augment_manifest)
    cmake_parse_arguments(AM "" "TARGET;OUTPUT;JSON" "" ${ARGN})
    if(NOT AM_TARGET OR NOT AM_OUTPUT)
        message(FATAL_ERROR "augment_manifest: TARGET and OUTPUT are required")
    endif()
    if(NOT AM_JSON)
        set(AM_JSON "${AM_OUTPUT}.json")
    endif()
    if(MSVC)
        target_compile_options(${AM_TARGET} PRIVATE $<$<CONFIG:Release>:/Zi>)
        message(WARNING "augment_manifest: PDB extractor not implemented yet; ${AM_OUTPUT} not produced (must emit manifest.json schema v2)")
        return()
    endif()
    find_package(Python3 COMPONENTS Interpreter REQUIRED)

    target_compile_options(${AM_TARGET} PRIVATE $<$<CONFIG:Release>:-g>)
    if(APPLE)
        set(_dbg $<TARGET_FILE:${AM_TARGET}>.dSYM)
        add_custom_command(TARGET ${AM_TARGET} POST_BUILD
            COMMAND dsymutil $<TARGET_FILE:${AM_TARGET}> -o ${_dbg}
            COMMAND ${Python3_EXECUTABLE} ${AUGMENT_EXTRACT_SCRIPT} ${_dbg} ${AM_JSON}
            COMMAND ${Python3_EXECUTABLE} ${AUGMENT_PACK_SCRIPT} ${AM_JSON} ${AM_OUTPUT}
            VERBATIM)
    else()
        add_custom_command(TARGET ${AM_TARGET} POST_BUILD
            COMMAND ${Python3_EXECUTABLE} ${AUGMENT_EXTRACT_SCRIPT} $<TARGET_FILE:${AM_TARGET}> ${AM_JSON}
            COMMAND ${Python3_EXECUTABLE} ${AUGMENT_PACK_SCRIPT} ${AM_JSON} ${AM_OUTPUT}
            VERBATIM)
        if(CMAKE_BUILD_TYPE STREQUAL "Release")
            add_custom_command(TARGET ${AM_TARGET} POST_BUILD
                COMMAND ${CMAKE_OBJCOPY} --strip-debug $<TARGET_FILE:${AM_TARGET}>
                VERBATIM)
        endif()
    endif()
endfunction()
