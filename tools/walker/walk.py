#!/usr/bin/env python3
"""
walk.py
-----------------
Walks one or more C/C++ headers via libclang and emits:
  1. symbols.json            -> manifest of every hookable symbol with full signatures
  2. augment_ctx.hpp         -> generated ctx structs (one per symbol)
  3. augment_trampolines.cpp -> generated dispatch wrappers

Usage:
    python3 augment_walker.py [options] header1.hpp header2.hpp ...

Options:
    --output-dir DIR     Where to write the three output files (default: .)
    --symbol-prefix SYM  Only emit symbols whose qualified name starts with SYM
    --clang-args ARGS    Extra args forwarded to clang (e.g. -std=c++17 -Iinclude)
                         Separate multiple args with spaces; wrap in quotes.
    --json-only          Emit only symbols.json, skip codegen
    --help               Print this message

Dependencies:
    pip install -r requirements.txt
"""

import sys
import os
import json
import argparse
import textwrap
from pathlib import Path
from typing import Optional

try:
    import clang.cindex as clang
except ImportError:
    print("ERROR: libclang Python bindings not found.\n"
          "Install with:  pip install libclang", file=sys.stderr)
    sys.exit(1)

class Param:
    __slots__ = ("name", "type_spelling", "is_pointer", "is_ref",
                 "is_const", "pointee_spelling")

    def __init__(self, cursor: clang.Cursor):
        self.name           = cursor.spelling or f"_p{cursor.hash}"
        t                   = cursor.type
        self.type_spelling  = t.spelling
        self.is_pointer     = t.kind == clang.TypeKind.POINTER
        self.is_ref         = t.kind == clang.TypeKind.LVALUEREFERENCE
        self.is_const       = t.is_const_qualified()

        if self.is_pointer or self.is_ref:
            self.pointee_spelling = t.get_pointee().spelling
        else:
            self.pointee_spelling = ""

    def to_dict(self) -> dict:
        return {
            "name":             self.name,
            "type":             self.type_spelling,
            "is_pointer":       self.is_pointer,
            "is_ref":           self.is_ref,
            "is_const":         self.is_const,
            "pointee_type":     self.pointee_spelling,
        }

    # What type to store in the ctx struct for this param.
    # References become raw pointers; everything else is value.
    def ctx_field_type(self) -> str:
        if self.is_ref:
            # strip const from stored pointer
            base = self.pointee_spelling.replace("const ", "").strip()
            return f"{base}*"
        return self.type_spelling

    # How to initialise the ctx field from a call-site argument.
    def ctx_init_expr(self, arg_name: str) -> str:
        if self.is_ref:
            return f"&{arg_name}"
        return arg_name


class Symbol:
    __slots__ = ("qualified_name", "short_name", "namespace", "class_name",
                 "params", "return_type", "is_member", "is_const_method",
                 "source_file", "line")

    def __init__(self, cursor: clang.Cursor, tu_path: str):
        self.short_name      = cursor.spelling
        self.qualified_name  = _qualified_name(cursor)
        parts                = self.qualified_name.rsplit("::", 1)
        if len(parts) == 2:
            self.class_name  = parts[0].rsplit("::", 1)[-1]
            self.namespace   = parts[0].rsplit("::", 1)[0] if "::" in parts[0] else ""
        else:
            self.class_name  = ""
            self.namespace   = ""

        self.params          = [Param(c) for c in cursor.get_arguments()]
        self.return_type     = cursor.result_type.spelling
        self.is_member       = cursor.kind == clang.CursorKind.CXX_METHOD
        self.is_const_method = bool(cursor.is_const_method()) if self.is_member else False
        self.source_file     = tu_path
        self.line            = cursor.location.line

    def to_dict(self) -> dict:
        return {
            "symbol":           self.qualified_name,
            "short_name":       self.short_name,
            "class":            self.class_name,
            "namespace":        self.namespace,
            "is_member":        self.is_member,
            "is_const_method":  self.is_const_method,
            "return_type":      self.return_type,
            "returns_void":     self._returns_void(),
            "params":           [p.to_dict() for p in self.params],
            "source_file":      self.source_file,
            "line":             self.line,
        }

    def ctx_struct_name(self) -> str:
        """ctx_Namespace_Class_method  (colons replaced, spaces stripped)"""
        safe = self.qualified_name.replace("::", "_").replace(" ", "_")
        return f"ctx_{safe}"

    def _returns_void(self) -> bool:
        return self.return_type.strip() == "void"

