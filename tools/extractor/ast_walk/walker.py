"""
extractor/ast/walker.py

Walk a translation unit with libclang and [extract]
  - structs / classes / unions  (fields, sizes)
  - functions / methods         (args, return type, mangled name)
  - enums                       (values)
  - typedefs
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

try:
    import clang.cindex as _cx
except ImportError:  # pragma: no cover
    raise ImportError("walker requires the libclang Python bindings: pip install libclang")

import subprocess as _sp
from pathlib import Path

def _resource_dir() -> str:
    try:
        return _sp.run(
            ["clang", "--print-resource-dir"],
            capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:
        return ""


_PROJECT_ROOT: Optional[Path] = None


def set_project_root(path: str) -> None:
    global _PROJECT_ROOT
    _PROJECT_ROOT = Path(path).resolve()


def _is_system_cursor(cursor: _cx.Cursor) -> bool:
    f = cursor.location.file
    if not f:
        return True
    try:
        if _cx.conf.lib.clang_Location_isInSystemHeader(cursor.location):
            return True
    except AttributeError:
        pass

    try:
        file_resolved = Path(f.name).resolve()
    except (ValueError, OSError):
        return True

    root = _PROJECT_ROOT
    if root is None:
        return False

    try:
        file_resolved.relative_to(root)
        return False
    except ValueError:
        return True


def walk(
    source_path: str,
    flags: List[str],
    index: Optional[Any] = None,
) -> Dict[str, List[dict]]:
    """
    Parse *source_path* with the given compiler *flags* and return::

        {
            "structs":   [...],
            "functions": [...],
            "enums":     [...],
            "typedefs":  [...],
        }

    *index* is an optional ``clang.cindex.Index``. Pass one in when
    walking many files so the global index is reused.
    """
    if index is None:
        index = _cx.Index.create()

    rd = _resource_dir()
    if rd:
        flags = [f"-resource-dir={rd}"] + list(flags)

    tu = index.parse(
        source_path,
        args=flags,
        options=(
            _cx.TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD
            | _cx.TranslationUnit.PARSE_SKIP_FUNCTION_BODIES
        ),
    )

    _check_diagnostics(tu, source_path)

    structs: List[dict]   = []
    functions: List[dict] = []
    enums: List[dict]     = []
    typedefs: List[dict]  = []

    seen_structs:   set = set()
    seen_functions: set = set()
    seen_enums:     set = set()
    seen_typedefs:  set = set()

    def visit(cursor: _cx.Cursor) -> None:
        kind = cursor.kind

        if kind in (_cx.CursorKind.STRUCT_DECL,
                    _cx.CursorKind.CLASS_DECL,
                    _cx.CursorKind.UNION_DECL):
            _visit_struct(cursor, structs, seen_structs)

        elif kind in (_cx.CursorKind.FUNCTION_DECL,
                      _cx.CursorKind.CXX_METHOD,
                      _cx.CursorKind.CONSTRUCTOR,
                      _cx.CursorKind.DESTRUCTOR):
            _visit_function(cursor, functions, seen_functions)

        elif kind == _cx.CursorKind.ENUM_DECL:
            _visit_enum(cursor, enums, seen_enums)

        elif kind == _cx.CursorKind.TYPEDEF_DECL:
            _visit_typedef(cursor, typedefs, seen_typedefs)

        for child in cursor.get_children():
            visit(child)

    for child in tu.cursor.get_children():
        visit(child)

    return {
        "structs":   structs,
        "functions": functions,
        "enums":     enums,
        "typedefs":  typedefs,
    }

_PRIM = {
    "void": "void",
    "bool": "u8", "_Bool": "u8",
    "char": "i8", "signed char": "i8", "unsigned char": "u8",
    "short": "i16", "short int": "i16", "signed short": "i16",
    "unsigned short": "u16", "unsigned short int": "u16",
    "int": "i32", "signed int": "i32", "signed": "i32",
    "unsigned int": "u32", "unsigned": "u32",
    "long": "i32", "long int": "i32", "signed long": "i32",
    "unsigned long": "u32", "unsigned long int": "u32",
    "long long": "i64", "long long int": "i64",
    "unsigned long long": "u64", "unsigned long long int": "u64",
    "float": "f32", "double": "f64", "long double": "f64",
    "int8_t": "i8",  "uint8_t":  "u8",
    "int16_t": "i16", "uint16_t": "u16",
    "int32_t": "i32", "uint32_t": "u32",
    "int64_t": "i64", "uint64_t": "u64",
    "size_t": "u64", "ptrdiff_t": "i64",
    "intptr_t": "i64", "uintptr_t": "u64",
    "wchar_t": "i16",
}

_CHAR_ARR_RE = re.compile(r"^(?:const\s+)?(?:unsigned\s+)?char\s*\[(\d+)\]$")

def _type_kind(clang_type: _cx.Type) -> dict:
    """Map a libclang Type to a minimal schema dict."""
    tk = clang_type.kind

    # pointer / reference
    if tk in (_cx.TypeKind.POINTER,
              _cx.TypeKind.LVALUEREFERENCE,
              _cx.TypeKind.RVALUEREFERENCE,
              _cx.TypeKind.MEMBERPOINTER):
        pointee = clang_type.get_pointee()
        pointee_name = pointee.spelling.replace("const ", "").replace("volatile ", "").strip()
        return {"kind": "ptr", "view": pointee_name} if pointee_name and pointee_name != "void" else {"kind": "ptr"}

    # fixed-size array
    if tk == _cx.TypeKind.CONSTANTARRAY:
        elem = clang_type.get_array_element_type()
        size = clang_type.get_array_size()
        spelling = clang_type.spelling
        if _CHAR_ARR_RE.match(spelling):
            return {"kind": "str", "len": size}
        return {"kind": "array", "len": size}

    # typedef / elaborated
    if tk in (_cx.TypeKind.TYPEDEF, _cx.TypeKind.ELABORATED):
        return _type_kind(clang_type.get_canonical())

    # named type
    spelling = clang_type.spelling.replace("const ", "").replace("volatile ", "").strip()
    if spelling in _PRIM:
        return {"kind": _PRIM[spelling]}

    canonical = clang_type.get_canonical().spelling.replace("const ", "").strip()
    if canonical in _PRIM:
        return {"kind": _PRIM[canonical]}

    # struct / class / union / enum by name
    decl = clang_type.get_declaration()
    if decl and decl.kind in (_cx.CursorKind.STRUCT_DECL,
                               _cx.CursorKind.CLASS_DECL,
                               _cx.CursorKind.UNION_DECL):
        name = decl.spelling or spelling
        return {"kind": f"struct:{name}", "view": name}

    return {"kind": "ptr"}

def _struct_key(cursor: _cx.Cursor) -> str:
    return cursor.type.spelling or cursor.spelling

def _visit_struct(cursor: _cx.Cursor, out: list, seen: set) -> None:
    if _is_system_cursor(cursor):
        return
    if not cursor.is_definition():
        return
    name = cursor.spelling
    if not name or _is_anonymous(name):
        return
    key = _struct_key(cursor)
    if key in seen:
        return
    seen.add(key)

    fields = []
    for child in cursor.get_children():
        if child.kind == _cx.CursorKind.FIELD_DECL:
            schema = _type_kind(child.type)
            f = {"name": child.spelling, "offset": child.get_field_offsetof() // 8}
            f.update(schema)
            fields.append(f)

    size = cursor.type.get_size()
    out.append({
        "name":   name,
        "size":   size if size > 0 else 0,
        "fields": fields,
    })

def _visit_function(cursor: _cx.Cursor, out: list, seen: set) -> None:
    if _is_system_cursor(cursor):
        return
    mangled = cursor.mangled_name
    if not mangled or mangled in seen:
        return
    seen.add(mangled)

    ret_schema = _type_kind(cursor.result_type)
    ret = ret_schema.get("kind", "void")

    args = []
    for arg in cursor.get_arguments():
        schema = _type_kind(arg.type)
        a = {"name": arg.spelling or f"arg{len(args)}"}
        a.update(schema)
        args.append(a)

    member = cursor.kind in (
        _cx.CursorKind.CXX_METHOD,
        _cx.CursorKind.CONSTRUCTOR,
        _cx.CursorKind.DESTRUCTOR,
    )

    self_view: Optional[str] = None
    if member:
        parent = cursor.semantic_parent
        if parent and parent.kind in (_cx.CursorKind.CLASS_DECL,
                                       _cx.CursorKind.STRUCT_DECL):
            self_view = parent.spelling or None

    loc = None
    if cursor.location.file:
        loc = f"{cursor.location.file.name}:{cursor.location.line}"

    flat = _flat(cursor.spelling, cursor.semantic_parent)

    out.append({
        "flat":      flat,
        "mangled":   mangled,
        "member":    member,
        "self_view": self_view,
        "rva":       None,
        "loc":       loc,
        "ret":       ret,
        "args":      args,
    })

def _visit_enum(cursor: _cx.Cursor, out: list, seen: set) -> None:
    if _is_system_cursor(cursor):
        return
    if not cursor.is_definition():
        return
    name = cursor.spelling
    if not name or _is_anonymous(name):
        return
    if name in seen:
        return
    seen.add(name)

    values = []
    for child in cursor.get_children():
        if child.kind == _cx.CursorKind.ENUM_CONSTANT_DECL:
            values.append({"name": child.spelling, "value": child.enum_value})

    owner = None
    parent = cursor.semantic_parent
    if parent and parent.kind in (_cx.CursorKind.CLASS_DECL,
                                   _cx.CursorKind.STRUCT_DECL):
        owner = parent.spelling or None

    qualified = f"{owner}::{name}" if owner else name
    out.append({"name": qualified, "owner": owner, "values": values})

def _visit_typedef(cursor: _cx.Cursor, out: list, seen: set) -> None:
    if _is_system_cursor(cursor):
        return
    alias = cursor.spelling
    if not alias or alias in seen or _is_anonymous(alias):
        return
    seen.add(alias)

    schema = _type_kind(cursor.underlying_typedef_type)
    entry = {"alias": alias}
    entry.update(schema)
    out.append(entry)

def _is_anonymous(name: str) -> bool:
    markers = ["(anonymous", "<anonymous", "__unnamed", "$anon", "<unnamed"]
    return any(m in name for m in markers)

def _flat(spelling: str, parent: Optional[_cx.Cursor]) -> str:
    base = spelling.split("(")[0].strip()
    if parent and parent.kind in (_cx.CursorKind.CLASS_DECL,
                                   _cx.CursorKind.STRUCT_DECL,
                                   _cx.CursorKind.NAMESPACE):
        prefix = parent.spelling
        if prefix:
            base = f"{prefix}_{base}"
    return base.replace("::", "_").replace(" ", "")

def _check_diagnostics(tu: Any, path: str) -> list[str]:
    """
    Return a list of error message strings for any Error/Fatal diagnostics.
    """
    errors = [d for d in tu.diagnostics
              if d.severity >= _cx.Diagnostic.Error]
    return [d.spelling for d in errors]
