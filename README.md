# Augment

Mixin-based patching framework written in C++ without sacrificing performance or stability. 
These patches are called "augments" ;).

The core philosophy: hook in any function at runtime with before/after/replace semantics, with no hooks to maintain in the codebase, no annotations, and little runtime overhead.

## Dependencies

- Dobby
- LibClang
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

**Foreign language consumers** get an additional layer beneath the registry. Instead of providing a native function pointer directly, they use the FFI path:
```
augment_make_closure("Foo::bar")
↓
libffi trampoline  ← synthesized at runtime, ABI-correct for the symbol's signature
↓
closure_handler    ← bridges into augment_before / augment_after with a normalized ctx
↓
MixinRegistry      ← same chain as above, symbol lookup by name
```
The signature for the closure is loaded from a `symbols.json` artifact generated at build time by the tools pipeline. Field offsets for struct access come from the same pipeline via. DWARF extraction. This behavior is entirely optional and disabled by default for consumers who only require C++. If you require this behavior, see [our building instructions](#building). A full usage example can be found in our game agnostic C++ modloader library, [Petrichor](https://github.com/Linifadomra/Augment/tree/main/tools). In-depth documentation will come at a later date.

## Library Structure

Library structure (built [here](https://tree.nathanfriend.com/?s=(%27optiQs!(%27fancy!true~fullPath!false~trailHgSlash!true~rootDot!false)~F(%27F%27A42tests6testRuites2969%20modules%20%7Be.g.T4_codegenVdocsWBUILDING.md2HcludeWa42Ka4.hppEpublic-facHg%20API2srcWruntime3*0registry%20%2B7r8terfaceWplatform3EbacJndTbstracO%7BDobby%20wirHg%2CRym7Vtools6Pyth5libclang%20walJr%20hooJd8to%2092CMaJLists.txtK*0cQfiguraO%2B8stallaOscript%27)~versiQ!%271%27)*%20E%E2%86%90%202%5Cn*3%2FK*4ugment5Q%2063KK07%20resolve8%20H9cmaJE%200Fsource!HinJkeK**Oti5QonR%20sT%20aV%7D2W2*%01WVTRQOKJHFE987654320*)):

```
Augment/
├── tests/              ← test suites
├── cmake/              ← cmake modules (e.g. augment_codegen)
├── docs/
│   └── BUILDING.md
├── include/
│   └── augment/
│       └── augment.hpp ← public-facing API
├── src/
│   ├── runtime/        ← registry + resolver interface
│   └── platform/       ← backend abstraction (Dobby wiring, sym resolve)
├── tools/              ← Python libclang walker hooked into cmake
└── CMakeLists.txt      ← configuration + installation script
```
## Symbol resolution

- **Build-time** (libclang, analysis-only.): C++ source → Python `walk.py` → stable mangled symbol names → address offsets → symbol map artifact.
- **Runtime**: base_address + offset → function pointer. Works stripped, works in release, works on every platform.

## Building

In-depth building instructions can be found in the [building guide](docs/BUILDING.md)