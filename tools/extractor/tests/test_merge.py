"""
extractor/tests/test_merge.py

Checks:
  both match:
    - AST shape preserved (args, ret, member, self_view, loc, flat)
    - RVA filled in as hex string
    - mangled key correct

  AST-only:
    - emitted with rva=None
    - all shape fields intact

  RVA-only:
    - opaque stub emitted
    - rva hex string correct
    - args is empty list
    - ret is "ptr"
    - member is False
    - loc is None

  sorting:
    - functions sorted by (flat, mangled)
    - structs sorted by name
    - enums sorted by name
    - typedefs sorted by alias

  passthrough:
    - structs, enums, typedefs from AST passed through unchanged (content)
    - version == 2

  edge cases:
    - empty ast + empty rva_map -> valid empty manifest
    - empty rva_map -> all functions have rva=None
    - empty ast functions -> all rva_map entries become opaque stubs
    - duplicate mangled in rva_map (can't happen by type, but rva=0 edge):
      rva_map contract is Dict[str,int] so no duplicates possible
"""
import pytest
from extractor.merge import merge

def _fn(mangled, flat="fn", ret="void", args=None, member=False,
        self_view=None, loc=None):
    return {
        "flat": flat, "mangled": mangled, "member": member,
        "self_view": self_view, "rva": None, "loc": loc,
        "ret": ret, "args": args or [],
    }

def _struct(name, size=4, fields=None):
    return {"name": name, "size": size, "fields": fields or []}

def _enum(name, values=None):
    return {"name": name, "owner": None, "values": values or []}

def _typedef(alias, kind="i32"):
    return {"alias": alias, "kind": kind}

def test_both_rva_filled():
    ast = {"functions": [_fn("_ZN3Foo3barEi", flat="Foo_bar", ret="i32")],
           "structs": [], "enums": [], "typedefs": []}
    result = merge(ast, {"_ZN3Foo3barEi": 0x1100})
    fn = result["functions"][0]
    assert fn["rva"] == "0x1100"

def test_both_shape_preserved():
    args = [{"name": "x", "kind": "i32"}]
    ast = {"functions": [_fn("_Z3fooi", flat="foo", ret="i32", args=args,
                              loc="foo.cpp:10")],
           "structs": [], "enums": [], "typedefs": []}
    result = merge(ast, {"_Z3fooi": 0x2000})
    fn = result["functions"][0]
    assert fn["ret"]  == "i32"
    assert fn["args"] == args
    assert fn["loc"]  == "foo.cpp:10"
    assert fn["flat"] == "foo"

def test_both_mangled_correct():
    ast = {"functions": [_fn("_Z3fooi")],
           "structs": [], "enums": [], "typedefs": []}
    result = merge(ast, {"_Z3fooi": 0x1})
    assert result["functions"][0]["mangled"] == "_Z3fooi"

def test_both_member_fields():
    ast = {"functions": [_fn("_ZN3Foo3barEv", member=True, self_view="Foo")],
           "structs": [], "enums": [], "typedefs": []}
    result = merge(ast, {"_ZN3Foo3barEv": 0x500})
    fn = result["functions"][0]
    assert fn["member"]    is True
    assert fn["self_view"] == "Foo"

def test_ast_only_rva_none():
    ast = {"functions": [_fn("_Z3bazv")],
           "structs": [], "enums": [], "typedefs": []}
    result = merge(ast, {})
    assert result["functions"][0]["rva"] is None

def test_ast_only_shape_intact():
    args = [{"name": "n", "kind": "u32"}]
    ast = {"functions": [_fn("_Z3bazv", ret="u32", args=args)],
           "structs": [], "enums": [], "typedefs": []}
    result = merge(ast, {})
    fn = result["functions"][0]
    assert fn["ret"]  == "u32"
    assert fn["args"] == args

def test_rva_only_stub_emitted():
    ast = {"functions": [], "structs": [], "enums": [], "typedefs": []}
    result = merge(ast, {"_ZN3Foo6secretEv": 0x9900})
    assert any(f["mangled"] == "_ZN3Foo6secretEv" for f in result["functions"])

def test_rva_only_rva_correct():
    ast = {"functions": [], "structs": [], "enums": [], "typedefs": []}
    result = merge(ast, {"_ZN3Foo6secretEv": 0x9900})
    fn = next(f for f in result["functions"] if f["mangled"] == "_ZN3Foo6secretEv")
    assert fn["rva"] == "0x9900"

