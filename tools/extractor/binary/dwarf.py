"""
extractor/binary/dwarf.py

DWARF backend: shells out to llvm-dwarfdump, parses DIEs inline, and
returns {mangled_name: rva_int} for every subprogram with DW_AT_low_pc.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from typing import Dict

from extractor.binary.interface import DebugInfoBackend

_DWARFDUMP = shutil.which("llvm-dwarfdump") or shutil.which("dwarfdump")

_DIE_RE  = re.compile(r'^(0x[0-9a-fA-F]+):(\s*)(DW_TAG_\w+)')
_ATTR_RE = re.compile(r'^\s+(DW_AT_\w+)\s*\((.*)\)\s*$')

class _Die:
    __slots__ = ("tag", "indent", "attrs", "children")

    def __init__(self, tag: str, indent: int):
        self.tag = tag
        self.indent = indent
        self.attrs: dict = {}
        self.children: list = []

    def attr(self, name: str):
        return self.attrs.get(name)

def _attr_value(raw: str) -> str:
    m = re.search(r'"([^"]*)"', raw)
    return m.group(1) if m else raw.strip()

def _parse_dies(text: str) -> list:
    roots: list = []
    stack: list = []
    cur = None
    for line in text.splitlines():
        m = _DIE_RE.match(line)
        if m:
            indent = len(m.group(2))
            cur = _Die(m.group(3), indent)
            while stack and stack[-1].indent >= indent:
                stack.pop()
            if stack:
                stack[-1].children.append(cur)
            else:
                roots.append(cur)
            stack.append(cur)
            continue
        if cur is not None:
            am = _ATTR_RE.match(line)
            if am:
                cur.attrs[am.group(1)] = _attr_value(am.group(2))
    return roots

class DwarfBackend(DebugInfoBackend):
    name = "dwarf"

    def extract_rvas(self, binary_path: str) -> Dict[str, int]:
        if not _DWARFDUMP:
            sys.exit("dwarf backend: requires llvm-dwarfdump or dwarfdump")

        text = subprocess.run(
            [_DWARFDUMP, "--debug-info", binary_path],
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout

        result: Dict[str, int] = {}

        def visit(die: _Die) -> None:
            if die.tag == "DW_TAG_subprogram":
                mangled = die.attr("DW_AT_linkage_name")
                low_pc  = die.attr("DW_AT_low_pc")
                if mangled and low_pc:
                    rva = int(low_pc, 0)
                    if mangled not in result or rva > result[mangled]:
                        result[mangled] = rva
            for child in die.children:
                visit(child)

        for root in _parse_dies(text):
            visit(root)

        return result
