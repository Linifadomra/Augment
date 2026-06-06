import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "manifest"))
import extract

def test_assemble_from_text(sample_text):
    m = extract.assemble(sample_text, demangle={"_ZN7daCow_c7ExecuteEv": "daCow_c::Execute()"})
    assert m["version"] == 2
    assert any(f["flat"] == "daCow_c_Execute" for f in m["functions"])
    assert any(s["name"] == "daCow_c" for s in m["structs"])
    assert any(e["name"] == "Action" for e in m["enums"])
    assert any(g["name"] == "g_dComIfG" for g in m["globals"])
    assert any(t["alias"] == "BOOL" for t in m["typedefs"])
    flats = [f["flat"] for f in m["functions"]]
    assert flats == sorted(flats)
