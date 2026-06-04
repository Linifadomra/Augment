# cmake/AugmentManifest.cmake
# ---------------------------------------------------------------------------
# augment_manifest(
#     TARGET  <name>     # CMake target to attach to (required)
#     OUTPUT  <path>     # Where to write the signature manifest (required)
# )
#
# Derives a per-function signature manifest (return type, member-ness, FFI arg
# kinds) from TARGET's DWARF for the libffi closure engine, and adds the
# debug-info flag the toolchain needs so it can be generated:
#
#   APPLE   -g            dsymutil -> dwarf_manifest.py(<bin>.dSYM)
#   Linux   -gsplit-dwarf dwarf_manifest.py(<bin>)
#   MSVC    /Zi           PDB-based generator not implemented yet
# ---------------------------------------------------------------------------

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
        message(WARNING
            "augment_manifest: no PDB manifest generator yet; "
            "${AM_OUTPUT} will not be produced on this toolchain")
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
        target_compile_options(${AM_TARGET} PRIVATE $<$<CONFIG:Release>:-gsplit-dwarf>)
        add_custom_command(TARGET ${AM_TARGET} POST_BUILD
            COMMAND ${Python3_EXECUTABLE} ${AUGMENT_MANIFEST_SCRIPT}
                    $<TARGET_FILE:${AM_TARGET}> ${AM_OUTPUT}
            VERBATIM)
    endif()
endfunction()
