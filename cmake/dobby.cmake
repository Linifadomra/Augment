add_subdirectory(${CMAKE_CURRENT_SOURCE_DIR}/vendor/dobby)

set(DOBBY_ALL_ARCH_FILES
    # ARM 32-bit
    "assembler-arm.cc"
    "codegen-arm.cc"
    "InstructionRelocationARM.cc"
    "trampoline_arm.cc"
    "helper_arm.cc"
    "closure_bridge_arm.cc"
    "ClosureTrampolineARM.cc"
    # ARM64 64-bit
    "InstructionRelocationARM64.cc"
    "trampoline_arm64.cc"
    "helper_arm64.cc"
    "closure_bridge_arm64.cc"
    "ClosureTrampolineARM64.cc"
    "closure_bridge_arm64.asm"
    "closure_trampoline_arm64.asm"
    # X86 32-bit
    "assembler-ia32.cc"
    "codegen-ia32.cc"
    "InstructionRelocationX86.cc"
    "trampoline_x86.cc"
    "helper_x86.cc"
    "closure_bridge_x86.cc"
    "ClosureTrampolineX86.cc"
    # X64 64-bit
    "assembler-x64.cc"
    "InstructionRelocationX64.cc"
    "trampoline_x64.cc"
    "helper_x64.cc"
    "closure_bridge_x64.cc"
    "ClosureTrampolineX64.cc"
    "closure_bridge_x64.asm"
    "closure_trampoline_x64.asm"
    # X86 Shared
    "InstructionRelocationX86Shared.cc"
    "x86_insn_decode.c"
)

set(DOBBY_KEEP_FILES "")
string(TOLOWER "${CMAKE_SYSTEM_PROCESSOR}" CMAKE_SYSTEM_PROCESSOR_LOWER)
if(CMAKE_SYSTEM_PROCESSOR_LOWER MATCHES "^arm64.*|aarch64.*")
    list(APPEND DOBBY_KEEP_FILES
        "InstructionRelocationARM64.cc"
        "trampoline_arm64.cc"
        "helper_arm64.cc"
        "closure_bridge_arm64.cc"
        "ClosureTrampolineARM64.cc"
        "closure_bridge_arm64.asm"
        "closure_trampoline_arm64.asm"
    )
elseif(CMAKE_SYSTEM_PROCESSOR_LOWER MATCHES "^arm.*")
    list(APPEND DOBBY_KEEP_FILES
        "assembler-arm.cc"
        "codegen-arm.cc"
        "InstructionRelocationARM.cc"
        "trampoline_arm.cc"
        "helper_arm.cc"
        "closure_bridge_arm.cc"
        "ClosureTrampolineARM.cc"
    )
elseif(CMAKE_SYSTEM_PROCESSOR_LOWER MATCHES "amd64.*|x86_64.*|x64.*")
    list(APPEND DOBBY_KEEP_FILES
        "assembler-x64.cc"
        "InstructionRelocationX64.cc"
        "InstructionRelocationX86Shared.cc"
        "x86_insn_decode.c"
        "trampoline_x64.cc"
        "helper_x64.cc"
        "closure_bridge_x64.cc"
        "ClosureTrampolineX64.cc"
        "closure_bridge_x64.asm"
        "closure_trampoline_x64.asm"
    )
elseif(CMAKE_SYSTEM_PROCESSOR_LOWER MATCHES "i686.*|i386.*|x86.*")
    list(APPEND DOBBY_KEEP_FILES
        "assembler-ia32.cc"
        "codegen-ia32.cc"
        "InstructionRelocationX86.cc"
        "InstructionRelocationX86Shared.cc"
        "x86_insn_decode.c"
        "trampoline_x86.cc"
        "helper_x86.cc"
        "closure_bridge_x86.cc"
        "ClosureTrampolineX86.cc"
    )
endif()

set(DOBBY_REMOVE_FILES "")
foreach(f ${DOBBY_ALL_ARCH_FILES})
    set(keep OFF)
    foreach(k ${DOBBY_KEEP_FILES})
        if(f STREQUAL k)
            set(keep ON)
            break()
        endif()
    endforeach()
    if(NOT keep)
        list(APPEND DOBBY_REMOVE_FILES "${f}")
    endif()
endforeach()

target_include_directories(dobby_static PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/vendor/dobby/include
)

foreach(target dobby dobby_static DobbyX macho_ctx_kit shared_cache_ctx_kit dobby_symbol_resolver)
    if(TARGET ${target})
        # Filter sources
        get_target_property(target_sources ${target} SOURCES)
        if(target_sources)
            set(filtered_sources "")
            foreach(src ${target_sources})
                set(remove OFF)
                foreach(rem ${DOBBY_REMOVE_FILES})
                    # Match filename at the end of the path
                    if(src MATCHES "(/|^)${rem}$")
                        set(remove ON)
                        break()
                    endif()
                endforeach()
                if(NOT remove)
                    list(APPEND filtered_sources "${src}")
                endif()
            endforeach()
            set_target_properties(${target} PROPERTIES SOURCES "${filtered_sources}")
        endif()

        # Silence macro redefinition warning (assert)
        if(CMAKE_CXX_COMPILER_ID MATCHES "Clang|AppleClang")
            target_compile_options(${target} PRIVATE -Wno-macro-redefined)
        endif()
    endif()
endforeach()