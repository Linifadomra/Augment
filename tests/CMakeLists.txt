if(MSVC)
    set(CMAKE_MSVC_DEBUG_INFORMATION_FORMAT "ProgramDatabase")
    add_compile_options($<$<CONFIG:Release>:/Zi>)
    add_link_options($<$<CONFIG:Release>:/DEBUG>)
endif()

add_executable(test_chain test_chain.cpp)
target_link_libraries(test_chain PRIVATE augment)
target_include_directories(test_chain PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/../src)
add_test(NAME chain COMMAND test_chain)

add_executable(test_conflicts test_conflicts.cpp)
target_link_libraries(test_conflicts PRIVATE augment)
target_include_directories(test_conflicts PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/../src)
add_test(NAME conflict COMMAND test_conflicts)

add_executable(test_registry test_registry.cpp platform_stub.cpp)
target_link_libraries(test_registry PRIVATE augment)
target_include_directories(test_registry PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/../src)
add_test(NAME registry COMMAND test_registry)

add_executable(platform_selftest platform_selftest.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../src/platform/sym_resolve.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../src/platform/hook_backend.cpp)
target_link_libraries(platform_selftest PRIVATE dobby)
target_include_directories(platform_selftest PRIVATE 
${CMAKE_CURRENT_SOURCE_DIR}/../src
${CMAKE_CURRENT_SOURCE_DIR}/../include
)
add_test(NAME platform COMMAND platform_selftest)

add_executable(mixin_selftest mixin_selftest.cpp)
target_link_libraries(mixin_selftest PRIVATE augment::augment dobby)
add_test(NAME mixin COMMAND mixin_selftest)

if(AUGMENT_FFI)
    add_executable(closure_selftest closure_selftest.cpp)
    target_link_libraries(closure_selftest PRIVATE augment::augment dobby ffi)
    add_test(NAME closure COMMAND closure_selftest)
endif()

add_executable(test_all
    ${CMAKE_CURRENT_SOURCE_DIR}/test_all.cpp
)
target_link_libraries(test_all PRIVATE augment::augment)
target_include_directories(test_all PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/../src
    ${CMAKE_CURRENT_SOURCE_DIR}
)
augment_codegen_target(
    TARGET  test_all
    HEADERS ${CMAKE_CURRENT_SOURCE_DIR}/test_all.hpp
    INCLUDE_ROOT ${CMAKE_CURRENT_SOURCE_DIR}
)
add_test(NAME all COMMAND test_all)

add_executable(manifest_read_test manifest_read_test.cpp)
target_link_libraries(manifest_read_test PRIVATE augment::augment)
target_include_directories(manifest_read_test PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/../src)
add_test(NAME manifest_read COMMAND manifest_read_test WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR})

add_executable(introspect_test introspect_test.cpp)
target_link_libraries(introspect_test PRIVATE augment::augment)
add_test(NAME introspect COMMAND introspect_test WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR})

add_executable(mem_test mem_test.cpp)
target_link_libraries(mem_test PRIVATE augment::augment)
add_test(NAME mem COMMAND mem_test)
if(AUGMENT_FFI)
    add_executable(abi_selftest abi_selftest.cpp)
    target_link_libraries(abi_selftest PRIVATE augment::augment dobby ffi)
    add_test(NAME abi COMMAND abi_selftest)
endif()
