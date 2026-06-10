if(NOT DEFINED AUGMENT_EXTRACT_SCRIPT)
    set(AUGMENT_EXTRACT_SCRIPT "${CMAKE_CURRENT_SOURCE_DIR}/tools/manifest/extract.py"
        CACHE FILEPATH "Path to extract.py")
endif()
if(NOT DEFINED AUGMENT_PACK_SCRIPT)
    set(AUGMENT_PACK_SCRIPT "${CMAKE_CURRENT_SOURCE_DIR}/tools/manifest/pack.py"
        CACHE FILEPATH "Path to pack.py")
endif()

function(augment_manifest)
    cmake_parse_arguments(AM "SEPARATE_TARGET" "TARGET;OUTPUT;JSON" "EXCLUDE;EXCLUDE_PREFIX" ${ARGN})
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

    if(WIN32 AND MSVC)
        target_compile_options(${AM_TARGET} PRIVATE $<$<CONFIG:Release>:/Zi>)
        set(_extract_src "$<TARGET_PDB_FILE:${AM_TARGET}>")
    else()
        target_compile_options(${AM_TARGET} PRIVATE $<$<CONFIG:Release>:-g>)
        set(_extract_src "$<TARGET_FILE:${AM_TARGET}>")
    endif()

    set(_target_bin $<TARGET_FILE:${AM_TARGET}>)

    if(AM_SEPARATE_TARGET)
        if(APPLE)
            set(_dbg "${_target_bin}.dSYM")
            add_custom_command(
                OUTPUT  "${AM_OUTPUT}" "${AM_JSON}"
                COMMAND dsymutil "${_target_bin}" -o "${_dbg}"
                COMMAND "${Python3_EXECUTABLE}" "${AUGMENT_EXTRACT_SCRIPT}"
                        "${_dbg}" "${AM_JSON}"
                COMMAND ${_pack_cmd}
                DEPENDS "${_target_bin}"
                VERBATIM
            )
        else()
            set(_strip_cmd "")
            if(NOT MSVC AND CMAKE_BUILD_TYPE STREQUAL "Release")
                set(_strip_cmd COMMAND "${CMAKE_OBJCOPY}" --strip-debug "${_target_bin}")
            endif()
            add_custom_command(
                OUTPUT  "${AM_OUTPUT}" "${AM_JSON}"
                COMMAND "${Python3_EXECUTABLE}" "${AUGMENT_EXTRACT_SCRIPT}"
                        "${_extract_src}" "${AM_JSON}"
                COMMAND ${_pack_cmd}
                ${_strip_cmd}
                DEPENDS "${_target_bin}"
                VERBATIM
            )
        endif()
        add_custom_target("gen_manifest"
            DEPENDS "${AM_OUTPUT}"
        )
        add_dependencies("gen_manifest" "${AM_TARGET}")
    else()
        if(APPLE)
            set(_dbg "${_target_bin}.dSYM")
            add_custom_command(TARGET ${AM_TARGET} POST_BUILD
                COMMAND dsymutil "${_target_bin}" -o "${_dbg}"
                COMMAND "${Python3_EXECUTABLE}" "${AUGMENT_EXTRACT_SCRIPT}"
                        "${_dbg}" "${AM_JSON}"
                COMMAND ${_pack_cmd}
                VERBATIM
            )
        else()
            add_custom_command(TARGET ${AM_TARGET} POST_BUILD
                COMMAND "${Python3_EXECUTABLE}" "${AUGMENT_EXTRACT_SCRIPT}"
                        "${_extract_src}" "${AM_JSON}"
                COMMAND ${_pack_cmd}
                VERBATIM
            )
            if(NOT MSVC AND CMAKE_BUILD_TYPE STREQUAL "Release")
                add_custom_command(TARGET ${AM_TARGET} POST_BUILD
                    COMMAND ${CMAKE_OBJCOPY} --strip-debug "${_target_bin}"
                    VERBATIM
                )
            endif()
        endif()
    endif()
endfunction()
