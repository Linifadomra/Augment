"""
extractor/binary/pdb.py
"""
from __future__ import annotations

import glob
import re
import shutil
import subprocess
import sys
from typing import Dict, Optional, Tuple

from extractor.binary.interface import DebugInfoBackend

def _find_pdbutil() -> str | None:
    found = shutil.which("llvm-pdbutil")
    if found:
        return found
    # VS-bundled llvm-pdbutil
    patterns = [
        r"C:\Program Files (x86)\Microsoft Visual Studio\*\*\VC\Tools\Llvm\x64\bin\llvm-pdbutil.EXE",
        r"C:\Program Files\Microsoft Visual Studio\*\*\VC\Tools\Llvm\x64\bin\llvm-pdbutil.EXE",
    ]
    for pattern in patterns:
        matches = glob.glob(pattern)
        if matches:
            return matches[-1]  # take the latest
    return None

_PDBUTIL = _find_pdbutil()

# section header parsing
# Matches:  SECTION HEADER #3
_SEC_NUM_RE = re.compile(r'SECTION HEADER #(\d+)', re.IGNORECASE)
# Matches:  00001000 virtual address
_SEC_VA_RE  = re.compile(r'([0-9a-fA-F]+)\s+virtual address', re.IGNORECASE)

# symbol record parsing
# Matches the record header line, e.g.:
#   32 | S_GPROC32_ID [size = 56] `_ZN3Foo3barEi`
_SYM_REC_RE = re.compile(
    r'^\s*(?:\d+|0x[0-9a-fA-F]+)\s*\|\s*'
    r'(S_[A-Z0-9_]+)'
    r'(?:\s+\[size\s*=\s*\d+\])?'
    r'\s*(.*)'
)
# Matches the addr continuation line, e.g.:
#   addr = 0001:00001080
_ADDR_RE = re.compile(r'addr\s*=\s*([0-9a-fA-F]+)\s*:\s*([0-9a-fA-F]+)', re.IGNORECASE)

_PROC_KINDS = frozenset({
    "S_GPROC32", "S_LPROC32", "S_GPROC32_ID", "S_LPROC32_ID",
    "S_GPROC32_DPC", "S_LPROC32_DPC",
    "S_GPROC32_DPC_ID", "S_LPROC32_DPC_ID",
})

_REC_START_RE = re.compile(r'^\s*(0x[0-9A-Fa-f]+)\s*\|\s*LF_(\w+)\b(.*)')
_NAME_RE      = re.compile(r'`([^`]+)`')
_FIELDLIST_RE = re.compile(r'field list:\s*(0x[0-9A-Fa-f]+|<no type>)')
_SIZEOF_RE    = re.compile(r'sizeof\s+(\d+)')
_MEMBER_RE    = re.compile(r'-\s*LF_MEMBER\s*\[name = `(.+?)`,.*?\boffset = (-?\d+)')
_BCLASS_RE    = re.compile(r'type\s*=\s*(0x[0-9A-Fa-f]+),\s*offset\s*=\s*(\d+)')
_INDEX_RE     = re.compile(r'-\s*LF_INDEX\s+continuation\s*=\s*(0x[0-9A-Fa-f]+)')
_SYM_TYPE_RE  = re.compile(r'\btype\s*=\s*`?(0x[0-9A-Fa-f]+)')
_SIMPLE_TYPE_RE = {
    0x0003: ("void", "void"),
    0x0010: ("i8", "char"),
    0x0011: ("i16", "short"),
    0x0012: ("i32", "long"),
    0x0013: ("i64", "long long"),
    0x0020: ("u8", "unsigned char"),
    0x0021: ("u16", "unsigned short"),
    0x0022: ("u32", "unsigned long"),
    0x0023: ("u64", "unsigned long long"),
    0x0030: ("u8", "bool"),
    0x0040: ("f32", "float"),
    0x0041: ("f64", "double"),
    0x0068: ("i8", "int8_t"),
    0x0069: ("u8", "uint8_t"),
    0x0070: ("i8", "char"),
    0x0071: ("i16", "wchar_t"),
    0x0072: ("i16", "short"),
    0x0073: ("u16", "unsigned short"),
    0x0074: ("i32", "int"),
    0x0075: ("u32", "unsigned int"),
    0x0076: ("i64", "long long"),
    0x0077: ("u64", "unsigned long long"),
    0x0080: ("f32", "float"),
    0x0081: ("f64", "double"),
}

_CLASS_KINDS = frozenset({"CLASS", "STRUCTURE", "UNION"})


