from __future__ import annotations
import subprocess
from typing import Dict, List, Optional
import re

_ANON_NS = re.compile(r'\(anonymous namespace\)::')
_STRIP_ARGS = re.compile(r'(?<!operator)\(.*')
_MSVC_CLEANUP = re.compile(r'\b(public:|private:|protected:|__cdecl|__stdcall|__thiscall|__vectorcall|__ptr64)\b')


def _is_generated_artifact(fn: dict) -> bool:
    loc = fn.get("loc") or ""
    sv  = fn.get("self_view") or ""
    return "augment_generated" in loc or "_AugmentPtrReg_" in sv


def _is_cold_block(mangled: str) -> bool:
    return ".cold." in (mangled or "")


def _is_mangled(name: str) -> bool:
    return bool(re.match(r'^_?(_Z|\?|@)', name or ""))


_BAD_PTR_VIEWS = frozenset({"int", "i32", "u32", "void"})


def _parse_itanium_param_segment(s: str) -> tuple[Optional[str], str]:
    if not s:
        return None, s
    c = s[0]
    if c == "P":
        s = s[1:]
        while s and s[0] in "rV":
            s = s[1:]
        m = re.match(r"^(\d+)(.+)", s)
        if not m:
            return None, ""
        n = int(m.group(1))
        return m.group(2)[:n], m.group(2)[n:]
    if c in "iuxcsbv":
        return None, s[1:]
    m = re.match(r"^(\d+)(.+)", s)
    if m:
        n = int(m.group(1))
        return None, m.group(2)[n:]
    return None, s[1:]


def _itanium_param_ptr_views(mangled: str) -> List[str]:
    s = (mangled or "").lstrip("_")
    if not s.startswith("Z"):
        return []
    s = s[1:]
    if s and s[0] in "LGK":
        s = s[1:]
    m = re.match(r"^(\d+)(.+)", s)
    if not m:
        return []
    n = int(m.group(1))
    s = m.group(2)[n:]
    views: List[str] = []
    while s:
        view, s = _parse_itanium_param_segment(s)
        if view:
            views.append(view)
    return views


def _fix_arg_views_from_mangled(record: dict) -> None:
    ptr_views = _itanium_param_ptr_views(record.get("mangled") or "")
    if not ptr_views:
        return
    pi = 0
    for arg in record.get("args") or []:
        if arg.get("kind") != "ptr":
            continue
        view = (arg.get("view") or "").strip()
        if pi < len(ptr_views) and (not view or view in _BAD_PTR_VIEWS):
            arg["view"] = ptr_views[pi]
        pi += 1


def _is_excluded(flat: str, exclude_prefixes: tuple, exclude_substrs: tuple) -> bool:
    if any(flat.startswith(p) for p in exclude_prefixes):
        return True
    if any(s in flat for s in exclude_substrs):
        return True
    return False


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
    exclude_substrs: tuple[str, ...] = (),
) -> Dict[str, List[dict]]:
    rva_keys = list(rva_map.keys())
    ast_fns = ast.get("functions", [])
    ast_mangled = [fn.get("mangled", "") for fn in ast_fns if fn.get("mangled")]

    all_mangled_strings = list(set(rva_keys + ast_mangled))
    global_dm_cache = _demangle_batch(all_mangled_strings)

    functions = _merge_functions(ast_fns, rva_map, global_dm_cache,
                                 exclude_prefixes, exclude_substrs)
    _apply_flat_names(functions, global_dm_cache, exclude_prefixes, exclude_substrs)

    structs   = sorted(ast.get("structs",   []), key=lambda s: s["name"])
    enums     = sorted(ast.get("enums",     []), key=lambda e: e["name"])
    typedefs  = sorted(ast.get("typedefs",  []), key=lambda t: t["alias"])
    functions.sort(key=lambda f: (f.get("flat", ""), f["mangled"]))

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


