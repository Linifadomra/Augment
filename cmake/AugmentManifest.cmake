if(NOT DEFINED AUGMENT_EXTRACT_SCRIPT)
    set(AUGMENT_EXTRACT_SCRIPT "${CMAKE_CURRENT_SOURCE_DIR}/tools/extractor/extract.py"
        CACHE FILEPATH "Path to extract.py")
endif()

function(augment_manifest)
    cmake_parse_arguments(AM "SEPARATE_TARGET;REGENERATE_AST"
        "TARGET;OUTPUT;COMPILE_COMMANDS;PROJECT_ROOT;REGISTRY_OUT;PCH_OUT;AST_MANIFEST_HINT_DIR"
        "EXCLUDE;EXCLUDE_PREFIX;EXCLUDE_PATH"
        ${ARGN})
    find_package(Python3 REQUIRED COMPONENTS Interpreter)

    if(NOT AM_TARGET OR NOT AM_OUTPUT)
        message(FATAL_ERROR "augment_manifest: TARGET and OUTPUT are required")
    endif()

    if(NOT AM_COMPILE_COMMANDS)
        set(AM_COMPILE_COMMANDS "${CMAKE_BINARY_DIR}/compile_commands.json")
    endif()

    if(NOT AM_PROJECT_ROOT)
        set(AM_PROJECT_ROOT "${CMAKE_SOURCE_DIR}")
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
    if(AM_EXCLUDE_PATH)
        foreach(_frag ${AM_EXCLUDE_PATH})
            list(APPEND _excl_args "--exclude-path" "${_frag}")
        endforeach()
    endif()

    set(_target_bin $<TARGET_FILE:${AM_TARGET}>)

    if(WIN32 AND MSVC)
        target_compile_options(${AM_TARGET} PRIVATE
            $<$<NOT:$<OR:$<CONFIG:RelWithDebInfo>,$<CONFIG:Debug>>>:/Zi>
        )
        set(_extract_src "$<TARGET_PDB_FILE:${AM_TARGET}>")
        set(_fmt_arg "--debug-format" "pdb")
    else()
        target_compile_options(${AM_TARGET} PRIVATE
            $<$<NOT:$<OR:$<CONFIG:RelWithDebInfo>,$<CONFIG:Debug>>>:-g>
        )
        set(_extract_src "${_target_bin}")
        set(_fmt_arg "--debug-format" "dwarf")
    endif()

    cmake_path(GET AUGMENT_EXTRACT_SCRIPT PARENT_PATH _extract_script_dir)
    cmake_path(GET _extract_script_dir PARENT_PATH _extract_tools_dir)
    set(_py_env
        "${CMAKE_COMMAND}"
        -E
        env
        "PYTHONPATH=${_extract_tools_dir}")
    set(_py_run
        ${_py_env}
        "${Python3_EXECUTABLE}"
        -u
        "${AUGMENT_EXTRACT_SCRIPT}")

    set(_ast_manifest
        "${CMAKE_CURRENT_BINARY_DIR}/${AM_TARGET}_ast_manifest.json")

    if(AM_AST_MANIFEST_HINT_DIR)
        set(_committed_ast_manifest
            "${AM_AST_MANIFEST_HINT_DIR}/${AM_TARGET}_ast_manifest.json")
    endif()

    if(AM_PCH_OUT)
        set(_pch_out "${AM_PCH_OUT}")
    else()
        set(_pch_out "${CMAKE_CURRENT_BINARY_DIR}/${AM_TARGET}_pch.pch")
    endif()

    set(_phase1_cmd
        ${CMAKE_COMMAND}
        -E
        env
        "AUGMENT_JOBS=$ENV{AUGMENT_JOBS}"
        ${_py_run}
        phase1
        "--compile-commands" "${AM_COMPILE_COMMANDS}"
        "--project-root" "${AM_PROJECT_ROOT}"
        "--ast-out" "${_ast_manifest}"
        "--pch" "${_pch_out}"
    )

    if(AM_EXCLUDE_PATH)
        foreach(_frag ${AM_EXCLUDE_PATH})
            list(APPEND _phase1_cmd "--exclude-path" "${_frag}")
        endforeach()
    endif()

    if(AM_AST_MANIFEST_HINT_DIR
       AND EXISTS "${_committed_ast_manifest}"
       AND NOT AM_REGENERATE_AST)
        add_custom_command(
            OUTPUT "${_ast_manifest}"
            COMMAND ${CMAKE_COMMAND}
                -E
                copy
                "${_committed_ast_manifest}"
                "${_ast_manifest}"
            COMMENT "augment: using committed AST manifest"
            VERBATIM
        )
    else()
        add_custom_command(
            OUTPUT "${_ast_manifest}"
            COMMAND ${_phase1_cmd}
            DEPENDS "${AM_COMPILE_COMMANDS}"
            COMMENT "augment: phase1 AST walk + registry codegen for ${AM_TARGET}"
            USES_TERMINAL
            VERBATIM
        )
    endif()

    if(AM_AST_MANIFEST_HINT_DIR)
        add_custom_target("${AM_TARGET}_regenerate_ast"
            COMMAND ${_phase1_cmd}
            COMMAND ${CMAKE_COMMAND}
                -E
                copy
                "${_ast_manifest}"
                "${_committed_ast_manifest}"
            COMMENT "augment: regenerate committed AST manifest"
            USES_TERMINAL
            VERBATIM
        )
    endif()

    add_custom_target("${AM_TARGET}_augment_phase1"
        DEPENDS "${_ast_manifest}"
    )

    cmake_path(REPLACE_EXTENSION AM_OUTPUT LAST_ONLY ".json"
        OUTPUT_VARIABLE _json_out)

    set(_agmf_out "${AM_OUTPUT}")

    set(_phase2_cmd
        ${_py_run}
        phase2
        "--ast-manifest" "${_ast_manifest}"
        "--binary" "${_extract_src}"
        "--output" "${AM_OUTPUT}"
        ${_fmt_arg}
        ${_excl_args}
    )

    include("${CMAKE_CURRENT_LIST_DIR}/AugmentExclusions.cmake" OPTIONAL)
    if(COMMAND augment_get_exclusion_flags)
        augment_get_exclusion_flags(_excl_flags)
        list(APPEND _phase1_cmd ${_excl_flags})
        list(APPEND _phase2_cmd ${_excl_flags})
    endif()

    if(APPLE)
        set(_dbg "${_target_bin}.dSYM")
        add_custom_command(
            OUTPUT "${_agmf_out}" "${_json_out}"
            COMMAND dsymutil "${_target_bin}" -o "${_dbg}"
            COMMAND ${_phase2_cmd} "--binary" "${_dbg}"
            DEPENDS "${_target_bin}" "${_ast_manifest}"
            COMMENT "augment: phase2 RVA extraction + pack for ${AM_TARGET}"
            USES_TERMINAL
            VERBATIM
        )
    else()
        set(_strip_cmd "")
        if(NOT MSVC AND CMAKE_BUILD_TYPE STREQUAL "Release")
            set(_strip_cmd
                COMMAND "${CMAKE_OBJCOPY}" --strip-debug "${_target_bin}")
        endif()
        add_custom_command(
            OUTPUT "${_agmf_out}" "${_json_out}"
            COMMAND ${_phase2_cmd}
            ${_strip_cmd}
            DEPENDS "${_target_bin}" "${_ast_manifest}"
            COMMENT "augment: phase2 RVA extraction + pack for ${AM_TARGET}"
            USES_TERMINAL
            VERBATIM
        )
    endif()

    add_custom_target("${AM_TARGET}_augment_phase2" DEPENDS "${_agmf_out}")
    add_dependencies("${AM_TARGET}_augment_phase2" "${AM_TARGET}")

    if(AM_SEPARATE_TARGET)
        add_custom_target(gen_manifest_phase1)
        add_custom_target(gen_manifest_phase2)
        add_custom_target(gen_manifest)
    else()
        add_custom_target(gen_manifest_phase1 ALL)
        add_custom_target(gen_manifest_phase2 ALL)
        add_custom_target(gen_manifest ALL)
    endif()

    add_dependencies(
        gen_manifest_phase1
        "${AM_TARGET}_augment_phase1")

    add_dependencies(
        gen_manifest_phase2
        "${AM_TARGET}_augment_phase2")

    add_dependencies(
        gen_manifest
        "${AM_TARGET}_augment_phase1"
        "${AM_TARGET}_augment_phase2")

    if(COMMAND augment_generate_exclusions)

        get_target_property(
            _excl_dir
            ${AM_TARGET}
            AUGMENT_GENERATED_DIR)

        if(NOT _excl_dir)
            set(_excl_dir "${CMAKE_CURRENT_BINARY_DIR}/augment_generated")
        endif()

        augment_generate_exclusions(TARGET ${AM_TARGET})
    endif()

endfunction()
