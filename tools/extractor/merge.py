from __future__ import annotations
import subprocess
from typing import Dict, List, Optional
import re

_ANON_NS = re.compile(r'\(anonymous namespace\)::')
_STRIP_ARGS = re.compile(r'(?<!operator)\(.*')
_BUILTIN_EXCLUSIONS = (
    "struct (unnamed",
    "class (unnamed",
    "union (unnamed",
    "zz::",                  # dobby
    "AssemblerCodeBuilder",  # dobby
    "augment",               # augment
    "std::",                 # standard lib
    "boost::",               # boost lib
    "__gnu_cxx::",           # gnu specific
    "__cxxabiv",
    "vtable for ",
    "typeinfo for ",
    "typeinfo name for ",
    "construction vtable for ",
    "VTT for ",
    "non-virtual thunk to ",
    "virtual thunk to ",
    "covariant return thunk to ",
)


def _is_generated_artifact(fn: dict) -> bool:
    loc = fn.get("loc") or ""
    sv  = fn.get("self_view") or ""
    return "augment_generated" in loc or "_AugmentPtrReg_" in sv


def _is_excluded(flat: str, extra_prefixes: tuple) -> bool:
    return any(p in flat for p in _BUILTIN_EXCLUSIONS + extra_prefixes)
    

def _clean_flat(demangled: str) -> str:
    s = _ANON_NS.sub('', demangled)
    s = _STRIP_ARGS.sub('', s)
    return s.strip()


def merge(
    ast: Dict[str, List[dict]],
    rva_map: Dict[str, int],
    exclude_prefixes: tuple[str, ...] = (),
) -> Dict[str, List[dict]]:
    functions = _merge_functions(ast.get("functions", []), rva_map, exclude_prefixes)
    _apply_flat_names(functions, exclude_prefixes)

    structs   = sorted(ast.get("structs",   []), key=lambda s: s["name"])
    enums     = sorted(ast.get("enums",     []), key=lambda e: e["name"])
    typedefs  = sorted(ast.get("typedefs",  []), key=lambda t: t["alias"])
    functions.sort(key=lambda f: (f["flat"], f["mangled"]))
    return {
        "version":   2,
        "functions": functions,
        "structs":   structs,
        "enums":     enums,
        "typedefs":  typedefs,
    }


def _demangle_batch(mangled: List[str]) -> Dict[str, str]:
    if not mangled:
        return {}
    try:
        result = subprocess.run(
            ["c++filt", *mangled],
            capture_output=True, text=True, timeout=30,
        )
        lines = result.stdout.splitlines()
        if len(lines) == len(mangled):
            return dict(zip(mangled, lines))
    except Exception:
        pass
    return {m: m.lstrip("_") for m in mangled}


def _apply_flat_names(functions: List[dict], exclude_prefixes: tuple) -> None:
    mangled = [f["mangled"] for f in functions]
    dm = _demangle_batch(mangled)
    to_remove = []
    for i, fn in enumerate(functions):
        flat = _clean_flat(dm.get(fn["mangled"], fn["mangled"].lstrip("_")))
        if _is_excluded(flat, exclude_prefixes):
            to_remove.append(i)
        else:
            fn["flat"] = flat
    for i in reversed(to_remove):
        functions.pop(i)


def _rva_hex(rva: int) -> str:
    return f"0x{rva:x}"


def _merge_functions(
    ast_fns: List[dict],
    rva_map: Dict[str, int],
    exclude_prefixes: tuple,
) -> List[dict]:
    out: List[dict] = []
    consumed: set   = set()
    for fn in ast_fns:
        if _is_generated_artifact(fn):
            continue
        mangled    = fn.get("mangled", "")
        rva_int    = rva_map.get(mangled)
        record     = dict(fn)
        record["rva"] = _rva_hex(rva_int) if rva_int is not None else None
        out.append(record)
        consumed.add(mangled)
    for mangled, rva_int in rva_map.items():
        if mangled in consumed:
            continue
        out.append(_opaque_stub(mangled, rva_int))
    return out


def _opaque_stub(mangled: str, rva_int: int) -> dict:
    return {
        "flat":      mangled,
        "mangled":   mangled,
        "member":    False,
        "self_view": None,
        "rva":       _rva_hex(rva_int),
        "loc":       None,
        "ret":       "ptr",
        "args":      [],
    }