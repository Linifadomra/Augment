from __future__ import annotations
import subprocess
from typing import Dict, List, Optional
import re

_ANON_NS = re.compile(r'\(anonymous namespace\)::')
_STRIP_ARGS = re.compile(r'(?<!operator)\(.*')
_MSVC_CLEANUP = re.compile(r'\b(public:|private:|protected:|__cdecl|__stdcall|__thiscall|__vectorcall|__ptr64)\b')
_BUILTIN_EXCLUSIONS = (
    "struct (unnamed",
    "class (unnamed",
    "union (unnamed",
    "(unnamed struct",
    "(unnamed union",
    "tinystl",
    "zz::",                  # dobby
    "AssemblerCodeBuilder",  # dobby
    "ClearCache",            # dobby
    "ClosureTrampoline",     # dobby
    "CodeGenBase",           # dobby
    "CodeMemBuffer",         # dobby
    "true>>>",
    "_Augment",              # augment
    "augment",               # augment
    "std::",                 # standard lib
    "boost::",               # boost lib
    "__gnu_cxx::",           # gnu specific
    "$_",                    # compiler-generated
    ">::",
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
    s = _MSVC_CLEANUP.sub('', s)
    
    s = s.strip()
    if " " in s and "::" in s:
        parts = s.split()
        for part in reversed(parts):
            if "::" in part:
                s = part
                break

    return s.strip()


def _normalize_for_matching(name: str) -> str:
    return name.replace("::", "").replace("_", "").replace(" ", "").strip()

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


CHUNK_CHAR_LIMIT = 24000


def _chunks_by_length(items, limit):
    chunk = []
    total = 0
    for item in items:
        item_len = len(item) + 1  # +1 for separator/space
        if chunk and total + item_len > limit:
            yield chunk
            chunk = []
            total = 0
        chunk.append(item)
        total += item_len
    if chunk:
        yield chunk


def _demangle_batch(mangled: List[str]) -> Dict[str, str]:
    if not mangled:
        return {}

    def _msvc_demangle_one(name: str) -> str:
        if not name or not name.startswith("?"):
            return name
        try:
            body = name[1:]
            head = body.split('@@', 1)[0]
            parts = head.split('@')
            if not parts:
                return name
            fn = parts[0]
            scopes = [p for p in parts[1:] if p]
            if not scopes:
                return fn
            scopes_rev = list(reversed(scopes))
            return '::'.join(scopes_rev + [fn])
        except Exception:
            return name

    for binary in ["llvm-cxxfilt", "c++filt"]:
        try:
            mapping: Dict[str, str] = {}
            ok = True
            for chunk in _chunks_by_length(mangled, CHUNK_CHAR_LIMIT):
                result = subprocess.run(
                    [binary, *chunk],
                    capture_output=True, text=True, timeout=60,
                )
                lines = result.stdout.splitlines()
                if len(lines) != len(chunk):
                    ok = False
                    break
                for m, out in zip(chunk, lines):
                    if m.startswith("?") and out == m:
                        mapping[m] = _msvc_demangle_one(m)
                    else:
                        mapping[m] = out
            if ok:
                return mapping
        except Exception:
            pass

    mapping: Dict[str, str] = {m: m.lstrip("_") for m in mangled}
    for m in mangled:
        if m.startswith("?"):
            dm = _msvc_demangle_one(m)
            if dm and dm != m:
                mapping[m] = dm
    return mapping


def _apply_flat_names(functions: List[dict], exclude_prefixes: tuple) -> None:
    mangled = [f["mangled"] for f in functions]
    dm = _demangle_batch(mangled)
    to_remove = []
    for i, fn in enumerate(functions):
        dem = dm.get(fn["mangled"], fn["mangled"].lstrip("_"))
        flat = _clean_flat(dem)
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
    consumed_rva_keys: set = set()
    consumed_rva_values: set = set()

    rva_keys = list(rva_map.keys())
    print(f"[_merge_functions] rva_keys count={len(rva_keys)}")
    rva_dm = _demangle_batch(rva_keys)
    print(f"[_merge_functions] rva_dm size={len(rva_dm)}")

    clean_rva_lookup = {}
    for k in rva_keys:
        if rva_map[k] is None:
            continue

        raw_norm = _normalize_for_matching(_clean_flat(k))
        dm_norm = _normalize_for_matching(_clean_flat(rva_dm.get(k, k)))

        clean_rva_lookup[raw_norm] = (k, rva_map[k])
        clean_rva_lookup[dm_norm] = (k, rva_map[k])

    ast_mangled = [fn.get("mangled", "") for fn in ast_fns if fn.get("mangled")]
    print(f"[_merge_functions] ast_mangled count={len(ast_mangled)}")
    ast_dm = _demangle_batch(ast_mangled)
    print(f"[_merge_functions] ast_dm size={len(ast_dm)}")

    for fn in ast_fns:
        if _is_generated_artifact(fn):
            continue
        mangled    = fn.get("mangled", "")
        rva_int    = None
        used_key   = None

        if mangled and mangled in rva_map:
            rva_int = rva_map.get(mangled)
            used_key = mangled

        if rva_int is None and mangled:
            try:
                clean = _normalize_for_matching(_clean_flat(ast_dm.get(mangled, mangled)))
                if clean in clean_rva_lookup:
                    used_key, rva_int = clean_rva_lookup[clean]
            except Exception:
                pass

        detected_self: Optional[str] = None
        if not fn.get("member") and fn.get("args"):
            first_arg = fn["args"][0]
            if first_arg.get("name") == "actor" or first_arg.get("kind") == "ptr":
                base_name = fn.get("flat") or fn.get("mangled") or ""
                m = re.match(r"(?P<prefix>[^_]+)_(?P<method>.+)$", base_name)
                if m:
                    prefix = m.group("prefix")
                    method = m.group("method")
                    for cand in (prefix + "_c", prefix):
                        target_clean = _normalize_for_matching(f"{cand}_{method}")
                        if target_clean in clean_rva_lookup:
                            detected_self = cand
                            if used_key is None:
                                used_key, rva_int = clean_rva_lookup[target_clean]
                            break

        record = dict(fn)
        if detected_self:
            record["member"] = True
            record["self_view"] = detected_self
            args = list(fn.get("args", []))
            if args:
                args = args[1:]
            record["args"] = args

        record["rva"] = _rva_hex(rva_int) if rva_int is not None else None

        if used_key:
            if re.match(r'^(_Z|\?|@)', used_key):
                record["mangled"] = used_key
            elif rva_int is not None:
                for k2, v2 in rva_map.items():
                    if v2 == rva_int and re.match(r'^(_Z|\?|@)', k2):
                        record["mangled"] = k2
                        break

        record["loc"] = (
            record["loc"].replace("\\", "/")
            if isinstance(record.get("loc"), str)
            else record.get("loc")
        )

        out.append(record)

        if used_key:
            consumed_rva_keys.add(used_key)
        if rva_int is not None:
            consumed_rva_values.add(rva_int)

    rva_to_keys: Dict[int, List[str]] = {}
    for k, v in rva_map.items():
        if v is not None:
            rva_to_keys.setdefault(v, []).append(k)

    for rva_int, keys in rva_to_keys.items():
        if rva_int in consumed_rva_values:
            continue
        chosen: Optional[str] = None
        for k in keys:
            if '::' in k and not k.endswith('::'):
                chosen = k
                break
        if not chosen:
            for k in keys:
                if '_c' in k or '::' in k:
                    chosen = k
                    break
        if not chosen:
            chosen = keys[0]
        out.append(_opaque_stub(chosen, rva_int))

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
