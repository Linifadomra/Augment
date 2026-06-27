<div align="center"> <img src="assets/svg/Augment_purple_gradient.svg" alt="Logo" width="400"/> </div>

# Augment

Mixin-based patching framework written in C++ without sacrificing performance or stability. 
These patches are called "augments" ;).

The core philosophy: hook in any function at runtime with before/after/replace semantics, with no hooks to maintain in the codebase, no annotations, and little runtime overhead.

## Dependencies

- Dobby
- LibClang
- Python 3.8+

## Architecture

```
augment_register("Foo::bar", BEFORE, fn)
↓
Registry          ← one chain per hooked symbol, created lazily
↓
AugmentCtx        ← contract between C++ and hook: args, self, return value
↓
Trampoline        ← patched on first augment() call via Dobby
↓
Original function ← vanilla C++, zero framework knowledge
```

**Foreign language consumers (Lua, Python, etc.)** can use an additional FFI path beneath the registry:
```
augment_make_closure("Foo::bar")
↓
libffi trampoline  ← synthesized at runtime, ABI-correct for the symbol's signature
↓
closure_handler    ← bridges into augment_before / augment_after with a normalized ctx
↓
MixinRegistry      ← same chain as above, symbol lookup by name
```

## Symbol Resolution

Augment supports two first-class resolution paths depending on your build setup:

### Manifest Path
> [!NOTE] 
> Best suited for shipping titles where full build artifacts are available.

* C++ source + DWARF → build-time pipeline → binary manifest artifact
* Loaded at runtime via augment_manifest_load(path)
* Provides full type info, field offsets, RVA lookup, and ASLR slide compensation
* Can resolve non-exported internal symbols
* resolve_target uses manifest RVA + image_slide() as primary, falls back to plat::sym_resolve

### LibClang Walker Path
> [!NOTE] 
> Best suited for mod tooling or environments without a full manifest.

* walk.py analyzes C++ source at build time via LibClang
* Emits `symbols.json` artifact containing stable mangled symbol names and address offsets
* Emits generated ctx_ objects and trampolines
* Runtime resolution via plat::sym_resolve against exported symbols
* augment_resolve is the primary API here
* More limited than the manifest path but requires no binary artifact at runtime

The two paths can be used together or independently. Manifest covers internal symbols, plat::sym_resolve covers exported symbols not in the manifest. resolve_target handles the fallback automatically if both are present. Most projects will only need one path.

## Conflict System
Augment includes a contract-based conflict resolution system for augment ordering and exclusivity:

- **Order**: two augments write or read/write the same domain at differing priorities. Execution order becomes priority-dependent, logged as a warning
- **Hard**: two augments are structurally incompatible. Two `replace` hooks on the same symbol, or two hooks writing the same domain at equal priority with no resolution. Second registration is rejected outright.

Conflicts are declared via the `contract` field of `AugmentRegOpts`, passed to `augment_register` at registration time.

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

## Exclusions

Exclusions are first-class citizens in Augment. Due to the nature of arbitrary symbol hooking and resolution, different vulnerabilities that would otherwise be implausible may surface. Therefore, exclusions are central and simple. Just add to your CMake:

```cmake
# Matches by prefix against the qualified symbol name
set(AUGMENT_PREFIX_EXCLUSIONS
    "Foo"
)

# Matches by substring against the qualified symbol name
set(AUGMENT_SUBSTRING_EXCLUSIONS
    "Bar"
)
```

Exclusions are applied at every layer: symbols are filtered during the AST walk, stripped from the manifest, and blocked at runtime resolution. Built-in exclusions covering the C++ runtime, allocators, thread primitives, and Augment's own internals are always active regardless of what you specify here.

## Usage

A full usage example including Luau scripting support, the Petrichor.Mod lifecycle, and the foreign language consumer path can be found in [Petrichor](https://github.com/Linifadomra/Petrichor), our game-agnostic C++ modloader library built on Augment.

## Building

In-depth building instructions can be found in the [building guide](docs/BUILDING.md)