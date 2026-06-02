# Augment

Mixin-based modding framework written in C++ without sacrificing performance or stability. 

The core philosophy: hook in any function at runtime with before/after/replace semantics, with no hooks to maintain in the codebase, no annotations, and little runtime overhead.

## Dependencies

- Polyhook2 (vendored)
- LibClang
- Lua (Optional, see [the building guide](#building))
- Python 3.8+

## Architecture

Overview:

```
Mixin.Before("Foo::bar",fn)
↓
MixinRegistry     ← one chain per hooked symbol, created lazily
↓
ctx struct        ← contract between C++ and hook: args, self, return value
↓
Trampoline        ← NOP sled patched on first mixin() call
↓
Original function ← vanilla C++, zero framework knowledge
```

Library structure (built [here](https://tree.nathanfriend.com/?s=(%27opEs!(%27fancy!true~fullPath!false~trailJgSlash!true~rootDot!false)~R(%27R%27A74tKtX9tKtOuitK4FX3F%20modulK%20%7Be.g.Z7_codegV%7D4docsQBUILDING.md4JcludeQa7Q*a7.hpp9public-facJg%20API4srcQruntime5*3registry6TrjterfaceQplatform59backVdZbstracE%20%7BH2%20wirJg%2COym%20T%7DQctx5Wtext%20primitivK4toolsX3libclang%20walYr6ctx_gV%2C%20hooYdjto%20F4vVdor%2FQH_2_0%2F4CMaYLists.txtWfiguraE6JstallaEOcript%27)~version!%271%27)*%209%E2%86%90%204%5Cn*5%2F86%20%2B%207ugmVt8***9%203EtionFcmaYHpolyhookJinKesO%20sQ4*Rsource!TrKolveVenW83conX58*YkeZ%20aj%20J%01jZYXWVTRQOKJHFE9876543*)):

```
Augment/
├── test/               ← test suites
├── cmake/              ← cmake modules (e.g. augment_codegen)
├── docs/
│   └── BUILDING.md
├── include/
│   └── augment/
│       └── augment.hpp ← public-facing API
├── src/
│   ├── runtime/        ← registry + resolver interface
│   ├── platform/       ← backend abstraction (polyhook2 wiring, sym resolve)
│   └── ctx/            ← context primitives
├── tools/              ← libclang walker + ctx_gen, hooked into cmake
├── vendor/
│   └── polyhook_2_0/
└── CMakeLists.txt      ← configuration + installation script
```

## Symbol resolution

- **Build-time** (libclang, analysis-only. Projects build with any compiler): C++ source → stable mangled symbol names → address offsets → symbol map artifact.
- **Runtime**: base_address + offset → function pointer. Works stripped, works in release, works on every platform.

## Building

In-depth building instructions can be found in the [building guide](docs/BUILDING.md)