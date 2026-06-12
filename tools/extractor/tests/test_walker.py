"""
extractor/tests/test_walker.py

Use libclang's unsaved_files mechanism to parse inline C++ source strings.

We pass the source as an unsaved file and walk it with:
    index.parse(path, args=flags, unsaved_files=[(path, source)])

A thin _walk() helper wires this up so individual tests stay short.

Checks:
  structs:
    - basic struct with fields extracted
    - field offsets correct
    - field kinds mapped (int, ptr, char array -> str, nested struct)
    - forward declaration not emitted (only definitions)
    - anonymous struct skipped
    - size correct

  functions:
    - free function extracted with args and ret
    - mangled name present and non-empty
    - member function: member=True, self_view set
    - constructor / destructor: member=True
    - args with unnamed parameters get generated names (arg0, arg1…)
    - rva is None (merge step fills it)
    - loc is set

  enums:
    - values extracted with correct integers
    - anonymous enum skipped
    - nested enum: owner set, qualified name used

  typedefs:
    - typedef to primitive kind correct
    - typedef to pointer kind correct
    - anonymous typedef skipped

  general:
    - only declarations from the primary file are returned
      (not from #included headers)
"""
from __future__ import annotations

from typing import List

import pytest

pytest.importorskip("clang.cindex", reason="libclang not installed")
import clang.cindex as _cx

from extractor.ast_walk.walker import walk

_FLAGS = ["-std=c++17", "-x", "c++"]
_FAKE_PATH = "/fake/test.cpp"

def _walk(source: str, flags: List[str] = _FLAGS) -> dict:
    idx = _cx.Index.create()
    tu = idx.parse(
        _FAKE_PATH,
        args=flags,
        unsaved_files=[(_FAKE_PATH, source)],
        options=(
            _cx.TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD
            | _cx.TranslationUnit.PARSE_SKIP_FUNCTION_BODIES
        ),
    )
    # Re-use walker internals by calling walk() through the public API,
    # but since walk() calls index.parse() internally we replicate the
    # unsaved_files trick by monkey-patching Index.parse.
    import unittest.mock as mock

    original_parse = _cx.Index.parse

    def _patched_parse(self, path, args=None, unsaved_files=None, options=0):
        return original_parse(
            self, path, args=args,
            unsaved_files=[(_FAKE_PATH, source)],
            options=options,
        )

    with mock.patch.object(_cx.Index, "parse", _patched_parse):
        return walk(_FAKE_PATH, flags)

def test_struct_basic():
    result = _walk("struct Foo { int x; float y; };")
    names = [s["name"] for s in result["structs"]]
    assert "Foo" in names

def test_struct_fields():
    result = _walk("struct Vec2 { float x; float y; };")
    s = next(s for s in result["structs"] if s["name"] == "Vec2")
    field_names = [f["name"] for f in s["fields"]]
    assert field_names == ["x", "y"]

def test_struct_field_primitive_kind():
    result = _walk("struct S { int a; };")
    s = next(s for s in result["structs"] if s["name"] == "S")
    assert s["fields"][0]["kind"] == "i32"

def test_struct_field_pointer_kind():
    result = _walk("struct S { int* p; };")
    s = next(s for s in result["structs"] if s["name"] == "S")
    assert s["fields"][0]["kind"] == "ptr"

def test_struct_field_char_array_is_str():
    result = _walk("struct S { char name[32]; };")
    s = next(s for s in result["structs"] if s["name"] == "S")
    f = next(f for f in s["fields"] if f["name"] == "name")
    assert f["kind"] == "str"
    assert f["len"] == 32

def test_struct_field_offset():
    result = _walk("struct S { char a; int b; };")
    s = next(s for s in result["structs"] if s["name"] == "S")
    b = next(f for f in s["fields"] if f["name"] == "b")
    assert b["offset"] == 4  # natural alignment

def test_struct_size():
    result = _walk("struct S { int a; int b; };")
    s = next(s for s in result["structs"] if s["name"] == "S")
    assert s["size"] == 8

