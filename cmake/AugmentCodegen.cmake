# cmake/AugmentCodegen.cmake
# ---------------------------------------------------------------------------
# augment_codegen_target(
#     TARGET          <name>        # CMake target to attach to (required)
#     HEADERS         h1.hpp h2.hpp # Headers to walk (required)
#     OUTPUT_DIR      <path>        # Where to write generated files
#                                   # (default: ${CMAKE_CURRENT_BINARY_DIR}/augment_generated)
#     SYMBOL_PREFIX   <prefix>      # Only emit symbols starting with this (optional)
#     CLANG_ARGS      <args>        # Extra flags forwarded to libclang (optional)
#     JSON_ONLY                     # Emit only symbols.json, skip hpp/cpp (optional flag)
# )
#
# Creates a custom target  <name>_codegen  that:
#   1. Runs walk.py over the listed headers
#   2. Emits augment_ctx.hpp, augment_trampolines.cpp, symbols.json
#      into OUTPUT_DIR
#   3. Adds OUTPUT_DIR to TARGET's include path
#   4. Adds augment_trampolines.cpp to TARGET's sources (unless JSON_ONLY)
#
# The codegen target is added as a dependency of TARGET so it always runs
# before compilation.
#
# Requirements:
#   - Python3 in PATH
#   - pip install libclang   (checked at configure time with a warning)
#   - walk.py must be in ${CMAKE_CURRENT_SOURCE_DIR}/tools/
#     or set AUGMENT_WALKER_SCRIPT before including this file.
# ---------------------------------------------------------------------------

cmake_minimum_required(VERSION 3.20)

# Locate the walker script once at include time.
if(NOT DEFINED AUGMENT_WALKER_SCRIPT)
    set(AUGMENT_WALKER_SCRIPT
        "${CMAKE_CURRENT_SOURCE_DIR}/tools/walker/walk.py"
        CACHE FILEPATH "Path to walk.py")
endif()

# Check Python3 is available.
find_package(Python3 REQUIRED COMPONENTS Interpreter)

# Warn if libclang bindings are missing (non-fatal so configure still succeeds;
# the build will fail at codegen time with a clear error from the script itself).
execute_process(
    COMMAND "${Python3_EXECUTABLE}" -c "import clang.cindex"
    RESULT_VARIABLE _augment_clang_check
    OUTPUT_QUIET ERROR_QUIET
)
if(NOT _augment_clang_check EQUAL 0)
    message(WARNING
        "[Augment] libclang Python bindings not found.\n"
        "Install with:  pip install libclang\n"
        "Codegen targets will fail until this is resolved.")
endif()

# ---------------------------------------------------------------------------
# augment_codegen_target()
# ---------------------------------------------------------------------------
function(augment_codegen_target)
    cmake_parse_arguments(
        ACG                         # prefix
        "JSON_ONLY"                 # options (flags)
        "TARGET;OUTPUT_DIR;SYMBOL_PREFIX"   # one-value keywords
        "HEADERS;CLANG_ARGS"        # multi-value keywords
        ${ARGN}
    )

    # -- Validate required args --
    if(NOT ACG_TARGET)
        message(FATAL_ERROR "[augment_codegen_target] TARGET is required")
    endif()
    if(NOT ACG_HEADERS)
        message(FATAL_ERROR "[augment_codegen_target] HEADERS is required")
    endif()

    # -- Defaults --
    if(NOT ACG_OUTPUT_DIR)
        set(ACG_OUTPUT_DIR
            "${CMAKE_CURRENT_BINARY_DIR}/augment_generated")
    endif()

    set(_codegen_target "${ACG_TARGET}_codegen")

    # -- Build walker command-line --
    set(_walker_cmd
        "${Python3_EXECUTABLE}"
        "${AUGMENT_WALKER_SCRIPT}"
        "--output-dir" "${ACG_OUTPUT_DIR}"
    )

    if(ACG_SYMBOL_PREFIX)
        list(APPEND _walker_cmd "--symbol-prefix" "${ACG_SYMBOL_PREFIX}")
    endif()

    if(ACG_CLANG_ARGS)
        # Join into a single quoted string as the script splits on spaces
        list(JOIN ACG_CLANG_ARGS " " _clang_args_joined)
        list(APPEND _walker_cmd "--clang-args" "${_clang_args_joined}")
    endif()

    if(ACG_JSON_ONLY)
        list(APPEND _walker_cmd "--json-only")
    endif()

    # Append headers last (positional)
    foreach(_hdr ${ACG_HEADERS})
        list(APPEND _walker_cmd "${_hdr}")
    endforeach()

    # -- Declare outputs --
    set(_out_manifest   "${ACG_OUTPUT_DIR}/symbols.json")
    set(_out_ctx        "${ACG_OUTPUT_DIR}/augment_ctx.hpp")
    set(_out_trampoline "${ACG_OUTPUT_DIR}/augment_trampolines.cpp")

    if(ACG_JSON_ONLY)
        set(_outputs "${_out_manifest}")
    else()
        set(_outputs "${_out_manifest}" "${_out_ctx}" "${_out_trampoline}")
    endif()

    # -- Custom command that actually runs the walker --
    add_custom_command(
        OUTPUT          ${_outputs}
        COMMAND         ${_walker_cmd}
        DEPENDS         ${ACG_HEADERS} "${AUGMENT_WALKER_SCRIPT}"
        COMMENT         "[Augment] Running codegen for ${ACG_TARGET}..."
        VERBATIM
    )

    # -- Custom target so you can run it explicitly:
    #    cmake --build . --target <name>_codegen --
    add_custom_target(${_codegen_target}
        DEPENDS ${_outputs}
    )

    # -- Wire into the main target --
    add_dependencies(${ACG_TARGET} ${_codegen_target})

    # Add generated include dir to the target
    target_include_directories(${ACG_TARGET}
        PRIVATE "${ACG_OUTPUT_DIR}"
    )

    # Add the trampoline source unless JSON_ONLY
    if(NOT ACG_JSON_ONLY)
        target_sources(${ACG_TARGET}
            PRIVATE "${_out_trampoline}"
        )
    endif()

    # Surface the output paths as target properties for downstream consumers
    set_target_properties(${ACG_TARGET} PROPERTIES
        AUGMENT_GENERATED_DIR       "${ACG_OUTPUT_DIR}"
        AUGMENT_MANIFEST_JSON       "${_out_manifest}"
    )

    message(STATUS
        "[Augment] Codegen registered for target '${ACG_TARGET}'\n"
        "          headers:    ${ACG_HEADERS}\n"
        "          output dir: ${ACG_OUTPUT_DIR}")
endfunction()