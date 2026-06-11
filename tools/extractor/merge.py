"""
extractor/merge.py

Join AST records (from walker.py) with RVA maps (from binary backends)
by mangled name.

Three cases:
  both      - AST record wins for shape; RVA filled from binary
  AST only  - symbol present in source but stripped/inlined in binary;
              emitted with rva=None
  RVA only  - symbol in binary but not in parsed source (template
              instantiation, extern "C", LTO remainder, …);
              emitted as opaque with no arg/type info
"""
from __future__ import annotations

from typing import Dict, List, Optional

def merge(
    ast: Dict[str, List[dict]],
    rva_map: Dict[str, int],
) -> Dict[str, List[dict]]:
    """
    Parameters
    ----------
    ast:
        Output of walker.walk(): structs, functions, enums, typedefs.
        Function records carry rva=None; all other shape info is populated.
    rva_map:
        Output of DebugInfoBackend.extract_rvas(): {mangled_name: rva_int}.

    Returns
    -------
    A manifest dict with the same keys as ast, functions enriched with RVAs,
    plus opaque stubs for RVA-only symbols.
    """
    functions   = _merge_functions(ast.get("functions", []), rva_map)
    structs     = sorted(ast.get("structs",   []), key=lambda s: s["name"])
    enums       = sorted(ast.get("enums",     []), key=lambda e: e["name"])
    typedefs    = sorted(ast.get("typedefs",  []), key=lambda t: t["alias"])

    functions.sort(key=lambda f: (f["flat"], f["mangled"]))

    return {
        "version":   2,
        "functions": functions,
        "structs":   structs,
        "enums":     enums,
        "typedefs":  typedefs,
    }

def _rva_hex(rva: int) -> str:
    return f"0x{rva:x}"

def _merge_functions(
    ast_fns: List[dict],
    rva_map: Dict[str, int],
) -> List[dict]:
    out: List[dict] = []
    consumed: set   = set()

    for fn in ast_fns:
        mangled = fn.get("mangled", "")
        rva_int = rva_map.get(mangled)
        record  = dict(fn)
        record["rva"] = _rva_hex(rva_int) if rva_int is not None else None
        out.append(record)
        consumed.add(mangled)

    # RVA-only: in binary but not in AST
    for mangled, rva_int in rva_map.items():
        if mangled in consumed:
            continue
        out.append(_opaque_stub(mangled, rva_int))

    return out

def _opaque_stub(mangled: str, rva_int: int) -> dict:
    """
    Minimal record for a symbol that has an RVA but no AST entry.
    flat is a best-effort human-readable label only.
    """
    return {
        "flat":      _flat_from_mangled(mangled),
        "mangled":   mangled,
        "member":    False,
        "self_view": None,
        "rva":       _rva_hex(rva_int),
        "loc":       None,
        "ret":       "ptr",
        "args":      [],
    }

def _flat_from_mangled(mangled: str) -> str:
    """
    Very cheap label for opaque stubs. Not a demangler, just strips
    leading underscores so the name is readable in logs/manifests.
    """
    s = mangled.lstrip("_")
    return s or mangled