def test_rva_only_args_empty():
    ast = {"functions": [], "structs": [], "enums": [], "typedefs": []}
    result = merge(ast, {"_ZN3Foo6secretEv": 0x1})
    fn = result["functions"][0]
    assert fn["args"] == []

def test_rva_only_ret_ptr():
    ast = {"functions": [], "structs": [], "enums": [], "typedefs": []}
    result = merge(ast, {"_ZN3Foo6secretEv": 0x1})
    assert result["functions"][0]["ret"] == "ptr"

def test_rva_only_member_false():
    ast = {"functions": [], "structs": [], "enums": [], "typedefs": []}
    result = merge(ast, {"_ZN3Foo6secretEv": 0x1})
    assert result["functions"][0]["member"] is False

def test_rva_only_loc_none():
    ast = {"functions": [], "structs": [], "enums": [], "typedefs": []}
    result = merge(ast, {"_ZN3Foo6secretEv": 0x1})
    assert result["functions"][0]["loc"] is None

def test_rva_only_not_duplicated_when_also_in_ast():
    """A mangled name present in both must not appear twice."""
    ast = {"functions": [_fn("_Z3fooi")], "structs": [], "enums": [], "typedefs": []}
    result = merge(ast, {"_Z3fooi": 0x100})
    matches = [f for f in result["functions"] if f["mangled"] == "_Z3fooi"]
    assert len(matches) == 1

def test_functions_sorted_by_flat_then_mangled():
    fns = [
        _fn("_Z1cv", flat="c"),
        _fn("_Z1av", flat="a"),
        _fn("_Z1bv", flat="b"),
    ]
    ast = {"functions": fns, "structs": [], "enums": [], "typedefs": []}
    result = merge(ast, {})
    flats = [f["flat"] for f in result["functions"]]
    assert flats == sorted(flats)

def test_structs_sorted_by_name():
    ast = {"functions": [],
           "structs": [_struct("Zoo"), _struct("Alpha"), _struct("Mango")],
           "enums": [], "typedefs": []}
    result = merge(ast, {})
    names = [s["name"] for s in result["structs"]]
    assert names == sorted(names)

def test_enums_sorted_by_name():
    ast = {"functions": [], "structs": [],
           "enums": [_enum("Z"), _enum("A"), _enum("M")],
           "typedefs": []}
    result = merge(ast, {})
    names = [e["name"] for e in result["enums"]]
    assert names == sorted(names)

def test_typedefs_sorted_by_alias():
    ast = {"functions": [], "structs": [], "enums": [],
           "typedefs": [_typedef("ZAlias"), _typedef("AAlias"), _typedef("MAlias")]}
    result = merge(ast, {})
    aliases = [t["alias"] for t in result["typedefs"]]
    assert aliases == sorted(aliases)

def test_version_is_2():
    ast = {"functions": [], "structs": [], "enums": [], "typedefs": []}
    assert merge(ast, {})["version"] == 2

def test_structs_content_unchanged():
    s = _struct("Foo", size=8, fields=[{"name": "x", "offset": 0, "kind": "i32"}])
    ast = {"functions": [], "structs": [s], "enums": [], "typedefs": []}
    result = merge(ast, {})
    assert result["structs"][0] == s

def test_enums_content_unchanged():
    e = _enum("Color", values=[{"name": "RED", "value": 0}])
    ast = {"functions": [], "structs": [], "enums": [e], "typedefs": []}
    result = merge(ast, {})
    assert result["enums"][0] == e

def test_typedefs_content_unchanged():
    t = _typedef("MyInt", kind="i32")
    ast = {"functions": [], "structs": [], "enums": [], "typedefs": [t]}
    result = merge(ast, {})
    assert result["typedefs"][0] == t

def test_empty_both():
    ast = {"functions": [], "structs": [], "enums": [], "typedefs": []}
    result = merge(ast, {})
    assert result["functions"] == []
    assert result["structs"]   == []

def test_empty_rva_map_all_none():
    ast = {"functions": [_fn("_Z1av"), _fn("_Z1bv")],
           "structs": [], "enums": [], "typedefs": []}
    result = merge(ast, {})
    assert all(f["rva"] is None for f in result["functions"])

def test_empty_ast_functions_all_opaque():
    rva_map = {"_Z1av": 0x100, "_Z1bv": 0x200}
    ast = {"functions": [], "structs": [], "enums": [], "typedefs": []}
    result = merge(ast, rva_map)
    assert len(result["functions"]) == 2
    assert all(f["args"] == [] for f in result["functions"])
