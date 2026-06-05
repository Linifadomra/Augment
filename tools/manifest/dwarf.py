#!/usr/bin/env python3
import re

_DIE_RE  = re.compile(r'^(0x[0-9a-fA-F]+):(\s*)(DW_TAG_\w+)')
_ATTR_RE = re.compile(r'^\s+(DW_AT_\w+)\s*\((.*)\)\s*$')

class Die:
    __slots__ = ("tag", "indent", "attrs", "children")
    def __init__(self, tag, indent):
        self.tag = tag
        self.indent = indent
        self.attrs = {}
        self.children = []
    def attr(self, name):
        return self.attrs.get(name)

def _attr_value(raw):
    m = re.search(r'"([^"]*)"', raw)
    if m:
        return m.group(1)
    return raw.strip()

def parse_dies(text):
    roots = []
    stack = []
    cur = None
    for line in text.splitlines():
        m = _DIE_RE.match(line)
        if m:
            indent = len(m.group(2))
            cur = Die(m.group(3), indent)
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

_PRIM = {
    "void":"void","bool":"u8","char":"i8","signed char":"i8","unsigned char":"u8",
    "short":"i16","short int":"i16","unsigned short":"u16","short unsigned int":"u16",
    "int":"i32","unsigned int":"u32","long":"i64","long int":"i64",
    "unsigned long":"u64","long unsigned int":"u64","long long":"i64","long long int":"i64",
    "unsigned long long":"u64","long long unsigned int":"u64","float":"f32",
    "double":"f64","long double":"f64","wchar_t":"i16",
    "s8":"i8","u8":"u8","s16":"i16","u16":"u16","s32":"i32","u32":"u32",
    "s64":"i64","u64":"u64","f32":"f32","f64":"f64","BOOL":"i32",
    "int8_t":"i8","uint8_t":"u8","int16_t":"i16","uint16_t":"u16",
    "int32_t":"i32","uint32_t":"u32","int64_t":"i64","uint64_t":"u64",
    "size_t":"u64","intptr_t":"i64","uintptr_t":"u64","ptrdiff_t":"i64",
}
_CHAR_ARR_RE = re.compile(r"^(?:const\s+|volatile\s+)*(?:signed\s+|unsigned\s+)?char\s*\[(\d+)\]$")
_IDENT_RE = re.compile(r"^[A-Za-z_]\w*$")

def _clean(t):
    return t.replace("const", "").replace("volatile", "").strip()

def ffi_kind(t):
    t = t.strip()
    m = _CHAR_ARR_RE.match(t)
    if m:
        return ("str", int(m.group(1)))
    if "::*" in t:
        return ("pmf", None)
    if t.endswith("*") or t.endswith("&") or "(*)" in t:
        return ("ptr", None)
    base = _clean(t)
    return (_PRIM.get(base, "ptr"), None)

def pointee_struct(t):
    t = t.strip()
    if t.endswith("*") or t.endswith("&"):
        base = _clean(t[:-1])
        if _IDENT_RE.match(base) and base not in _PRIM:
            return base
    return None

def _flat(qualified):
    return qualified.split("(")[0].strip().replace("::", "_").replace(" ", "")

def _arg(p):
    t = p.attr("DW_AT_type") or ""
    a = {"name": p.attr("DW_AT_name"), "kind": ffi_kind(t)[0]}
    v = pointee_struct(t)
    if v:
        a["view"] = v
    return a

