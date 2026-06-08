if(NOT DEFINED AUGMENT_EXTRACT_SCRIPT)
    set(AUGMENT_EXTRACT_SCRIPT "${CMAKE_CURRENT_SOURCE_DIR}/tools/manifest/extract.py"
        CACHE FILEPATH "Path to extract.py")
endif()
if(NOT DEFINED AUGMENT_PACK_SCRIPT)
    set(AUGMENT_PACK_SCRIPT "${CMAKE_CURRENT_SOURCE_DIR}/tools/manifest/pack.py"
        CACHE FILEPATH "Path to pack.py")
endif()

function(augment_manifest)
    cmake_parse_arguments(AM "" "TARGET;OUTPUT;JSON" "EXCLUDE;EXCLUDE_PREFIX" ${ARGN})
    find_package(Python3 REQUIRED COMPONENTS Interpreter)

    if(NOT AM_TARGET OR NOT AM_OUTPUT)
        message(FATAL_ERROR "augment_manifest: TARGET and OUTPUT are required")
    endif()

    if(NOT AM_JSON)
        set(AM_JSON "${AM_OUTPUT}.json")
    endif()

    set(_excl_file "")
    if(AM_EXCLUDE)
        set(_excl_file "${CMAKE_CURRENT_BINARY_DIR}/${AM_TARGET}_exclude.txt")
        list(JOIN AM_EXCLUDE "\n" _excl_content)
        file(WRITE "${_excl_file}" "${_excl_content}\n")
    endif()

    set(_excl_prefix_file "")
    if(AM_EXCLUDE_PREFIX)
        set(_excl_prefix_file "${CMAKE_CURRENT_BINARY_DIR}/${AM_TARGET}_exclude_prefix.txt")
        list(JOIN AM_EXCLUDE_PREFIX "\n" _excl_prefix_content)
        file(WRITE "${_excl_prefix_file}" "${_excl_prefix_content}\n")
    endif()

    set(_pack_cmd
        "${Python3_EXECUTABLE}" "${AUGMENT_PACK_SCRIPT}"
        "${AM_JSON}" "${AM_OUTPUT}"
    )
    if(_excl_file)
        list(APPEND _pack_cmd "--exclude-file" "${_excl_file}")
    endif()
    if(_excl_prefix_file)
        list(APPEND _pack_cmd "--exclude-prefix-file" "${_excl_prefix_file}")
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
            COMMAND ${_pack_cmd}
            VERBATIM)
    else()
        add_custom_command(TARGET ${AM_TARGET} POST_BUILD
            COMMAND ${Python3_EXECUTABLE} ${AUGMENT_EXTRACT_SCRIPT} $<TARGET_FILE:${AM_TARGET}> ${AM_JSON}
            COMMAND ${_pack_cmd}
            VERBATIM)
        if(CMAKE_BUILD_TYPE STREQUAL "Release")
            add_custom_command(TARGET ${AM_TARGET} POST_BUILD
                COMMAND ${CMAKE_OBJCOPY} --strip-debug $<TARGET_FILE:${AM_TARGET}>
                VERBATIM)
        endif()
    endif()
endfunction()