def _apply_flat_names(functions: List[dict], dm_cache: Dict[str, str],
                      exclude_prefixes: tuple, exclude_substrs: tuple) -> None:
    to_remove = []
    for i, fn in enumerate(functions):
        dem = dm_cache.get(fn["mangled"], fn["mangled"].lstrip("_"))
        flat = _clean_flat(dem)
        if _is_excluded(flat, exclude_prefixes, exclude_substrs):
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
    dm_cache: Dict[str, str],
    exclude_prefixes: tuple,
    exclude_substrs: tuple,
) -> List[dict]:
    out: List[dict] = []
    consumed_rva_keys: set = set()
    consumed_rva_values: set = set()

    mangled_rva_lookup: Dict[int, str] = {}
    for k, v in rva_map.items():
        if v is not None and _is_mangled(k):
            if v not in mangled_rva_lookup:
                mangled_rva_lookup[v] = k

    clean_rva_lookup: Dict[str, List[tuple[str, int]]] = {}
    for k, v in rva_map.items():
        if v is None:
            continue
        try:
            raw_norm = _normalize_for_matching(_clean_flat(k))
            dm_norm = _normalize_for_matching(_clean_flat(dm_cache.get(k, k)))

            entry = (k, v)
            clean_rva_lookup.setdefault(raw_norm, []).append(entry)
            if dm_norm != raw_norm:
                clean_rva_lookup.setdefault(dm_norm, []).append(entry)
        except Exception:
            pass

    for fn in ast_fns:
        if _is_generated_artifact(fn):
            continue
        if _is_cold_block(fn.get("mangled", "")):
            continue
        mangled    = fn.get("mangled", "")
        rva_int    = None
        used_key   = None

        if mangled and mangled in rva_map:
            rva_int = rva_map.get(mangled)
            used_key = mangled

        if rva_int is None and mangled:
            try:
                clean = _normalize_for_matching(_clean_flat(dm_cache.get(mangled, mangled)))
                if clean in clean_rva_lookup:
                    used_key, rva_int = clean_rva_lookup[clean][0]
            except Exception:
                pass

        detected_self: Optional[str] = None
        try:
            if not fn.get("member") and fn.get("args"):
                first_arg = fn["args"][0]
                if first_arg.get("kind") == "ptr":
                    base_name = fn.get("flat") or mangled or ""
                    m = re.match(r"(?P<prefix>[^_]+)_(?P<method>.+)$", base_name)
                    if m:
                        prefix = m.group("prefix")
                        method = m.group("method")
                        for cand in (f"{prefix}_c",):
                            target_clean = _normalize_for_matching(f"{cand}_{method}")
                            if target_clean in clean_rva_lookup:
                                detected_self = cand
                                if rva_int is None:
                                    used_key, rva_int = clean_rva_lookup[target_clean][0]
                                break
        except Exception:
            pass

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
            if _is_mangled(used_key):
                record["mangled"] = used_key
            elif rva_int is not None:
                if rva_int in mangled_rva_lookup:
                    record["mangled"] = mangled_rva_lookup[rva_int]

        if isinstance(record.get("loc"), str):
            record["loc"] = record["loc"].replace("\\", "/")

        _fix_arg_views_from_mangled(record)
        out.append(record)

        if used_key:
            consumed_rva_keys.add(used_key)
        if rva_int is not None:
            consumed_rva_values.add(rva_int)

    try:
        rva_to_keys: Dict[int, List[str]] = {}
        for k, v in rva_map.items():
            if v is not None:
                rva_to_keys.setdefault(v, []).append(k)

        for rva_int, keys in rva_to_keys.items():
            if rva_int in consumed_rva_values:
                continue
            chosen: Optional[str] = None
            for k in keys:
                if _is_cold_block(k):
                    continue
                if '::' in k and not k.endswith('::'):
                    chosen = k
                    break
            if not chosen:
                for k in keys:
                    if _is_cold_block(k):
                        continue
                    if '_c' in k or '::' in k:
                        chosen = k
                        break
            if not chosen:
                for k in keys:
                    if not _is_cold_block(k):
                        chosen = k
                        break
            if not chosen:
                continue
            out.append(_opaque_stub(chosen, rva_int))
    except Exception:
        pass

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