def _normalize_type_id(type_id: str) -> str:
    return "0x" + type_id[2:].lower()


def _resolve_fieldlist(fid, fieldlists):
    members: Dict[str, int] = {}
    bases = []
    seen = set()
    while fid and fid not in seen:
        seen.add(fid)
        fl = fieldlists.get(fid)
        if fl is None:
            break
        for n, o in fl["members"].items():
            if n not in members:
                members[n] = o
        bases.extend(fl["bases"])
        fid = fl["cont"]
    return members, bases


def _resolve_layouts(classes, fieldlists, id_to_name, by_name) -> Dict[str, Dict]:
    chosen: Dict[str, Tuple[dict, Dict[str, int], list]] = {}
    for name, ids in by_name.items():
        best = None
        best_count = -1
        for cid in ids:
            c = classes[cid]
            if c["fwdref"] or not c["fieldlist"]:
                continue
            members, bases = _resolve_fieldlist(c["fieldlist"], fieldlists)
            count = len(members) + len(bases)
            if count > best_count:
                best_count = count
                best = (c, members, bases)
        if best is not None:
            chosen[name] = best

    memo: Dict[str, Dict[str, int]] = {}
    visiting: set = set()

    def flatten(name):
        cached = memo.get(name)
        if cached is not None:
            return cached
        entry = chosen.get(name)
        if entry is None or name in visiting:
            return {}
        visiting.add(name)
        _, members, bases = entry
        flat = dict(members)
        for bid, boff in bases:
            bname = id_to_name.get(bid)
            if not bname:
                continue
            for n, o in flatten(bname).items():
                if n not in flat:
                    flat[n] = o + boff
        visiting.discard(name)
        memo[name] = flat
        return flat

    out: Dict[str, Dict] = {}
    for name, (c, _members, _bases) in chosen.items():
        fields = flatten(name)
        if not fields and not c["size"]:
            continue
        out[name] = {"size": c["size"], "fields": fields}
    return out


def _parse_types_stream(lines) -> Dict[str, Dict]:
    classes: Dict[str, dict] = {}
    fieldlists: Dict[str, dict] = {}
    id_to_name: Dict[str, str] = {}
    by_name: Dict[str, list] = {}

    cur_kind = None
    cur = None
    pending_base = False

    for line in lines:
        if '| LF_' in line:
            m = _REC_START_RE.match(line)
            if m:
                cur_id, kind, rest = m.group(1), m.group(2), m.group(3)
                pending_base = False
                if kind in _CLASS_KINDS:
                    nm = _NAME_RE.search(rest)
                    name = nm.group(1) if nm else None
                    cur_kind = "CLASS"
                    cur = {"name": name, "size": None, "fieldlist": None,
                           "fwdref": False}
                    classes[cur_id] = cur
                    if name:
                        id_to_name[cur_id] = name
                        by_name.setdefault(name, []).append(cur_id)
                elif kind == "FIELDLIST":
                    cur_kind = "FIELDLIST"
                    cur = {"members": {}, "bases": [], "cont": None}
                    fieldlists[cur_id] = cur
                else:
                    cur_kind = None
                    cur = None
                continue
        if cur_kind is None:
            continue
        if cur_kind == "FIELDLIST":
            if pending_base:
                pending_base = False
                bm = _BCLASS_RE.search(line)
                if bm:
                    cur["bases"].append((bm.group(1), int(bm.group(2))))
                continue
            if '- LF_' not in line:
                continue
            mm = _MEMBER_RE.search(line)
            if mm:
                name = mm.group(1)
                if name not in cur["members"]:
                    cur["members"][name] = int(mm.group(2))
                continue
            if '- LF_BCLASS' in line:
                pending_base = True
                continue
            im = _INDEX_RE.search(line)
            if im:
                cur["cont"] = im.group(1)
        else:
            if 'field list:' in line:
                fm = _FIELDLIST_RE.search(line)
                if fm and fm.group(1) != '<no type>':
                    cur["fieldlist"] = fm.group(1)
            if 'forward ref' in line:
                cur["fwdref"] = True
            if 'sizeof' in line:
                sm = _SIZEOF_RE.search(line)
                if sm:
                    cur["size"] = int(sm.group(1))

    return _resolve_layouts(classes, fieldlists, id_to_name, by_name)