# AST Traversal

def _qualified_name(cursor: clang.Cursor) -> str:
    parts = []
    c = cursor
    while c and c.kind not in (clang.CursorKind.TRANSLATION_UNIT,
                                clang.CursorKind.INVALID_FILE):
        if c.spelling:
            parts.append(c.spelling)
        c = c.semantic_parent
    parts.reverse()
    return "::".join(parts)


def _is_hookable(cursor: clang.Cursor, prefix_filter: Optional[str]) -> bool:
    """True for non-inline, non-template, non-deleted member/free functions."""
    if cursor.kind not in (clang.CursorKind.CXX_METHOD,
                           clang.CursorKind.FUNCTION_DECL):
        return False
    # skip pure virtuals, deleted, defaulted
    if cursor.is_pure_virtual_method():
        return False
    if cursor.availability == clang.AvailabilityKind.NOT_AVAILABLE:
        return False
    # skip declarations without a definition body (forward decls in headers
    # without an inline body are fine, we want the declaration for ctx gen)
    qn = _qualified_name(cursor)
    if prefix_filter and not qn.startswith(prefix_filter):
        return False
    # skip compiler-generated operators we can't meaningfully hook
    boring = ("operator=", "operator==", "operator!=",
              "operator<", "operator>", "operator<<", "operator>>")
    if cursor.spelling in boring:
        return False
    return True


def walk_tu(tu: clang.TranslationUnit, source_path: str,
            prefix_filter: Optional[str]) -> list[Symbol]:
    symbols: list[Symbol] = []
    seen: set[str] = set()

    def visit(cursor: clang.Cursor):
        # Only descend into nodes from our file (avoid system headers)
        if cursor.location.file and cursor.location.file.name != source_path:
            return
        if _is_hookable(cursor, prefix_filter):
            qn = _qualified_name(cursor)
            if qn not in seen:
                seen.add(qn)
                symbols.append(Symbol(cursor, source_path))
        for child in cursor.get_children():
            visit(child)

    visit(tu.cursor)
    return symbols


# Code generation

_CTX_HEADER = textwrap.dedent("""\
    // AUTO-GENERATED by walk.py. Do not edit by hand.
    // Re-run via CMake: cmake --build . --target augment_codegen
    #pragma once
    #include <cstddef>
    #include "augment/augment.hpp"
{user_includes}

""")

_TRAMPOLINE_HEADER = textwrap.dedent("""\
    // AUTO-GENERATED by walk.py. Do not edit by hand.
    // Re-run via CMake: cmake --build . --target augment_codegen
    #include "augment_ctx.hpp"
    #include "augment/augment.hpp"
    #include <cstring>
{user_includes}
""")


def emit_ctx_struct(sym: Symbol) -> str:
    lines = [f"// {sym.qualified_name}  ({sym.source_file}:{sym.line})"]
    lines.append(f"struct {sym.ctx_struct_name()} {{")

    if sym.is_member:
        lines.append("    void*   self;       // owning instance")

    lines.append("    int     cancelled;  // set nonzero in BEFORE to skip original")

    for p in sym.params:
        lines.append(f"    {p.ctx_field_type():<16} {p.name};")

    if not sym._returns_void():
        lines.append(f"    {sym.return_type:<16} __return{{}};")

    lines.append("};")
    return "\n".join(lines)


def emit_ctx_pack_fn(sym: Symbol) -> str:
    """
    Emit a helper:
        augment_ctx_pack_{name}(AugmentCtx* actx, ctx_T* out)
    that unpacks the void** args array into the typed ctx struct.
    This is what generated trampoline dispatchers call.
    """
    sname = sym.ctx_struct_name()
    fn    = f"augment_ctx_pack_{sym.qualified_name.replace('::', '_')}"
    lines = [f"inline void {fn}(const AugmentCtx* actx, {sname}* out) {{"]

    i = 0
    if sym.is_member:
        lines.append(f"    out->self      = actx->self;")
    for p in sym.params:
        ct = p.ctx_field_type()
        if p.is_ref:
            # stored as pointer in ctx; arg slot holds T*
            lines.append(f"    out->{p.name:<12} = *static_cast<{ct}*>(actx->args[{i}]);")
        else:
            lines.append(f"    out->{p.name:<12} = *static_cast<{ct}*>(actx->args[{i}]);")
        i += 1

    if not sym._returns_void():
        lines.append(f"    out->__return  = *static_cast<{sym.return_type}*>(actx->ret);")

    lines.append("    out->cancelled = actx->cancelled;")
    lines.append("}")
    return "\n".join(lines)


