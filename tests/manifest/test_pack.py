import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "manifest"))
import extract, pack

def test_pack_roundtrip(sample_text, tmp_path):
    m = extract.assemble(sample_text, demangle={
        "_ZN7daCow_c7ExecuteEv": "daCow_c::Execute()",
        "_Z8setStageP7daCph_ci": "setStage(daCph_c*, int)",
    })
    blob = pack.pack(m)
    out = tmp_path / "augment.manifest"
    out.write_bytes(blob)

    r = pack.Reader(out.read_bytes())
    assert r.version == 2
    f = r.lookup_function("daCow_c_Execute")
    assert f["mangled"] == "_ZN7daCow_c7ExecuteEv"
    assert f["member"] is True
    assert f["self_view"] == "daCow_c"
    assert f["rva"] == 0x801234
    ss = r.lookup_function("setStage")
    assert ss["args"] == [
        {"name": "stage", "kind": "ptr", "view": "daCph_c"},
        {"name": "point", "kind": "i32", "view": ""},
    ]
    s = r.lookup_struct("daCow_c")
    assert s["size"] == 0x220
    assert {fl["name"]: fl["offset"] for fl in s["fields"]}["mProcess"] == 0x1c
    e = r.lookup_enum("Action")
    assert {v["name"]: v["value"] for v in e["values"]} == {"idle": 0, "angry": 3}
    assert r.lookup_global("g_dComIfG") == {"kind": "ptr", "addr": 0x802000}
    assert r.lookup_typedef("BOOL") == {"kind": "i32"}
    assert {fl["name"]: fl["len"] for fl in s["fields"]}["mName"] == 8
    assert r.lookup_function("does_not_exist") is None

def test_pack_collision():
    m = {"version": 2,
         "functions": [
             {"flat":"init","mangled":"_ZL4initv","member":False,"self_view":None,"rva":"0x1","loc":"a.cpp:1","ret":"void","args":[]},
             {"flat":"init","mangled":"_ZL4initi","member":False,"self_view":None,"rva":"0x2","loc":"b.cpp:2","ret":"void","args":[{"name":"n","kind":"i32"}]},
         ],
         "structs": [], "enums": [], "globals": [], "typedefs": []}
    r = pack.Reader(pack.pack(m))
    grp = r.lookup_function_group("init")
    assert len(grp) == 2
    assert {f["mangled"] for f in grp} == {"_ZL4initv", "_ZL4initi"}
    assert r.lookup_function("init")["mangled"] in ("_ZL4initv", "_ZL4initi")
