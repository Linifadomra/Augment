"""
extractor/binary/dwarf.py
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from typing import Dict, Optional

from extractor.binary.interface import DebugInfoBackend
from extractor.utility.dependencies import dwarf_dump

_DIE_RE  = re.compile(r'^(0x[0-9a-fA-F]+):\s*(DW_TAG_\w+)')
_ATTR_RE = re.compile(r'^\s+(DW_AT_\w+)\s*\((.*)\)\s*$')
_QUOTED  = re.compile(r'"([^"]*)"')
_ADDR_RE = re.compile(r'(0x[0-9a-fA-F]+)')


def _attr_value(raw: str) -> str:
    m = _QUOTED.search(raw)
    return m.group(1) if m else raw.strip()


def _parse_addr(raw: str) -> Optional[int]:
    """Extract the leading hex address; returns None for zero (unlinked)."""
    m = _ADDR_RE.search(raw)
    if not m:
        return None
    val = int(m.group(1), 16)
    return val if val != 0 else None


class DwarfBackend(DebugInfoBackend):
    name = "dwarf"

    def extract_rvas(self, binary_path: str) -> Dict[str, int]:
        proc = subprocess.Popen(
            [dwarf_dump, "--debug-info", binary_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
        )

        result: Dict[str, int] = {}

        decl_mangles: Dict[int, str] = {} # offset -> mangled
        pending: list[tuple[int, int]] = [] # (spec_offset, low_pc)

        cur_offset:   Optional[int] = None
        in_subprogram = False
        is_decl       = False
        mangled:      Optional[str] = None
        low_pc:       Optional[int] = None
        spec_offset:  Optional[int] = None

        def _flush() -> None:
            nonlocal mangled, low_pc, spec_offset, is_decl

            if spec_offset is not None and low_pc is not None:
                decl_name = decl_mangles.get(spec_offset)
                if decl_name and decl_name not in result:
                    result[decl_name] = low_pc
                else:
                    pending.append((spec_offset, low_pc))

            elif not is_decl and mangled and low_pc is not None:
                if mangled not in result:
                    result[mangled] = low_pc

            elif is_decl and mangled and cur_offset is not None:
                decl_mangles[cur_offset] = mangled

            mangled = low_pc = spec_offset = None
            is_decl = False

        for line in proc.stdout:
            die_m = _DIE_RE.match(line)
            if die_m:
                if in_subprogram:
                    _flush()
                cur_offset = int(die_m.group(1), 16)
                tag = die_m.group(2)
                in_subprogram = (tag == "DW_TAG_subprogram")
                continue

            if not in_subprogram:
                continue

            attr_m = _ATTR_RE.match(line)
            if not attr_m:
                continue

            attr, raw_val = attr_m.group(1), attr_m.group(2)
            val = _attr_value(raw_val)

            if attr == "DW_AT_linkage_name":
                mangled = val
            elif attr == "DW_AT_name" and mangled is None:
                mangled = val
            elif attr == "DW_AT_low_pc":
                low_pc = _parse_addr(raw_val)
            elif attr == "DW_AT_declaration":
                is_decl = True
            elif attr == "DW_AT_specification":
                spec_offset = _parse_addr(raw_val)

        _flush()

        for spec_off, pc in pending:
            decl_name = decl_mangles.get(spec_off)
            if decl_name and decl_name not in result:
                result[decl_name] = pc

        proc.wait()
        return result