def _parse_section_headers(text: str) -> Dict[int, int]:
    """Return {section_index: virtual_address_int}."""
    sections: Dict[int, int] = {}
    current: Optional[int] = None
    for line in text.splitlines():
        m = _SEC_NUM_RE.search(line)
        if m:
            current = int(m.group(1))
            continue
        if current is not None:
            m = _SEC_VA_RE.search(line)
            if m:
                sections[current] = int(m.group(1), 16)
    return sections

def _parse_pdbutil_int(s: str) -> int:
    """
    pdbutil prints address fields as either:
      - plain decimal ("17573936")  — section-relative offsets, code sizes
      - hex without 0x prefix ("010C2830", "1000")  — when hex chars are present
      - zero-padded 8-digit hex ("00000100")
      - hex with 0x prefix ("0x1000")  — rare, but handle it
    Detect by presence of a–f; only base-10 chars are ambiguous.
    """
    s = s.strip()
    if s.startswith(("0x", "0X")):
        return int(s, 16)

    if any(c in s for c in "abcdefABCDEF"):
        return int(s, 16)

    if len(s) == 8 and s.startswith("0"):
        return int(s, 16)

    return int(s)

def _resolve_rva(seg_str: str, off_str: str, section_map: Dict[int, int]) -> Optional[int]:
    """Convert a seg:off pair to an integer RVA, or None if unresolvable."""
    try:
        seg = _parse_pdbutil_int(seg_str)
        off = _parse_pdbutil_int(off_str)
    except (ValueError, TypeError):
        return None
    if seg == 0:
        return None
    base = section_map.get(seg)
    if base is None:
        return None
    rva = base + off
    return rva if rva != 0 else None

def _parse_function_rvas(text: str, section_map: Dict[int, int]) -> Dict[str, int]:
    """
    Walk the symbols section of a pdbutil dump and return
    {symbol_name: rva_int} for every supported procedure record with a
    resolvable non-zero address.
    """
    result: Dict[str, int] = {}
    current_name: Optional[str] = None

    for line in text.splitlines():
        m = _SYM_REC_RE.match(line)
        if m:
            kind = m.group(1)
            raw_name = m.group(2)
            name = raw_name.strip(" `\r\n") if raw_name else ""
            if kind in _PROC_KINDS:
                current_name = name if name else None
            else:
                current_name = None
            continue

        if current_name is not None:
            m = _ADDR_RE.search(line)
            if m:
                rva = _resolve_rva(m.group(1), m.group(2), section_map)
                if rva is not None:
                    # best-pick: keep the highest RVA for duplicates
                    if current_name not in result or rva > result[current_name]:
                        result[current_name] = rva
                current_name = None  # addr consumed; don't re-match on later lines

    return result


def _parse_type_records(lines) -> Dict[str, Dict[str, str]]:
    records: Dict[str, Dict[str, str]] = {}
    current_id: Optional[str] = None
    for line in lines:
        match = _REC_START_RE.match(line)
        if match:
            current_id, kind, rest = match.groups()
            current_id = _normalize_type_id(current_id)
            records[current_id] = {"kind": kind, "text": rest}
        elif current_id is not None:
            records[current_id]["text"] += "\n" + line
    return records


def _dump_type_records(binary_path: str, ids: bool = False) -> Dict[str, Dict[str, str]]:
    args = [_PDBUTIL, "dump", "-ids" if ids else "-types", binary_path]
    proc = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="ignore",
    )
    try:
        records = _parse_type_records(proc.stdout)
    finally:
        proc.stdout.close()
        returncode = proc.wait()
    if returncode != 0:
        raise subprocess.CalledProcessError(returncode, args)
    return records


def _record_ref(record: Optional[Dict[str, str]], label: str) -> Optional[str]:
    if record is None:
        return None
    match = re.search(
        rf'\b{re.escape(label)}\s*=\s*`?(0x[0-9A-Fa-f]+)', record["text"]
    )
    return _normalize_type_id(match.group(1)) if match else None


def _record_name(record: Dict[str, str]) -> Optional[str]:
    match = _NAME_RE.search(record["text"])
    return match.group(1) if match else None