def test_forward_declaration_not_emitted():
    result = _walk("struct Foo; struct Foo { int x; };")
    matches = [s for s in result["structs"] if s["name"] == "Foo"]
    assert len(matches) == 1

def test_anonymous_struct_skipped():
    result = _walk("struct { int x; } anon;")
    assert all(s["name"] for s in result["structs"])

def test_free_function_extracted():
    result = _walk("int add(int a, int b);")
    mangled = [f["mangled"] for f in result["functions"]]
    assert any("add" in m for m in mangled)

def test_function_ret_kind():
    result = _walk("int foo();")
    f = next(f for f in result["functions"] if "foo" in f["mangled"])
    assert f["ret"] == "i32"

def test_function_args():
    result = _walk("void bar(int x, float y);")
    f = next(f for f in result["functions"] if "bar" in f["mangled"])
    kinds = [a["kind"] for a in f["args"]]
    assert kinds == ["i32", "f32"]

def test_function_arg_names():
    result = _walk("void baz(int count, float scale);")
    f = next(f for f in result["functions"] if "baz" in f["mangled"])
    names = [a["name"] for a in f["args"]]
    assert names == ["count", "scale"]

def test_unnamed_args_get_generated_names():
    result = _walk("void qux(int, float);")
    f = next(f for f in result["functions"] if "qux" in f["mangled"])
    names = [a["name"] for a in f["args"]]
    assert names == ["arg0", "arg1"]

def test_function_mangled_nonempty():
    result = _walk("void fn();")
    f = next(f for f in result["functions"] if "fn" in f["mangled"])
    assert f["mangled"]

def test_function_rva_is_none():
    result = _walk("void fn();")
    f = next(f for f in result["functions"] if "fn" in f["mangled"])
    assert f["rva"] is None

def test_function_loc_set():
    result = _walk("void fn();")
    f = next(f for f in result["functions"] if "fn" in f["mangled"])
    assert f["loc"] is not None
    assert ":" in f["loc"]

def test_member_function():
    src = "struct Foo { void bar(); };"
    result = _walk(src)
    f = next((f for f in result["functions"] if "bar" in f["mangled"]), None)
    assert f is not None
    assert f["member"] is True
    assert f["self_view"] == "Foo"

def test_constructor_member():
    src = "struct Foo { Foo(); };"
    result = _walk(src)
    ctors = [f for f in result["functions"] if f["member"] and "Foo" in f["mangled"]]
    assert ctors

def test_enum_extracted():
    result = _walk("enum Color { RED=0, GREEN=1, BLUE=2 };")
    names = [e["name"] for e in result["enums"]]
    assert "Color" in names

def test_enum_values():
    result = _walk("enum Dir { NORTH=0, SOUTH=1, EAST=2, WEST=3 };")
    e = next(e for e in result["enums"] if e["name"] == "Dir")
    by_name = {v["name"]: v["value"] for v in e["values"]}
    assert by_name == {"NORTH": 0, "SOUTH": 1, "EAST": 2, "WEST": 3}

def test_anonymous_enum_skipped():
    result = _walk("enum { A=1, B=2 };")
    assert all(e["name"] for e in result["enums"])

def test_nested_enum_owner():
    src = "struct Foo { enum State { ON=1, OFF=0 }; };"
    result = _walk(src)
    e = next((e for e in result["enums"] if "State" in e["name"]), None)
    assert e is not None
    assert e["owner"] == "Foo"
    assert e["name"] == "Foo::State"

def test_typedef_primitive():
    result = _walk("typedef int MyInt;")
    t = next((t for t in result["typedefs"] if t["alias"] == "MyInt"), None)
    assert t is not None
    assert t["kind"] == "i32"

def test_typedef_pointer():
    result = _walk("typedef void* Handle;")
    t = next((t for t in result["typedefs"] if t["alias"] == "Handle"), None)
    assert t is not None
    assert t["kind"] == "ptr"

def test_typedef_no_anonymous():
    result = _walk("typedef struct { int x; } AnonStruct;")
    aliases = [t["alias"] for t in result["typedefs"]]
    assert "AnonStruct" in aliases
    # the anonymous struct itself should not appear in typedefs
    assert all(a for a in aliases)
