"""
extractor/tests/test_model.py

Verify that every record type round-trips through
to_dict / from_dict without data loss, and that the dict keys produced
by to_dict exactly match what pack.py expects.

Run with:  python -m pytest extractor/tests/test_model.py -v
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from extractor.model import (
    Arg, Field, EnumValue,
    Function, Struct, Enum, Global, Typedef,
    Manifest, MANIFEST_VERSION,
)

FUNC_FULL = {
    "flat":      "MyClass_doThing",
    "mangled":   "_ZN7MyClass7doThingEiv",
    "member":    True,
    "self_view": "MyClass",
    "rva":       "0x1a2b3c",
    "loc":       "src/myclass.cpp:42",
    "ret":       "i32",
    "args": [
        {"name": "count", "kind": "i32"},
        {"name": "data",  "kind": "ptr", "view": "Buffer"},
    ],
}

FUNC_MINIMAL = {
    "flat":    "freeFunc",
    "mangled": "_Z8freeFuncv",
    "member":  False,
    "ret":     "void",
    "args":    [],
}

STRUCT_FULL = {
    "name": "Vec3",
    "size": 12,
    "fields": [
        {"name": "x", "offset": 0, "kind": "f32"},
        {"name": "y", "offset": 4, "kind": "f32"},
        {"name": "z", "offset": 8, "kind": "f32"},
    ],
}

STRUCT_WITH_OPTIONALS = {
    "name": "Packet",
    "size": 32,
    "fields": [
        {"name": "tag",  "offset": 0,  "kind": "str", "len": 8},
        {"name": "next", "offset": 8,  "kind": "ptr", "view": "Packet"},
        {"name": "id",   "offset": 16, "kind": "u32"},
    ],
}

ENUM_OWNED = {
    "name":   "State::Kind",
    "owner":  "State",
    "values": [
        {"name": "Idle",    "value": 0},
        {"name": "Running", "value": 1},
        {"name": "Dead",    "value": 2},
    ],
}

ENUM_FREE = {
    "name":   "Color",
    "values": [{"name": "Red", "value": 0}],
    # owner absent
}

GLOBAL_FULL    = {"name": "g_counter", "kind": "i32",  "addr": "0xdeadbeef"}
GLOBAL_MINIMAL = {"name": "g_opaque",  "kind": "ptr"}   # addr absent

TYPEDEF = {"alias": "Handle", "kind": "u32"}

MANIFEST_DICT = {
    "version":   MANIFEST_VERSION,
    "functions": [FUNC_FULL, FUNC_MINIMAL],
    "structs":   [STRUCT_FULL, STRUCT_WITH_OPTIONALS],
    "enums":     [ENUM_OWNED, ENUM_FREE],
    "globals":   [GLOBAL_FULL, GLOBAL_MINIMAL],
    "typedefs":  [TYPEDEF],
}

def roundtrip(cls, d):
    """from_dict then to_dict must reproduce d exactly (modulo absent optionals)."""
    obj = cls.from_dict(d)
    return obj.to_dict()

def normalise(d, optional_keys):
    """Fill absent optional keys with None so equality checks are symmetric."""
    out = dict(d)
    for k in optional_keys:
        out.setdefault(k, None)
    return out

class TestArg:
    def test_roundtrip_full(self):
        d = {"name": "buf", "kind": "ptr", "view": "Buffer"}
        assert roundtrip(Arg, d) == d

    def test_roundtrip_no_view(self):
        d = {"name": "n", "kind": "i32"}
        result = roundtrip(Arg, d)
        assert result["kind"] == "i32"
        assert result.get("view") is None

    def test_none_name(self):
        d = {"name": None, "kind": "u8"}
        obj = Arg.from_dict(d)
        assert obj.name is None
        assert obj.to_dict()["name"] is None

class TestField:
    def test_roundtrip_primitive(self):
        d = {"name": "x", "offset": 0, "kind": "f32"}
        assert roundtrip(Field, d) == d

    def test_roundtrip_str_field(self):
        d = {"name": "tag", "offset": 4, "kind": "str", "len": 16}
        assert roundtrip(Field, d) == d

    def test_roundtrip_ptr_with_view(self):
        d = {"name": "next", "offset": 8, "kind": "ptr", "view": "Node"}
        assert roundtrip(Field, d) == d

    def test_optional_fields_absent(self):
        d = {"name": "id", "offset": 0, "kind": "u32"}
        obj = Field.from_dict(d)
        assert obj.len is None
        assert obj.view is None
        result = obj.to_dict()
        assert "len" not in result
        assert "view" not in result

class TestFunction:
    def test_roundtrip_full(self):
        obj = Function.from_dict(FUNC_FULL)
        result = obj.to_dict()
        assert result["flat"]      == FUNC_FULL["flat"]
        assert result["mangled"]   == FUNC_FULL["mangled"]
        assert result["member"]    == FUNC_FULL["member"]
        assert result["self_view"] == FUNC_FULL["self_view"]
        assert result["rva"]       == FUNC_FULL["rva"]
        assert result["loc"]       == FUNC_FULL["loc"]
        assert result["ret"]       == FUNC_FULL["ret"]
        assert len(result["args"]) == 2
        assert result["args"][1]["view"] == "Buffer"

    def test_roundtrip_minimal_optionals_are_none(self):
        obj = Function.from_dict(FUNC_MINIMAL)
        result = obj.to_dict()
        assert result["self_view"] is None
        assert result["rva"]       is None
        assert result["loc"]       is None
        assert result["args"]      == []

    def test_required_keys_present(self):
        """pack.py accesses these keys unconditionally."""
        required = {"flat", "mangled", "member", "ret", "args",
                    "self_view", "rva", "loc"}
        result = Function.from_dict(FUNC_FULL).to_dict()
        assert required.issubset(result.keys())

class TestStruct:
    def test_roundtrip_simple(self):
        obj = Struct.from_dict(STRUCT_FULL)
        assert obj.to_dict() == STRUCT_FULL

    def test_roundtrip_with_optionals(self):
        obj = Struct.from_dict(STRUCT_WITH_OPTIONALS)
        result = obj.to_dict()
        assert result["fields"][0]["len"]  == 8
        assert result["fields"][1]["view"] == "Packet"
        assert "len"  not in result["fields"][2]
        assert "view" not in result["fields"][2]

class TestEnum:
    def test_roundtrip_owned(self):
        obj = Enum.from_dict(ENUM_OWNED)
        result = obj.to_dict()
        assert result["name"]  == "State::Kind"
        assert result["owner"] == "State"
        assert len(result["values"]) == 3

    def test_roundtrip_free_owner_none(self):
        obj = Enum.from_dict(ENUM_FREE)
        result = obj.to_dict()
        assert result["owner"] is None

    def test_negative_enum_value(self):
        d = {"name": "Err", "values": [{"name": "Invalid", "value": -1}]}
        obj = Enum.from_dict(d)
        assert obj.values[0].value == -1

class TestGlobal:
    def test_roundtrip_with_addr(self):
        assert roundtrip(Global, GLOBAL_FULL) == GLOBAL_FULL

    def test_roundtrip_no_addr(self):
        obj = Global.from_dict(GLOBAL_MINIMAL)
        assert obj.addr is None
        assert obj.to_dict()["addr"] is None

class TestTypedef:
    def test_roundtrip(self):
        assert roundtrip(Typedef, TYPEDEF) == TYPEDEF

class TestManifest:
    def test_roundtrip_full(self):
        m = Manifest.from_dict(MANIFEST_DICT)
        result = m.to_dict()
        assert result["version"]        == MANIFEST_VERSION
        assert len(result["functions"]) == 2
        assert len(result["structs"])   == 2
        assert len(result["enums"])     == 2
        assert len(result["globals"])   == 2
        assert len(result["typedefs"])  == 1

    def test_empty_manifest(self):
        m = Manifest()
        d = m.to_dict()
        for key in ("functions", "structs", "enums", "globals", "typedefs"):
            assert d[key] == []
        assert d["version"] == MANIFEST_VERSION

    def test_version_preserved(self):
        d = dict(MANIFEST_DICT, version=99)
        assert Manifest.from_dict(d).version == 99

    def test_top_level_keys_match_pack(self):
        """pack.py iterates these exact keys; they must all be present."""
        pack_keys = {"version", "functions", "structs", "enums", "globals", "typedefs"}
        assert pack_keys.issubset(Manifest().to_dict().keys())