def _resolve_codeview_type(
    type_id: str,
    type_records: Dict[str, Dict[str, str]],
    seen: Optional[set[str]] = None,
) -> Dict[str, Optional[str]]:
    """Resolve a CodeView type into the extractor's argument type shape."""
    type_id = _normalize_type_id(type_id)
    seen = set() if seen is None else seen
    if type_id in seen:
        return {"kind": "ptr", "name": None, "view": None}
    seen.add(type_id)

    try:
        numeric_id = int(type_id, 16)
    except ValueError:
        return {"kind": "ptr", "name": None, "view": None}

    simple_id = numeric_id & 0xFF
    pointer_mode = numeric_id & 0xF00
    if numeric_id < 0x1000 and pointer_mode and simple_id in _SIMPLE_TYPE_RE:
        primitive_kind, primitive_name = _SIMPLE_TYPE_RE[simple_id]
        view = primitive_name if primitive_name != "void" else None
        return {"kind": "ptr", "name": primitive_name, "view": view}
    primitive = _SIMPLE_TYPE_RE.get(numeric_id)
    if primitive:
        return {"kind": primitive[0], "name": primitive[1], "view": None}

    record = type_records.get(type_id)
    if record is None:
        return {"kind": "ptr", "name": None, "view": None}

    kind = record["kind"]
    if kind == "POINTER":
        referent = _record_ref(record, "referent")
        if referent:
            pointee = _resolve_codeview_type(referent, type_records, seen)
            name = pointee.get("name")
            return {
                "kind": "ptr",
                "name": name,
                "view": name if name and name != "void" else None,
            }
    elif kind in {"MODIFIER", "ALIAS"}:
        target = _record_ref(
            record,
            "modified type" if kind == "MODIFIER" else "underlying type",
        )
        target = target or (_record_ref(record, "type") if kind == "ALIAS" else None)
        if target:
            return _resolve_codeview_type(target, type_records, seen)
    elif kind in {"CLASS", "STRUCTURE", "UNION"}:
        name = _record_name(record)
        if name:
            return {"kind": f"struct:{name}", "name": name, "view": name}
    elif kind == "ENUM":
        target = _record_ref(record, "underlying type")
        if target:
            return _resolve_codeview_type(target, type_records, seen)

    return {"kind": "ptr", "name": None, "view": None}


def _parse_arglist(record: Optional[Dict[str, str]]) -> list[str]:
    if record is None or record["kind"] != "ARGLIST":
        return []
    args = []
    for line in record["text"].splitlines():
        match = re.match(r'\s*(0x[0-9A-Fa-f]+)\s*:', line)
        if match:
            args.append(_normalize_type_id(match.group(1)))
    return args


def _resolve_procedure(
    type_id: str,
    type_records: Dict[str, Dict[str, str]],
    id_records: Dict[str, Dict[str, str]],
) -> Optional[Dict]:
    type_id = _normalize_type_id(type_id)
    seen: set[str] = set()
    is_member_id = False
    class_id = None
    while type_id not in seen:
        seen.add(type_id)
        record = type_records.get(type_id)
        if record is not None and record["kind"] in {"PROCEDURE", "MFUNCTION"}:
            break
        id_record = id_records.get(type_id)
        if id_record is None or id_record["kind"] not in {"FUNC_ID", "MFUNC_ID"}:
            return None
        if id_record["kind"] == "MFUNC_ID":
            is_member_id = True
            class_id = _record_ref(id_record, "class type")
        type_id = _record_ref(id_record, "function type") or ""
        if not type_id:
            return None
    else:
        return None

    record = type_records.get(type_id)
    if record is None or record["kind"] not in {"PROCEDURE", "MFUNCTION"}:
        return None

    return_id = _record_ref(record, "return type")
    arglist_id = _record_ref(record, "param list")
    if return_id is None:
        return None

    args = []
    for index, arg_type_id in enumerate(
        _parse_arglist(type_records.get(arglist_id or ""))
    ):
        arg_type = _resolve_codeview_type(arg_type_id, type_records)
        arg = {"name": f"arg{index}", "kind": arg_type["kind"]}
        if arg_type["view"]:
            arg["view"] = arg_type["view"]
        args.append(arg)

    return_type = _resolve_codeview_type(return_id, type_records)
    ret = return_type["kind"]
    if ret == "ptr" and return_type["name"]:
        ret = f'{return_type["name"]}*'

    member = False
    self_view = None
    if record["kind"] == "MFUNCTION" or is_member_id:
        class_id = class_id or _record_ref(record, "class type")
        this_id = _record_ref(record, "this type")
        class_type = _resolve_codeview_type(class_id, type_records) if class_id else None
        class_name = class_type.get("name") if class_type else None
        if is_member_id and class_name:
            member = True
            self_view = class_name
        elif class_name and this_id:
            this_type = _resolve_codeview_type(this_id, type_records)
            if this_type.get("name") == class_name:
                member = True
                self_view = class_name

    return {
        "ret": ret,
        "args": args,
        "member": member,
        "self_view": self_view,
    }


