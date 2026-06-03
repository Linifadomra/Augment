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
target_include_directories(platform_selftest PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/../src)
add_test(NAME platform COMMAND platform_selftest)