def emit_trampoline(sym: Symbol) -> str:
    """
    Emit the dispatch wrapper function that:
      1. Packs typed ctx
      2. Calls augment chain dispatch (via macro / inline helper)
      3. Unpacks return value and mutated args back
    """
    sname   = sym.ctx_struct_name()
    fname   = sym.qualified_name.replace("::", "_")
    rt      = sym.return_type

    # Build parameter list for the wrapper signature
    sig_parts = []
    if sym.is_member:
        cls = sym.qualified_name.rsplit("::", 1)[0]
        sig_parts.append(f"{cls}* __self")
    for p in sym.params:
        sig_parts.append(f"{p.type_spelling} {p.name}")
    sig = ", ".join(sig_parts)

    # Build void* args array initialiser
    arg_addrs = []
    for p in sym.params:
        if p.is_ref:
            arg_addrs.append(f"(void*)&{p.name}")
        else:
            arg_addrs.append(f"(void*)&{p.name}")

    lines = [f"// Trampoline: {sym.qualified_name}"]
    lines.append(f"{rt} augment_dispatch_{fname}({sig}) {{")

    # args array
    if arg_addrs:
        lines.append(f"    void* __args[{len(arg_addrs)}] = {{ {', '.join(arg_addrs)} }};")
    else:
        lines.append( "    void* __args[1] = { nullptr };  // no params")

    # return slot
    if not sym._returns_void():
        lines.append(f"    {rt} __ret{{}};")
        lines.append( "    void* __ret_ptr = (void*)&__ret;")
    else:
        lines.append( "    void* __ret_ptr = nullptr;")

    # AugmentCtx
    self_expr = "(void*)__self" if sym.is_member else "nullptr"
    lines.append(f"    AugmentCtx __actx = {{ {self_expr}, __args, __ret_ptr, 0, nullptr }};")

    # Typed call to the original through the saved pointer
    if sym.is_member:
        cls = sym.qualified_name.rsplit("::", 1)[0]
        orig_params = ", ".join([f"{cls}*"] + [p.type_spelling for p in sym.params])
        call_args   = ", ".join(["__self"] + [p.name for p in sym.params])
    else:
        orig_params = ", ".join(p.type_spelling for p in sym.params)
        call_args   = ", ".join(p.name for p in sym.params)
    orig_fp = f"{rt}(*)({orig_params})"

    lines.append(f'    void* __saved = augment_before("{sym.qualified_name}", &__actx);')
    if not sym._returns_void():
        lines.append( "    if (__saved)")
        lines.append(f"        __ret = reinterpret_cast<{orig_fp}>(__saved)({call_args});")
    else:
        lines.append( "    if (__saved)")
        lines.append(f"        reinterpret_cast<{orig_fp}>(__saved)({call_args});")
    lines.append(f'    augment_after("{sym.qualified_name}", &__actx);')

    if not sym._returns_void():
        lines.append("    return __ret;")

    lines.append("}")
    return "\n".join(lines)

# Top-level emitter

def emit_ctx_hpp(symbols: list[Symbol], headers: list[str]) -> str:
    user_includes = "\n".join(f'#include "{h}"' for h in headers)
    parts = [_CTX_HEADER.format(user_includes=user_includes)]
    for sym in symbols:
        parts.append(emit_ctx_struct(sym))
        parts.append("")
        parts.append(emit_ctx_pack_fn(sym))
        parts.append("")
    return "\n".join(parts)

def emit_ptr_registrar(sym: Symbol) -> str:
    fname = sym.qualified_name.replace("::", "_")
    dispatch_name = f"augment_dispatch_{fname}"

    lines = [
        f"// Ptr registrar: {sym.qualified_name}",
        f"namespace {{",
        f"struct _AugmentPtrReg_{fname} {{",
        f"    _AugmentPtrReg_{fname}() {{",
        f"        augment_register_ptr(\"{sym.qualified_name}\",",
        f"            reinterpret_cast<void*>(&{dispatch_name}));",
        f"    }}",
        f"}} _augment_ptr_reg_{fname}_inst;",
        f"}} // namespace",
    ]
    return "\n".join(lines)

