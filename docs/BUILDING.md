# Building Augment

## Requirements

- CMake 3.25 or newer
- A C++17-capable compiler (MSVC, Clang, GCC)
- [Polyhook2](https://github.com/stevemk14ebr/PolyHook_2_0)
- [libclang](https://clang.llvm.org/docs/Tooling.html) (for codegen, see [Codegen](#codegen))
- Python 3.8 or newer (for the codegen walker)
- Lua 5.4 (optional, see [Lua Bindings](#lua-bindings))

---

## Cloning

```bash
git clone https://github.com/yourorg/augment.git
cd augment
git submodule update --init --recursive
```

---

## Configuring

```bash
cmake -B build -DCMAKE_BUILD_TYPE=Release
```

### CMake Options

| Option | Default | Description |
|---|---|---|
| `AUGMENT_CODEGEN` | `ON` | Build the codegen tool (requires libclang + Python) |
| `AUGMENT_LUA` | `OFF` | Enable Lua scripting bindings |
| `AUGMENT_TESTS` | `OFF` | Build the test suite |
| `AUGMENT_INSTALL` | `ON` | Enable install targets |

---

## Building

```bash
cmake --build build --config Release
```

---

## Codegen

Augment's codegen walker uses libclang to analyze your project's C++ source and emit:
- A symbol map artifact (mangled name → address offset)
- Typed `ctx` structs for every hooked symbol

### Requirements

libclang must be discoverable by CMake. On most systems:

**Linux / macOS**
```bash
# Ubuntu / Debian
sudo apt install libclang-dev

# macOS via Homebrew
brew install llvm
export LIBCLANG_PATH=$(brew --prefix llvm)/lib
```

**Windows**

Install LLVM from the [official releases](https://github.com/llvm/llvm-project/releases) and add it to your PATH. CMake will find it via `find_package(Clang)`.

### Running the walker

The walker is invoked automatically as a CMake custom command during your project's configure step when `AUGMENT_CODEGEN=ON`. It reads your compile commands and emits generated files into `build/augment_gen/`.

To run it manually:

```bash
python3 tools/codegen/walker.py \
  --compile-commands build/compile_commands.json \
  --output build/augment_gen
```

Generated files should be committed if your project does not run codegen at configure time. See [Consuming Augment](#consuming-augment) for details.

---

## Lua Bindings

Enable with `-DAUGMENT_LUA=ON`. Requires Lua 5.4 headers and libraries to be discoverable by CMake.

```bash
# Ubuntu / Debian
sudo apt install liblua5.4-dev

# macOS via Homebrew
brew install lua
```

```bash
cmake -B build -DAUGMENT_LUA=ON
```

---

## Consuming Augment

### As a subdirectory

```cmake
add_subdirectory(augment)
target_link_libraries(your_project PRIVATE augment::augment)
```

### Via CMake FetchContent

```cmake
include(FetchContent)
FetchContent_Declare(
    augment
    GIT_REPOSITORY https://github.com/yourorg/augment.git
    GIT_TAG        main
)
FetchContent_MakeAvailable(augment)
target_link_libraries(your_project PRIVATE augment::augment)
```

When consuming Augment, wire the codegen step to your project's source tree:

```cmake
augment_codegen(
    TARGET       your_project
    SOURCES      ${YOUR_PROJECT_SOURCES}
    OUTPUT_DIR   ${CMAKE_BINARY_DIR}/augment_gen
)
```

This emits ctx structs and the symbol map for your specific codebase. The output directory should be added to your include path.

---

## Tests

```bash
cmake -B build -DAUGMENT_TESTS=ON
cmake --build build
ctest --test-dir build --output-on-failure
```

---

## Platform Notes

| Platform | Compiler | Hook Backend | Status |
|---|---|---|---|
| Windows x64 | MSVC / Clang-cl | Polyhook2 | Supported |
| Linux x64 | GCC / Clang | Polyhook2 | Supported |
| macOS x64 / ARM64 | Apple Clang | Polyhook2 | Supported |