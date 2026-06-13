"""
STUBBED FOR NOW

extractor/codegen/registry.py

Generates augment_generated_registry.cpp from an AST manifest.

For every class that appears as a self_view in the manifest, emits a
constructor hook that registers the live instance and a destructor hook
that unregisters it. This is called at the end of phase 1 so the
generated file is compiled into the mod runtime as part of the normal
build. This means there's zero manual work per class, always in sync with the manifest.

Constructor-mangling notes
===
The Itanium ABI emits up to three variants per constructor:
  C1  complete-object constructor
  C2  base-object constructor
  C3  allocating constructor (rare, Itanium extension)

We hook all variants present in the manifest so the registry is
populated regardless of which ctor the compiler chose at each call site.

Warnings
===
A self_view that has no matching constructor symbol in the manifest
likely means the constructor is inlined or only appears via placement
new.  We emit a comment warning in the generated file and print to
stderr so it shows up in the build log.

from __future__ import annotations

import sys
import re
from pathlib import Path
from typing import List


_CTOR_SUFFIXES = ("C1", "C2", "C3")
_DTOR_SUFFIXES = ("D0", "D1", "D2")


def _mangled_is_ctor(mangled: str, class_name: str) -> bool:
    escaped = re.escape(class_name)
    return bool(re.search(rf'{escaped}(?:\d+)?[CD][123]', mangled))


def _mangled_is_dtor(mangled: str, class_name: str) -> bool:
    escaped = re.escape(class_name)
    return bool(re.search(rf'{escaped}(?:\d+)?D[012]', mangled))


def _collect_ctor_dtor_mangled(
    functions: List[dict],
    class_name: str,
) -> tuple[List[str], List[str]]:
    """Return ([ctor mangled names], [dtor mangled names]) for class_name."""
    ctors: List[str] = []
    dtors: List[str] = []
    for fn in functions:
        mangled = fn.get("mangled") or ""
        if not mangled:
            continue
        sv = fn.get("self_view") or ""
        if sv != class_name:
            continue
        flat = fn.get("flat") or fn.get("mangled") or ""
        is_ctor = (
            f"::{class_name}" in flat and "~" not in flat
            and (flat.endswith(f"::{class_name}") or f"::{class_name}(" in flat)
        ) or _mangled_is_ctor(mangled, class_name)
        is_dtor = (
            f"::~{class_name}" in flat
        ) or _mangled_is_dtor(mangled, class_name)

        if is_ctor and mangled not in ctors:
            ctors.append(mangled)
        elif is_dtor and mangled not in dtors:
            dtors.append(mangled)
    return ctors, dtors


def generate_registry(manifest: dict, output_path: str) -> None:
    """
    Read self_view values from *manifest* and write augment_generated_registry.cpp
    to *output_path*.

    manifest    - the raw AST manifest dict produced by phase 1 (no RVAs required).
    output_path - destination path; parent directories are created if needed.
    """
    functions: List[dict] = manifest.get("functions", [])

    seen_classes: dict[str, None] = {}
    for fn in functions:
        sv = fn.get("self_view")
        if sv and sv not in seen_classes:
            seen_classes[sv] = None
    classes = list(seen_classes)

    lines: List[str] = [
        "// augment_generated_registry.cpp",
        "// Automatically generated. Do not edit by hand.",
        "//",
        "// Registers / unregisters live class instances so that modding scripts",
        "// can call member functions without holding a pointer.",
        "",
        "#include \"augment/augment.hpp\"",
        "",
    ]

    no_ctor_classes: List[str] = []

    for class_name in classes:
        ctors, dtors = _collect_ctor_dtor_mangled(functions, class_name)

        if not ctors:
            no_ctor_classes.append(class_name)
            lines += [
                f"// WARNING: no constructor symbol found for '{class_name}'.",
                f"// Instances will NOT be registered automatically.",
                f"// The constructor may be inlined or only used via placement new.",
                "",
            ]
            continue

        lines.append(f"// === {class_name} ===")

        for mangled in ctors:
            lines += [
                f'AUGMENT_HOOK({mangled}, [](AugmentCtx* ctx) {{',
                f'    augment_register_instance("{class_name}", ctx->self);',
                f'}});',
            ]

        if dtors:
            for mangled in dtors:
                lines += [
                    f'AUGMENT_HOOK({mangled}, [](AugmentCtx* ctx) {{',
                    f'    augment_unregister_instance("{class_name}", ctx->self);',
                    f'}});',
                ]
        else:
            # Emit a comment; missing dtor is less critical (instance leaks from
            # the registry table rather than causing a bad call) but worth noting.
            lines += [
                f"// NOTE: no destructor symbol found for '{class_name}'.",
                f"// Instances will not be unregistered on destruction.",
            ]

        lines.append("")

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")

    n_ok  = len(classes) - len(no_ctor_classes)
    n_warn = len(no_ctor_classes)
    print(
        f"[registry] wrote {output_path}: "
        f"{n_ok} class(es) registered, "
        f"{n_warn} warning(s) (no ctor found)"
    )

    if no_ctor_classes:
        print(
            "[registry] No constructor found for: "
            + ", ".join(no_ctor_classes),
            file=sys.stderr,
        )
"""