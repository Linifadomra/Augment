if(NOT DEFINED AUGMENT_EXTRACT_SCRIPT)
    set(AUGMENT_EXTRACT_SCRIPT "${CMAKE_CURRENT_SOURCE_DIR}/tools/extractor/extract.py"
        CACHE FILEPATH "Path to extract.py")
endif()

function(augment_manifest)
    cmake_parse_arguments(AM "SEPARATE_TARGET"
        "TARGET;OUTPUT;COMPILE_COMMANDS"
        "EXCLUDE;EXCLUDE_PREFIX"
        ${ARGN})
    find_package(Python3 REQUIRED COMPONENTS Interpreter)

    if(NOT AM_TARGET OR NOT AM_OUTPUT)
        message(FATAL_ERROR "augment_manifest: TARGET and OUTPUT are required")
    endif()

    if(NOT AM_COMPILE_COMMANDS)
        set(AM_COMPILE_COMMANDS "${CMAKE_BINARY_DIR}/compile_commands.json")
    endif()

    set(_excl_args "")
    if(AM_EXCLUDE)
        set(_excl_file "${CMAKE_CURRENT_BINARY_DIR}/${AM_TARGET}_exclude.txt")
        list(JOIN AM_EXCLUDE "\n" _excl_content)
        file(WRITE "${_excl_file}" "${_excl_content}\n")
        list(APPEND _excl_args "--exclude-file" "${_excl_file}")
    endif()
    if(AM_EXCLUDE_PREFIX)
        set(_excl_prefix_file "${CMAKE_CURRENT_BINARY_DIR}/${AM_TARGET}_exclude_prefix.txt")
        list(JOIN AM_EXCLUDE_PREFIX "\n" _excl_prefix_content)
        file(WRITE "${_excl_prefix_file}" "${_excl_prefix_content}\n")
        list(APPEND _excl_args "--exclude-prefix-file" "${_excl_prefix_file}")
    endif()

    set(_target_bin $<TARGET_FILE:${AM_TARGET}>)

    if(WIN32 AND MSVC)
        target_compile_options(${AM_TARGET} PRIVATE /Zi)
        set(_extract_src "$<TARGET_PDB_FILE:${AM_TARGET}>")
        set(_fmt_arg "--debug-format" "pdb")
    else()
        target_compile_options(${AM_TARGET} PRIVATE -g)
        set(_extract_src "${_target_bin}")
        set(_fmt_arg "--debug-format" "dwarf")
    endif()

    cmake_path(GET AUGMENT_EXTRACT_SCRIPT PARENT_PATH _extract_script_dir)
    cmake_path(GET _extract_script_dir PARENT_PATH _extract_tools_dir)

    set(_extract_cmd
        "${CMAKE_COMMAND}" -E env "PYTHONPATH=${_extract_tools_dir}"
        "${Python3_EXECUTABLE}" -u "${AUGMENT_EXTRACT_SCRIPT}"
        "--binary"            "${_extract_src}"
        "--compile-commands"  "${AM_COMPILE_COMMANDS}"
        "--output"            "${AM_OUTPUT}"
        "--project-root"      "${CMAKE_SOURCE_DIR}"
        ${_fmt_arg}
        ${_excl_args}
    )

    cmake_path(REPLACE_EXTENSION AM_OUTPUT LAST_ONLY ".json" OUTPUT_VARIABLE _json_out)
    set(_agmf_out "${AM_OUTPUT}") 

    if(AM_SEPARATE_TARGET)
        if(APPLE)
            set(_dbg "${_target_bin}.dSYM")
            add_custom_command(
                OUTPUT  "${_agmf_out}" "${_json_out}"
                COMMAND dsymutil "${_target_bin}" -o "${_dbg}"
                COMMAND ${_extract_cmd} "--binary" "${_dbg}"
                DEPENDS "${_target_bin}"
                USES_TERMINAL
                VERBATIM
            )
        else()
            set(_strip_cmd "")
            if(NOT MSVC AND CMAKE_BUILD_TYPE STREQUAL "Release")
                set(_strip_cmd COMMAND "${CMAKE_OBJCOPY}" --strip-debug "${_target_bin}")
            endif()
            add_custom_command(
                OUTPUT  "${_agmf_out}" "${_json_out}"
                COMMAND ${_extract_cmd}
                ${_strip_cmd}
                DEPENDS "${_target_bin}"
                USES_TERMINAL
                VERBATIM
            )
        endif()
        add_custom_target("gen_manifest"
            DEPENDS "${_agmf_out}"
        )
        add_dependencies("gen_manifest" "${AM_TARGET}")
    else()
        if(APPLE)
            set(_dbg "${_target_bin}.dSYM")
            add_custom_command(TARGET ${AM_TARGET} POST_BUILD
                COMMAND dsymutil "${_target_bin}" -o "${_dbg}"
                COMMAND ${_extract_cmd} "--binary" "${_dbg}"
                USES_TERMINAL
                VERBATIM
            )
        else()
            add_custom_command(TARGET ${AM_TARGET} POST_BUILD
                COMMAND ${_extract_cmd}
                USES_TERMINAL
                VERBATIM
            )
            if(NOT MSVC AND CMAKE_BUILD_TYPE STREQUAL "Release")
                add_custom_command(TARGET ${AM_TARGET} POST_BUILD
                    COMMAND ${CMAKE_OBJCOPY} --strip-debug "${_target_bin}"
                    USES_TERMINAL
                    VERBATIM
                )
            endif()
        endif()
    endif()
endfunction()
