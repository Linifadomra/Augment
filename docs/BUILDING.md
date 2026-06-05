# Building Augment

## Requirements

- CMake 3.17 or newer
- A C++17-capable compiler (MSVC, Clang, GCC)
- [Dobby (vendored)](https://github.com/jmpews/Dobby)
- Python 3.8 or newer (for the codegen walker, aswell as `libclang` Python package)

---

## Cloning

> [!IMPORTANT]
> You **MUST** clone submodules recursively, or you will be unable to [configure!](#configuring)

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
| `AUGMENT_TESTS` | `OFF` | Build the test suite |
| `AUGMENT_INSTALL` | `OFF` | Enable install targets |
| `AUGMENT_BUILD_EXAMPLES` | `OFF` | Build Augment examples |
| `BUILD_SHARED_LIBS` | `OFF` | Build Augment as a shared lib (propagates to Dobby) |
| `AUGMENT_FFI` | `OFF` | Build FFI bindings for Augment |

---

## Building

```bash
cmake --build build --config Release
```

---

## Codegen

Augment's codegen walker uses libclang and Python to analyze your project's C++ source and emit:
- A symbol map artifact (mangled name → address offset)
- Typed `ctx` structs for every hooked symbol

### Running the walker

The walker runs as a CMake custom command at build time when headers change. 
It takes explicit header paths. To run it manually:

```bash
python3 tools/walker/walk.py \
    --output-dir build/augment_generated \
    path/to/your/header.hpp
```

Generated files should be committed if your project does not run codegen at configure time. See [Consuming Augment](#consuming-augment) for details.

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
| Windows x64 | MSVC / Clang-cl | Dobby | Supported |
| Linux x64 | GCC / Clang | Dobby | Supported |
| macOS x64 / ARM64 | Apple Clang | Dobby | Supported |