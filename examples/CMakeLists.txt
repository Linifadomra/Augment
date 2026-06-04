add_executable(game_example 
    ${CMAKE_CURRENT_SOURCE_DIR}/augment/main.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/vanilla/game.cpp
)
target_link_libraries(game_example PRIVATE augment::augment)
target_include_directories(game_example PRIVATE 
    ${CMAKE_CURRENT_SOURCE_DIR}/../include
    ${CMAKE_CURRENT_SOURCE_DIR}
)

augment_codegen_target(
    TARGET      game_example
    HEADERS     ${CMAKE_CURRENT_SOURCE_DIR}/vanilla/game.hpp
)