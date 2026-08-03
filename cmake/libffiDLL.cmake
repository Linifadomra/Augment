function(augment_copy_ffi_dll target)
    if (NOT WIN32 OR NOT AUGMENT_FFI)
        return()
    endif ()

    add_custom_command(TARGET ${target} POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "${FFI_DLL}" "$<TARGET_FILE_DIR:${target}>"
        VERBATIM
    )
endfunction()