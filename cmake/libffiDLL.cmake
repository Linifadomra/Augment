function(augment_copy_ffi_dll target)
    if (NOT WIN32 OR NOT AUGMENT_FFI)
        return()
    endif ()

    add_custom_command(TARGET ${target} POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "${CMAKE_CURRENT_SOURCE_DIR}/external/libffi-prebuilt/libffi-8.dll"
            "$<TARGET_FILE_DIR:${target}>"
        VERBATIM
    )
endfunction()