def emit_trampoline_decl(sym: Symbol) -> str:
    fname = sym.qualified_name.replace("::", "_")
    sig_parts = []
    if sym.is_member:
        cls = sym.qualified_name.rsplit("::", 1)[0]
        sig_parts.append(f"{cls}* __self")
    for p in sym.params:
        sig_parts.append(f"{p.type_spelling} {p.name}")
    sig = ", ".join(sig_parts)
    return f"{sym.return_type} augment_dispatch_{fname}({sig});"

def emit_trampolines_cpp(symbols: list[Symbol], headers: list[str]) -> str:
    user_includes = "\n".join(f'#include "{h}"' for h in headers)
    parts = [_TRAMPOLINE_HEADER.format(user_includes=user_includes)]
    parts.append('extern "C" void augment_invoke(const char* symbol, AugmentCtx* ctx);')
    parts.append('extern "C" void augment_register_ptr(const char* symbol, void* ptr);')
    parts.append("")

    # Forward declarations
    for sym in symbols:
        parts.append(emit_trampoline_decl(sym))
    parts.append("")

    # Definitions + registrars
    for sym in symbols:
        parts.append(emit_trampoline(sym))
        parts.append("")
        parts.append(emit_ptr_registrar(sym))
        parts.append("")

    return "\n".join(parts)

def emit_manifest_json(symbols: list[Symbol]) -> str:
    return json.dumps(
        {
            "version": 1,
            "symbols": [s.to_dict() for s in symbols],
        },
        indent=2,
    )

# CLI

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Augment codebase walker: emits ctx structs, "
                    "trampolines, and symbol manifest from C++ headers.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("headers", nargs="+", metavar="HEADER",
                   help="Header files to walk")
    p.add_argument("--output-dir", default=".",
                   help="Directory to write output files (default: .)")
    p.add_argument("--symbol-prefix", default=None,
                   help="Only emit symbols whose qualified name starts with this")
    p.add_argument("--clang-args", default="",
                   help="Extra clang flags, space-separated (e.g. '-std=c++17 -Iinclude')")
    p.add_argument("--json-only", action="store_true",
                   help="Emit only symbols.json, skip hpp/cpp codegen")
    return p.parse_args()


def main():
    args = parse_args()

    index       = clang.Index.create()
    clang_flags = args.clang_args.split() if args.clang_args else []
    # Always compile as C++17 unless caller overrides
    if not any(f.startswith("-std=") for f in clang_flags):
        clang_flags = ["-std=c++17"] + clang_flags

    all_symbols: list[Symbol] = []
    errors = 0

    for header in args.headers:
        header = os.path.abspath(header)
        if not os.path.exists(header):
            print(f"ERROR: file not found: {header}", file=sys.stderr)
            errors += 1
            continue

        tu = index.parse(header, args=clang_flags,
                         options=clang.TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD |
                                 clang.TranslationUnit.PARSE_SKIP_FUNCTION_BODIES)

        diag_errors = [d for d in tu.diagnostics
                       if d.severity >= clang.Diagnostic.Error]
        if diag_errors:
            for d in diag_errors:
                print(f"  clang [{header}]: {d.spelling}", file=sys.stderr)
            # non-fatal: partial AST is still useful
            errors += len(diag_errors)

        syms = walk_tu(tu, header, args.symbol_prefix)
        print(f"  {header}: {len(syms)} symbol(s) found")
        all_symbols.extend(syms)

    if not all_symbols:
        print("No hookable symbols found. Nothing to emit.")
        sys.exit(0 if not errors else 1)

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # Always emit the manifest
    manifest_path = out / "symbols.json"
    manifest_path.write_text(emit_manifest_json(all_symbols))
    print(f"  -> {manifest_path}  ({len(all_symbols)} symbols)")

    if not args.json_only:
        ctx_path = out / "augment_ctx.hpp"
        ctx_path.write_text(emit_ctx_hpp(all_symbols, args.headers))
        print(f"  -> {ctx_path}")

        tramp_path = out / "augment_trampolines.cpp"
        tramp_path.write_text(emit_trampolines_cpp(all_symbols, args.headers))
        print(f"  -> {tramp_path}")

    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
