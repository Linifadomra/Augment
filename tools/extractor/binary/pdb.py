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

_PROC_KINDS = frozenset({"S_GPROC32", "S_LPROC32", "S_GPROC32_ID", "S_LPROC32_ID"})

_REC_START_RE = re.compile(r'^\s*(0x[0-9A-Fa-f]+)\s*\|\s*LF_(\w+)\b(.*)')
_NAME_RE      = re.compile(r'`([^`]+)`')
_FIELDLIST_RE = re.compile(r'field list:\s*(0x[0-9A-Fa-f]+|<no type>)')
_SIZEOF_RE    = re.compile(r'sizeof\s+(\d+)')
_MEMBER_RE    = re.compile(r'-\s*LF_MEMBER\s*\[name = `(.+?)`,.*?\boffset = (-?\d+)')
_BCLASS_RE    = re.compile(r'type\s*=\s*(0x[0-9A-Fa-f]+),\s*offset\s*=\s*(\d+)')
_INDEX_RE     = re.compile(r'-\s*LF_INDEX\s+continuation\s*=\s*(0x[0-9A-Fa-f]+)')

_CLASS_KINDS = frozenset({"CLASS", "STRUCTURE", "UNION"})


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
      - hex with 0x prefix ("0x1000")  — rare, but handle it
    Detect by presence of a–f; only base-10 chars are ambiguous.
    """
    s = s.strip()
    if s.startswith(("0x", "0X")):
        return int(s, 16)

    if any(c in s for c in "abcdefABCDEF"):
        return int(s, 16)

    return int(s)

def _resolve_rva(seg_str: str, off_str: str, section_map: Dict[int, int]) -> Optional[int]:
    """Convert a seg:off pair to an integer RVA, or None if unresolvable."""
    try:
        seg = int(seg_str, 16)
        off = int(off_str, 16)
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
    {mangled_name: rva_int} for every S_GPROC32 / S_LPROC32 record
    that has a resolvable non-zero address.
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
