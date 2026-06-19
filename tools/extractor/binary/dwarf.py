"""
extractor/binary/dwarf.py
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from typing import Dict, Iterator, Optional, TextIO, Union

from extractor.binary.interface import DebugInfoBackend

_DWARFDUMP = shutil.which("llvm-dwarfdump") or shutil.which("dwarfdump")

_DIE_RE  = re.compile(r'^(0x[0-9a-fA-F]+):\s*(DW_TAG_\w+)')
_ATTR_RE = re.compile(r'^\s+(DW_AT_\w+)\s*\((.*)\)\s*$')
_QUOTED  = re.compile(r'"([^"]*)"')
_ADDR_RE = re.compile(r'(0x[0-9a-fA-F]+)')

_COMPOUND_TAGS = frozenset({
    "DW_TAG_class_type",
    "DW_TAG_structure_type",
    "DW_TAG_union_type",
})

_COMPOUND_END_TAGS = frozenset({
    "DW_TAG_compile_unit",
    "DW_TAG_subprogram",
    "DW_TAG_namespace",
    "DW_TAG_base_type",
    "DW_TAG_typedef",
    "DW_TAG_enumeration_type",
    "DW_TAG_pointer_type",
    "DW_TAG_const_type",
    "DW_TAG_volatile_type",
    "DW_TAG_array_type",
})

_DWTYPE_TO_KIND = {
    "void": "void",
    "bool": "u8",
    "_Bool": "u8",
    "char": "i8",
    "signed char": "i8",
    "unsigned char": "u8",
    "u8": "u8",
    "s8": "i8",
    "u16": "u16",
    "s16": "i16",
    "u32": "u32",
    "s32": "i32",
    "int": "i32",
    "unsigned int": "u32",
    "unsigned": "u32",
    "long": "i32",
    "unsigned long": "u32",
    "long long": "i64",
    "unsigned long long": "u64",
    "f32": "f32",
    "float": "f32",
    "f64": "f64",
    "double": "f64",
    "size_t": "u64",
    "ptrdiff_t": "i64",
}

FieldLayout = Union[int, Dict[str, object]]


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


def _parse_byte_size(raw: str) -> Optional[int]:
    m = re.search(r'0x([0-9a-fA-F]+)', raw)
    if m:
        return int(m.group(1), 16)
    m = re.search(r'\b(\d+)\b', raw)
    return int(m.group(1)) if m else None


def _parse_member_location(raw: str) -> Optional[int]:
    m = re.search(r'DW_OP_plus_uconst,\s*(0x[0-9a-fA-F]+|\d+)', raw)
    if m:
        val = m.group(1)
        return int(val, 16) if val.startswith("0x") else int(val)
    m = re.search(r'0x([0-9a-fA-F]+)', raw)
    if m:
        return int(m.group(1), 16)
    m = re.search(r'\b(\d+)\b', raw)
    return int(m.group(1)) if m else None


def _dwarf_type_kind(type_name: str) -> tuple[str, str]:
    raw = (type_name or "").strip()
    if not raw:
        return "i32", ""
    if "[" in raw:
        return "array", ""
    is_ptr = raw.endswith("*")
    base = raw.rstrip(" *")
    if base in _DWTYPE_TO_KIND:
        return _DWTYPE_TO_KIND[base], ""
    if is_ptr:
        return "ptr", base
    return "ptr", base


def _is_anonymous_type(name: str) -> bool:
    markers = ("(anonymous", "<anonymous", "__unnamed", "<unnamed", "(unnamed")
    return not name or any(m in name for m in markers)


def _parse_dwarf_types_stream(lines: Iterator[str]) -> Dict[str, Dict]:
    """
  Parse llvm-dwarfdump --debug-info output and return::

      { "do_class": { "size": 4192, "fields": { "mAction": {"offset": 1854, "kind": "i16"} } } }

  llvm-dwarfdump prints DIE lines flush-left (0x...: DW_TAG_...), so nesting is
  inferred from tag order rather than leading whitespace.
    """
    layouts: Dict[str, Dict] = {}

    state = "none"
    compound_name: Optional[str] = None
    compound_size: Optional[int] = None
    compound_header = False
    fields: Dict[str, FieldLayout] = {}

    member_name: Optional[str] = None
    member_offset: Optional[int] = None
    member_type: Optional[str] = None

    def flush_member() -> None:
        nonlocal member_name, member_offset, member_type, state
        if member_name and member_offset is not None:
            kind, view = _dwarf_type_kind(member_type or "")
            entry: Dict[str, object] = {"offset": member_offset, "kind": kind}
            if view:
                entry["view"] = view
            fields[member_name] = entry
        member_name = member_offset = member_type = None
        if state == "member":
            state = "compound"

    def flush_compound() -> None:
        nonlocal compound_name, compound_size, fields, state, compound_header
        flush_member()
        if compound_name and not _is_anonymous_type(compound_name) and fields:
            prev = layouts.get(compound_name)
            if prev is None or len(fields) > len(prev.get("fields") or {}):
                layouts[compound_name] = {
                    "size": compound_size or 0,
                    "fields": dict(fields),
                }
        compound_name = compound_size = None
        fields = {}
        compound_header = False
        state = "none"

    for line in lines:
        die_m = _DIE_RE.match(line)
        if die_m:
            tag = die_m.group(2)

            if tag in _COMPOUND_TAGS:
                flush_compound()
                state = "compound"
                compound_header = True
            elif tag == "DW_TAG_member" and state in ("compound", "member"):
                flush_member()
                compound_header = False
                state = "member"
            elif tag == "DW_TAG_inheritance" and state == "compound":
                flush_member()
            elif tag in _COMPOUND_END_TAGS or tag == "DW_TAG_subroutine_type":
                flush_compound()
            elif state in ("compound", "member"):
                flush_member()
            continue

        attr_m = _ATTR_RE.match(line)
        if not attr_m:
            continue

        attr, raw_val = attr_m.group(1), attr_m.group(2)

        if state == "member":
            if attr == "DW_AT_name":
                member_name = _attr_value(raw_val)
            elif attr == "DW_AT_data_member_location":
                member_offset = _parse_member_location(raw_val)
            elif attr == "DW_AT_type":
                member_type = _attr_value(raw_val)
            continue

        if state == "compound" and compound_header:
            if attr == "DW_AT_name":
                compound_name = _attr_value(raw_val)
            elif attr == "DW_AT_byte_size":
                compound_size = _parse_byte_size(raw_val)

    flush_compound()
    return layouts


class DwarfBackend(DebugInfoBackend):
    name = "dwarf"

    def extract_rvas(self, binary_path: str) -> Dict[str, int]:
        if not _DWARFDUMP:
            sys.exit("dwarf backend: requires llvm-dwarfdump or dwarfdump")

        proc = subprocess.Popen(
            [_DWARFDUMP, "--debug-info", binary_path],
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
        if not result:
            result = _extract_rvas_nm(binary_path)
        return result

    def extract_struct_layouts(self, binary_path: str) -> Dict[str, Dict]:
        if not _DWARFDUMP:
            return {}
        proc = subprocess.Popen(
            [_DWARFDUMP, "--debug-info", binary_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
        )
        try:
            return _parse_dwarf_types_stream(proc.stdout)
        finally:
            if proc.stdout:
                proc.stdout.close()
            proc.wait()


def _extract_rvas_nm(binary_path: str) -> Dict[str, int]:
    try:
        proc = subprocess.run(
            ["nm", binary_path],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except Exception:
        return {}
    result: Dict[str, int] = {}
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        addr, kind, name = parts[0], parts[1], parts[2]
        if kind not in {"T", "t", "D", "d"}:
            continue
        try:
            rva = int(addr, 16)
        except ValueError:
            continue
        if name not in result:
            result[name] = rva
    return result