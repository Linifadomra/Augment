import pytest
import dwarf

def test_parse_dies_builds_tree(sample_text):
    roots = dwarf.parse_dies(sample_text)
    tags = [d.tag for d in roots]
    assert "DW_TAG_structure_type" in tags
    assert "DW_TAG_subprogram" in tags
    struct = next(d for d in roots if d.tag == "DW_TAG_structure_type")
    assert struct.attr("DW_AT_name") == "daCow_c"
    assert len(struct.children) == 3
    assert struct.children[0].attr("DW_AT_name") == "mProcess"

def test_die_attr_missing_returns_none(sample_text):
    roots = dwarf.parse_dies(sample_text)
    struct = next(d for d in roots if d.tag == "DW_TAG_structure_type")
    assert struct.attr("DW_AT_nonexistent") is None

@pytest.mark.parametrize("t,expected", [
    ("int", ("i32", None)),
    ("unsigned int", ("u32", None)),
    ("float", ("f32", None)),
    ("BOOL", ("i32", None)),
    ("daCph_c *", ("ptr", None)),
    ("char[8]", ("str", 8)),
    ("void (daCow_c::*)()", ("pmf", None)),
])
def test_ffi_kind(t, expected):
    assert dwarf.ffi_kind(t) == expected

def test_pointee_struct():
    assert dwarf.pointee_struct("daCph_c *") == "daCph_c"
    assert dwarf.pointee_struct("int") is None
    assert dwarf.pointee_struct("int *") is None

def test_extract_functions(sample_text):
    roots = dwarf.parse_dies(sample_text)
    fns = dwarf.extract_functions(roots, demangle={
        "_ZN7daCow_c7ExecuteEv": "daCow_c::Execute()",
        "_Z8setStageP7daCph_ci": "setStage(daCph_c*, int)",
    })
    by = {f["flat"]: f for f in fns}
    ex = by["daCow_c_Execute"]
    assert ex["mangled"] == "_ZN7daCow_c7ExecuteEv"
    assert ex["member"] is True
    assert ex["self_view"] == "daCow_c"
    assert ex["rva"] == "0x801234"
    assert ex["loc"] == "d/actor/d_a_cow.cpp:120"
    assert ex["ret"] == "void"
    assert ex["args"] == []
    ss = by["setStage"]
    assert ss["member"] is False
    assert ss["self_view"] is None
    assert ss["loc"] is None
    assert ss["args"] == [
        {"name": "stage", "kind": "ptr", "view": "daCph_c"},
        {"name": "point", "kind": "i32"},
    ]

def test_extract_structs(sample_text):
    roots = dwarf.parse_dies(sample_text)
    structs = dwarf.extract_structs(roots)
    s = next(s for s in structs if s["name"] == "daCow_c")
    assert s["size"] == 0x220
    by = {f["name"]: f for f in s["fields"]}
    assert by["mProcess"] == {"name": "mProcess", "offset": 0x1c, "kind": "i32"}
    assert by["mName"] == {"name": "mName", "offset": 0x40, "kind": "str", "len": 8}
    assert by["mAcch"] == {"name": "mAcch", "offset": 0x80, "kind": "ptr", "view": "daCph_c"}

def test_extract_enums(sample_text):
    roots = dwarf.parse_dies(sample_text)
    enums = dwarf.extract_enums(roots)
    by = {e["name"]: e for e in enums}
    action = by["Action"]
    assert action["owner"] is None
    assert {v["name"]: v["value"] for v in action["values"]} == {"idle": 0, "angry": 3}
    mode = by["daCow_c::Mode"]
    assert mode["owner"] == "daCow_c"
    assert {v["name"]: v["value"] for v in mode["values"]} == {"walk": 1}

def test_extract_globals(sample_text):
    roots = dwarf.parse_dies(sample_text)
    gs = dwarf.extract_globals(roots)
    g = next(g for g in gs if g["name"] == "g_dComIfG")
    assert g["kind"] == "ptr"
    assert g["addr"] == "0x802000"

def test_extract_typedefs(sample_text):
    roots = dwarf.parse_dies(sample_text)
    ts = dwarf.extract_typedefs(roots)
    assert {"alias": "BOOL", "kind": "i32"} in ts