def extract_functions(roots, demangle):
    out = []
    def visit(die):
        if die.tag == "DW_TAG_subprogram":
            mangled = die.attr("DW_AT_linkage_name")
            if mangled:
                params = [c for c in die.children if c.tag == "DW_TAG_formal_parameter"]
                member = bool(params and params[0].attr("DW_AT_artificial"))
                arg_dies = params[1:] if member else params
                args = [_arg(p) for p in arg_dies]
                self_view = pointee_struct(params[0].attr("DW_AT_type") or "") if member else None
                ret = ffi_kind(die.attr("DW_AT_type") or "void")[0]
                q = demangle.get(mangled, mangled)
                low = die.attr("DW_AT_low_pc")
                rva = hex(int(low, 0)) if low else None
                df = die.attr("DW_AT_decl_file")
                dl = die.attr("DW_AT_decl_line")
                loc = f"{df}:{dl}" if df and dl else None
                out.append({"flat": _flat(q), "mangled": mangled, "member": member,
                            "self_view": self_view, "rva": rva, "loc": loc,
                            "ret": ret, "args": args})
        for c in die.children:
            visit(c)
    for r in roots:
        visit(r)
    return out

_STRUCT_TAGS = ("DW_TAG_structure_type", "DW_TAG_class_type", "DW_TAG_union_type")

def extract_structs(roots):
    out = []
    def visit(die):
        if die.tag in _STRUCT_TAGS:
            name = die.attr("DW_AT_name")
            size = die.attr("DW_AT_byte_size")
            if name and _IDENT_RE.match(name) and size is not None:
                fields = []
                seen = set()
                for m in die.children:
                    if m.tag != "DW_TAG_member":
                        continue
                    mn = m.attr("DW_AT_name")
                    loc = m.attr("DW_AT_data_member_location")
                    if not mn or not _IDENT_RE.match(mn) or loc is None or mn in seen:
                        continue
                    seen.add(mn)
                    t = m.attr("DW_AT_type") or ""
                    kind, ln = ffi_kind(t)
                    fld = {"name": mn, "offset": int(loc, 0), "kind": kind}
                    if ln is not None:
                        fld["len"] = ln
                    view = pointee_struct(t)
                    if view:
                        fld["view"] = view
                    fields.append(fld)
                if fields:
                    out.append({"name": name, "size": int(size, 0), "fields": fields})
        for c in die.children:
            visit(c)
    for r in roots:
        visit(r)
    return out

def extract_enums(roots):
    out = []
    def visit(die, owner):
        if die.tag == "DW_TAG_enumeration_type":
            name = die.attr("DW_AT_name")
            if name:
                values = []
                for e in die.children:
                    if e.tag == "DW_TAG_enumerator":
                        en = e.attr("DW_AT_name")
                        ev = e.attr("DW_AT_const_value")
                        if en and ev is not None:
                            values.append({"name": en, "value": int(ev, 0)})
                if values:
                    qualified = f"{owner}::{name}" if owner else name
                    out.append({"name": qualified, "owner": owner, "values": values})
        child_owner = die.attr("DW_AT_name") if die.tag in _STRUCT_TAGS else owner
        for c in die.children:
            visit(c, child_owner)
    for r in roots:
        visit(r, None)
    return out

_ADDR_RE = re.compile(r"DW_OP_addr\s+(0x[0-9a-fA-F]+)")

def extract_globals(roots):
    out = []
    def visit(die, in_fn):
        if die.tag == "DW_TAG_variable" and not in_fn:
            name = die.attr("DW_AT_name")
            loc = die.attr("DW_AT_location") or ""
            m = _ADDR_RE.search(loc)
            if name and m:
                kind = ffi_kind(die.attr("DW_AT_type") or "")[0]
                out.append({"name": name, "kind": kind, "addr": hex(int(m.group(1), 0))})
        nested_in_fn = in_fn or die.tag == "DW_TAG_subprogram"
        for c in die.children:
            visit(c, nested_in_fn)
    for r in roots:
        visit(r, False)
    return out

def extract_typedefs(roots):
    out = []
    seen = set()
    def visit(die):
        if die.tag == "DW_TAG_typedef":
            alias = die.attr("DW_AT_name")
            if alias and alias not in seen:
                seen.add(alias)
                out.append({"alias": alias, "kind": ffi_kind(die.attr("DW_AT_type") or "")[0]})
        for c in die.children:
            visit(c)
    for r in roots:
        visit(r)
    return out
