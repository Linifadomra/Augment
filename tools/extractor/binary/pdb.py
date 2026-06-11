"""
extractor/binary/pdb.py
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from typing import Dict, Optional, Tuple

from extractor.binary.interface import DebugInfoBackend
from extractor.utility.dependencies import pdbutil

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
    r'(?:\s+`([^`]+)`)?'
)
# Matches the addr continuation line, e.g.:
#   addr = 0001:00001080
_ADDR_RE = re.compile(r'addr\s*=\s*([0-9a-fA-F]+)\s*:\s*([0-9a-fA-F]+)', re.IGNORECASE)

_PROC_KINDS = frozenset({"S_GPROC32", "S_LPROC32", "S_GPROC32_ID", "S_LPROC32_ID"})

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
            kind, name = m.group(1), m.group(2) or ""
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
        if not pdbutil:
            sys.exit(
                "pdb backend: llvm-pdbutil not found on PATH.\n"
                "  Install LLVM and add it to PATH, or use the VS-bundled version:\n"
                "  C:\\Program Files (x86)\\Microsoft Visual Studio\\<ver>\\<edition>"
                "\\VC\\Tools\\Llvm\\x64\\bin\\"
            )

        proc = subprocess.Popen(
            [pdbutil, "dump", "-symbols", "-section-headers", binary_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )

        section_map: Dict[int, int] = {}
        current_sec: Optional[int] = None
        current_name: Optional[str] = None
        result: Dict[str, int] = {}

        for line in proc.stdout:
            # --- section header parsing ---
            m = _SEC_NUM_RE.search(line)
            if m:
                current_sec = int(m.group(1))
                continue

            if current_sec is not None:
                m = _SEC_VA_RE.search(line)
                if m:
                    section_map[current_sec] = int(m.group(1), 16)
                continue

            # --- symbol parsing ---
            m = _SYM_REC_RE.match(line)
            if m:
                kind, name = m.group(1), m.group(2) or ""
                current_name = name if (kind in _PROC_KINDS and name) else None
                continue

            if current_name is not None:
                m = _ADDR_RE.search(line)
                if m:
                    rva = _resolve_rva(m.group(1), m.group(2), section_map)
                    if rva is not None and current_name not in result:
                        result[current_name] = rva
                    current_name = None

        proc.wait()
        return result
