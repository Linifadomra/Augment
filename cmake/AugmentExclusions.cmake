# cmake/AugmentExclusions.cmake
# ---------------------------------------------------------------------------
# Central exclusion registry.
#
# Both lists are written to cache so walk.py and extract.py can consume them
# via augment_get_exclusion_flags().
#
# ---------------------------------------------------------------------------

if(NOT DEFINED AUGMENT_EXCLUSIONS_SCRIPT)
    set(AUGMENT_EXCLUSIONS_SCRIPT
        "${CMAKE_CURRENT_SOURCE_DIR}/tools/exclusions/gen_exclusions.py"
        CACHE FILEPATH "Path to gen_exclusions.py")
endif()

# -- Built-in prefix exclusions --
set(_AUGMENT_BUILTIN_PREFIX_EXCLUSIONS
    "__cxa_"                # Itanium ABI: exception handling, guard vars
    "__gxx_"                # GCC C++ runtime
    "_Unwind_"              # Infinite recursion if hooked
    "__libc_"               # glibc internals
    "__sanitizer_"          # Breaks if intercepted
    "__asan_"
    "__tsan_"
    "__msan_"
    "__ubsan_"
    "__acrt_"               # MSVC CRT
    "__vcrt_"
    "_CRT_"
    "_dl_"                  # Dynamic linker
    "__dl_"
    "augment_"              # Never hook ourselves
    "Augment_"
    "_augment_"
    "std::"                 # standard lib
    "boost::"               # boost lib
    "__gnu_cxx::"           # gnu specific
    [[$_]]                  # compiler-generated
    "zz::"                  # dobby
    "AssemblerCodeBuilder"  # dobby
    "ClearCache"            # dobby
    "ClosureTrampoline"     # dobby
    "CodeGenBase"           # dobby
    "CodeMemBuffer"         # dobby
)

# -- Built-in substring exclusions --
set(_AUGMENT_BUILTIN_SUBSTR_EXCLUSIONS
    "operator new"      # Heap corruption if hooked
    "operator delete"
    "__malloc"
    "__free"
    "__realloc"
    "pthread_mutex"     # Deadlock risk
    "pthread_rwlock"
    "pthread_cond"
    "sigaction"         # Re-entrant hooking is UB
    "signal("
    "objc_msgSend"      # ObjC/Swift runtime (macOS)
    "swift_"
)

# Merge built-ins with caller-supplied lists into the two canonical names.
# These are set in PARENT_SCOPE by convention; modules that include this file
# get them as normal variables.
set(AUGMENT_SUBSTR_EXCLUSIONS
    ${_AUGMENT_BUILTIN_SUBSTR_EXCLUSIONS}
    ${AUGMENT_SUBSTR_EXCLUSIONS}
)
list(REMOVE_DUPLICATES AUGMENT_SUBSTR_EXCLUSIONS)
set(AUGMENT_SUBSTR_EXCLUSIONS ${AUGMENT_SUBSTR_EXCLUSIONS}
    CACHE STRING "Merged substring exclusion list" FORCE)

set(AUGMENT_PREFIX_EXCLUSIONS
    ${_AUGMENT_BUILTIN_PREFIX_EXCLUSIONS}
    ${AUGMENT_PREFIX_EXCLUSIONS}
)
list(REMOVE_DUPLICATES AUGMENT_PREFIX_EXCLUSIONS)
set(AUGMENT_PREFIX_EXCLUSIONS ${AUGMENT_PREFIX_EXCLUSIONS}
    CACHE STRING "Merged prefix exclusion list" FORCE)

function(augment_get_exclusion_flags out_var)
    set(_flags "")
    foreach(_p ${AUGMENT_PREFIX_EXCLUSIONS})
        list(APPEND _flags "--exclude-prefix" "${_p}")
    endforeach()
    foreach(_s ${AUGMENT_SUBSTR_EXCLUSIONS})
        list(APPEND _flags "--exclude-substr" "${_s}")
    endforeach()
    set(${out_var} "${_flags}" PARENT_SCOPE)
endfunction()

function(augment_generate_exclusions)
    cmake_parse_arguments(AGE "" "TARGET" "" ${ARGN})

    find_package(Python3 REQUIRED COMPONENTS Interpreter)

    if(NOT AGE_TARGET)
        message(FATAL_ERROR "[augment_generate_exclusions] TARGET is required")
    endif()

    set(_out_dir  "${CMAKE_CURRENT_BINARY_DIR}/augment_generated")
    set(_out_header "${_out_dir}/augment_exclusions.hpp")

    set(_prefix_file "${CMAKE_CURRENT_BINARY_DIR}/_augment_prefix_excl.txt")
    set(_substr_file "${CMAKE_CURRENT_BINARY_DIR}/_augment_substr_excl.txt")

    list(JOIN AUGMENT_PREFIX_EXCLUSIONS "\n" _prefix_content)
    list(JOIN AUGMENT_SUBSTR_EXCLUSIONS "\n" _substr_content)
    file(WRITE "${_prefix_file}" "${_prefix_content}\n")
    file(WRITE "${_substr_file}" "${_substr_content}\n")

    add_custom_command(
        OUTPUT  "${_out_header}"
        COMMAND "${Python3_EXECUTABLE}"
                "${AUGMENT_EXCLUSIONS_SCRIPT}"
                "--prefix-file" "${_prefix_file}"
                "--substr-file" "${_substr_file}"
                "--output"      "${_out_header}"
        DEPENDS "${AUGMENT_EXCLUSIONS_SCRIPT}"
                "${_prefix_file}"
                "${_substr_file}"
        COMMENT "[Augment] Generating augment_exclusions.hpp..."
        VERBATIM
    )

    if(NOT TARGET ${AGE_TARGET}_augment_exclusions)
        add_custom_target(${AGE_TARGET}_augment_exclusions
            DEPENDS "${_out_header}"
        )
    endif()

    add_dependencies(${AGE_TARGET} ${AGE_TARGET}_augment_exclusions)
    target_include_directories(${AGE_TARGET} PRIVATE "${_out_dir}")

    set_target_properties(${AGE_TARGET} PROPERTIES
        AUGMENT_EXCLUSIONS_HEADER "${_out_header}"
    )
endfunction()
