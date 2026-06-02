# Augment

Mixin-based modding framework written in C++ without sacrificing performance or stability. 

The core philosophy: hook in any function at runtime with before/after/replace semantics, with no hooks to maintain in the codebase, no annotations, and little runtime overhead.

## Dependencies

- Polyhook2
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

Library structure (built [here](https://tree.nathanfriend.com/?s=(%27op9s!(%27fancy!true~fullPath!false~trailFgSlash!true~rootDot!false)~K(%27K%27A63tHtV8tHtJuitH3EV0E%20modulH%20%7Be.g.W6_codegen%7D3docsOBUILDING.md3FcludeOa6O*a6.hpp8public-facFg%20API3srcOruntime4*0registry5QrXterfaceOplatform48bacRndWbstrac9%20%7Bpolyhook2%20wirFg%2CJym%20Q%7DOctx4Ttext%20primitivH3toolsV0libclang%20walRr5ctx_gen%2C%20hooRdXto%20E3CMaRLists.txtTfigura95Fstalla9Jcript%27)~version!%271%27)*%208%E2%86%90%203%5Cn*4%2F75%20%2B%206ugment7***8%2009tionEcmaRFinHesJ%20sKsource!O3*QrHolveRkeT70conV47*W%20aX%20F%01XWVTRQOKJHFE98765430*)):

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
└── CMakeLists.txt      ← configuration + installation script
```

## Symbol resolution

- **Build-time** (libclang, analysis-only. Projects build with any compiler): C++ source → stable mangled symbol names → address offsets → symbol map artifact.
- **Runtime**: base_address + offset → function pointer. Works stripped, works in release, works on every platform.

## Building

In-depth building instructions can be found in the [building guide](docs/BUILDING.md)