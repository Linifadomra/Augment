add_executable(game_example 
    ${CMAKE_CURRENT_SOURCE_DIR}/augment/main.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/vanilla/game.cpp
)
target_link_libraries(game_example PRIVATE augment::augment)
target_include_directories(game_example PRIVATE 
    ${CMAKE_CURRENT_SOURCE_DIR}/../include
    ${CMAKE_CURRENT_BINARY_DIR}
    ${CMAKE_CURRENT_SOURCE_DIR}
)

augment_codegen_target(
    TARGET      game_example
    HEADERS     ${CMAKE_CURRENT_SOURCE_DIR}/vanilla/game.hpp
)

augment_manifest(
    TARGET game_example
    OUTPUT ${CMAKE_BINARY_DIR}/augment.bin
    COMPILE_COMMANDS ${CMAKE_BINARY_DIR}/compile_commands.json
    SEPARATE_TARGET
)