def _parse_function_signatures(
    symbol_text: str,
    section_map: Dict[int, int],
    type_records: Dict[str, Dict[str, str]],
    id_records: Optional[Dict[str, Dict[str, str]]] = None,
) -> Dict[str, Dict]:
    """Return the selected signature for each symbol name with its resolved RVA."""
    id_records = id_records or {}
    result: Dict[str, Dict] = {}
    current: Optional[Dict[str, str]] = None

    def save() -> None:
        if not current or not current.get("name") or not current.get("type"):
            return
        rva = current.get("rva")
        signature = _resolve_procedure(current["type"], type_records, id_records)
        if rva is None or signature is None:
            return
        entry = {**signature, "rva": rva}
        name = current["name"]
        if name not in result or rva > result[name]["rva"]:
            result[name] = entry

    for line in symbol_text.splitlines():
        match = _SYM_REC_RE.match(line)
        if match:
            save()
            current = None
            if match.group(1) in _PROC_KINDS:
                raw_name = match.group(2)
                name = raw_name.strip(" `\r\n") if raw_name else ""
                if name:
                    current = {"name": name}
            continue
        if current is None:
            continue
        type_match = _SYM_TYPE_RE.search(line)
        if type_match:
            current["type"] = _normalize_type_id(type_match.group(1))
        addr_match = _ADDR_RE.search(line)
        if addr_match:
            rva = _resolve_rva(addr_match.group(1), addr_match.group(2), section_map)
            if rva is not None:
                current["rva"] = rva
    save()
    return result

class PdbBackend(DebugInfoBackend):
    name = "pdb"

    def extract_rvas(self, binary_path: str) -> Dict[str, int]:
        if not _PDBUTIL:
            sys.exit(
                "pdb backend: llvm-pdbutil not found on PATH.\n"
                "  Install LLVM and add it to PATH, or use the VS-bundled version:\n"
                "  C:\\Program Files (x86)\\Microsoft Visual Studio\\<ver>\\<edition>"
                "\\VC\\Tools\\Llvm\\x64\\bin\\"
            )

        result = subprocess.run(
            [_PDBUTIL, "dump", "-symbols", "-section-headers", binary_path],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            check=True,
        )

        text = result.stdout
        section_map = _parse_section_headers(text)
        return _parse_function_rvas(text, section_map)

    def extract_function_signatures(self, binary_path: str) -> Dict[str, Dict]:
        if not _PDBUTIL:
            sys.exit(
                "pdb backend: llvm-pdbutil not found on PATH; "
                "cannot extract PDB function signatures."
            )

        symbols = subprocess.run(
            [_PDBUTIL, "dump", "-symbols", "-section-headers", binary_path],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            check=True,
        ).stdout
        section_map = _parse_section_headers(symbols)
        if not any(
            re.search(r'\|\s*S_[GL]PROC32(?:_DPC)?(?:_ID)?\b', line)
            for line in symbols.splitlines()
        ):
            return {}

        type_records = _dump_type_records(binary_path)

        has_id_symbols = any(
            re.search(r'\|\s*S_[GL]PROC32(?:_DPC)?_ID\b', line)
            for line in symbols.splitlines()
        )
        id_records = {}
        if has_id_symbols:
            id_records = _dump_type_records(binary_path, ids=True)

        return _parse_function_signatures(
            symbols, section_map, type_records, id_records
        )

    def image_identity(self, binary_path: str) -> Dict[str, int] | None:
        if not _PDBUTIL:
            return None
        result = subprocess.run(
            [_PDBUTIL, "dump", "--summary", binary_path],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
        if result.returncode != 0:
            return None
        guid_m = re.search(r'GUID:\s*\{([0-9A-Fa-f-]+)\}', result.stdout)
        age_m = re.search(r'Age:\s*(\d+)', result.stdout)
        if not guid_m or not age_m:
            return None
        dashless = guid_m.group(1).replace("-", "")
        if len(dashless) != 32:
            return None
        return {
            "guid_lo": int(dashless[:16], 16),
            "guid_hi": int(dashless[16:], 16),
            "age": int(age_m.group(1)),
        }

    def extract_struct_layouts(self, binary_path: str) -> Dict[str, Dict]:
        if not _PDBUTIL:
            return {}
        proc = subprocess.Popen(
            [_PDBUTIL, "dump", "-types", binary_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
        try:
            layouts = _parse_types_stream(proc.stdout)
        finally:
            proc.stdout.close()
            proc.wait()
        return layouts
