#!/usr/bin/env python3
import re

_RECORD_RE = re.compile(r'^\s*(0x[0-9a-fA-F]+)\s*\|\s*([A-Z0-9_]+)\s+\[size = \d+\](?:\s+`([^`]+)`)?')
_FIELD_LIST_RE = re.compile(r'field list\s*=\s*(0x[0-9a-fA-F]+)')
_SIZE_RE = re.compile(r'size\s*=\s*(\d+)')
_RETURN_TYPE_RE = re.compile(r'return type\s*=\s*(0x[0-9a-fA-F]+)\s*\((.+)\)')
_CLASS_TYPE_RE = re.compile(r'class type\s*=\s*(0x[0-9a-fA-F]+)')
_PARAM_LIST_RE = re.compile(r'param list\s*=\s*(0x[0-9a-fA-F]+)')

_LF_MEMBER_RE = re.compile(r'^\s*-\s+LF_MEMBER\s+\[name\s*=\s*`([^`]+)`,\s*Type\s*=\s*(0x[0-9a-fA-F]+)\s*\((.+)\),\s*offset\s*=\s*(\d+)')
_LF_ENUMERATE_RE = re.compile(r'^\s*-\s+LF_ENUMERATE\s+\[name\s*=\s*`([^`]+)`,\s*value\s*=\s*(-?\d+|0x[0-9a-fA-F]+)')
_ARG_TYPE_RE = re.compile(r'^\s*-\s+ArgType\s*=\s*(0x[0-9a-fA-F]+)\s*\((.+)\)')

_SYM_RECORD_RE = re.compile(r'^\s*(\d+|0x[0-9a-fA-F]+)\s*\|\s*(S_GPROC32|S_LPROC32|S_GDATA32|S_LDATA32|S_UDT)\s+\[size = \d+\](?:\s+`([^`]+)`)?')
_SYM_TYPE_RE = re.compile(r'type\s*=\s*(0x[0-9a-fA-F]+)\s*(?:\((.+)\))?')
_SYM_ADDR_RE = re.compile(r'addr\s*=\s*([0-9a-fA-F]+):([0-9a-fA-F]+)')

_PRIM = {
    "void": "void", "bool": "u8", "char": "i8", "signed char": "i8", "unsigned char": "u8",
    "short": "i16", "short int": "i16", "unsigned short": "u16", "short unsigned int": "u16",
    "int": "i32", "unsigned int": "u32", "long": "i32", "unsigned long": "u32", 
    "long long": "i64", "long long int": "i64", "unsigned long long": "u64",
    "float": "f32", "double": "f64", "long double": "f64", "wchar_t": "i16",
    "__int8": "i8", "unsigned __int8": "u8", "__int16": "i16", "unsigned __int16": "u16",
    "__int32": "i32", "unsigned __int32": "u32", "__int64": "i64", "unsigned __int64": "u64",
    "int8_t": "i8", "uint8_t": "u8", "int16_t": "i16", "uint16_t": "u16",
    "int32_t": "i32", "uint32_t": "u32", "int64_t": "i64", "uint64_t": "u64",
    "size_t": "u64", "intptr_t": "i64", "uintptr_t": "u64", "ptrdiff_t": "i64"
}

_CHAR_ARR_RE = re.compile(r"^(?:const\s+|volatile\s+)*(?:signed\s+|unsigned\s+)?char\s*\[(\d+)\]$")
_IDENT_RE = re.compile(r"^[A-Za-z_]\w*(?:::[A-Za-z_]\w*)*$")

def ffi_kind(t):
    t = t.strip()
    m = _CHAR_ARR_RE.match(t)
    if m:
        return ("str", int(m.group(1)))
    if "*" in t or "&" in t or "[]" in t:
        return ("ptr", None)
    base = t.replace("const", "").replace("volatile", "").strip()
    return (_PRIM.get(base, "ptr"), None)

def pointee_struct(t):
    t = t.strip()
    if "*" in t or "&" in t:
        base = t.replace("*", "").replace("&", "").replace("const", "").replace("volatile", "").strip()
        if _IDENT_RE.match(base) and base not in _PRIM:
            return base
    return None

def _flat(qualified):
    return qualified.split("(")[0].strip().replace("::", "_").replace(" ", "")

class PdbType:
    __slots__ = ("kind", "name", "fields", "enum_values", "args", "byte_size", "field_list_id", "return_type_name", "class_type_id")
    def __init__(self, kind, name=""):
        self.kind = kind
        self.name = name
        self.fields = []
        self.enum_values = []
        self.args = []
        self.byte_size = 0
        self.field_list_id = None
        self.return_type_name = "void"
        self.class_type_id = None

def parse_pdb_dump(text):
    types_db = {}
    functions = []
    globals_list = []
    typedefs = []
    
    current_type = None
    current_sym = None

    for line in text.splitlines():
        m_rec = _RECORD_RE.match(line)
        if m_rec:
            current_sym = None  # Clear context
            tid, kind, name = m_rec.group(1), m_rec.group(2), m_rec.group(3) or ""
            current_type = PdbType(kind, name)
            types_db[tid] = current_type
            continue

        m_sym = _SYM_RECORD_RE.match(line)
        if m_sym:
            current_type = None  # Clear context
            sym_kind, sym_name = m_sym.group(2), m_sym.group(3) or ""
            current_sym = {
                "kind": sym_kind, "name": sym_name,
                "type_id": None, "type_name": "", "rva": None
            }
            if sym_kind in ("S_GPROC32", "S_LPROC32"):
                functions.append(current_sym)
            elif sym_kind in ("S_GDATA32", "S_LDATA32"):
                globals_list.append(current_sym)
            elif sym_kind == "S_UDT":
                typedefs.append(current_sym)
            continue

        if current_type:
            fl_m = _FIELD_LIST_RE.search(line)
            if fl_m: current_type.field_list_id = fl_m.group(1)
            
            sz_m = _SIZE_RE.search(line)
            if sz_m and current_type.kind in ("LF_STRUCTURE", "LF_CLASS", "LF_UNION"):
                current_type.byte_size = int(sz_m.group(1))
                
            ret_m = _RETURN_TYPE_RE.search(line)
            if ret_m: current_type.return_type_name = ret_m.group(2)
                
            cls_m = _CLASS_TYPE_RE.search(line)
            if cls_m: current_type.class_type_id = cls_m.group(1)
                
            p_m = _PARAM_LIST_RE.search(line)
            if p_m: current_type.field_list_id = p_m.group(1)

            if current_type.kind == "LF_FIELDLIST":
                mem_m = _LF_MEMBER_RE.match(line)
                if mem_m:
                    current_type.fields.append({
                        "name": mem_m.group(1), "type_id": mem_m.group(2),
                        "type_name": mem_m.group(3), "offset": int(mem_m.group(4))
                    })
                enum_m = _LF_ENUMERATE_RE.match(line)
                if enum_m:
                    val_str = enum_m.group(2)
                    val = int(val_str, 16) if val_str.lower().startswith("0x") else int(val_str)
                    current_type.enum_values.append({"name": enum_m.group(1), "value": val})
            elif current_type.kind == "LF_ARGLIST":
                arg_m = _ARG_TYPE_RE.match(line)
                if arg_m:
                    current_type.args.append({"type_id": arg_m.group(1), "type_name": arg_m.group(2)})

        elif current_sym:
            t_m = _SYM_TYPE_RE.search(line)
            if t_m:
                current_sym["type_id"] = t_m.group(1)
                if t_m.group(2): current_sym["type_name"] = t_m.group(2)
            
            addr_m = _SYM_ADDR_RE.search(line)
            if addr_m:
                current_sym["rva"] = f"0x{addr_m.group(1)}:{addr_m.group(2)}"

    return types_db, functions, globals_list, typedefs

def extract_structs(types_db):
    out = []
    for t in types_db.values():
        if t.kind in ("LF_STRUCTURE", "LF_CLASS", "LF_UNION") and t.name:
            fields = []
            if t.field_list_id and t.field_list_id in types_db:
                for fld in types_db[t.field_list_id].fields:
                    k, ln = ffi_kind(fld["type_name"])
                    f_info = {"name": fld["name"], "offset": fld["offset"], "kind": k}
                    if ln is not None: f_info["len"] = ln
                    view = pointee_struct(fld["type_name"])
                    if view: f_info["view"] = view
                    fields.append(f_info)
            out.append({"name": t.name, "size": t.byte_size, "fields": fields})
    return out

def extract_enums(types_db):
    out = []
    for t in types_db.values():
        if t.kind == "LF_ENUM" and t.name:
            values = []
            if t.field_list_id and t.field_list_id in types_db:
                for ev in types_db[t.field_list_id].enum_values:
                    values.append({"name": ev["name"], "value": ev["value"]})
            owner = "::".join(t.name.split("::")[:-1]) if "::" in t.name else None
            out.append({"name": t.name, "owner": owner, "values": values})
    return out

def extract_functions(functions_raw, types_db, struct_names):
    out = []
    for fn in functions_raw:
        qname = fn["name"]
        ret = "void"
        member = False
        self_view = None
        args = []
        
        tid = fn["type_id"]
        if tid and tid in types_db:
            t_rec = types_db[tid]
            ret = ffi_kind(t_rec.return_type_name)[0]
            if t_rec.kind == "LF_MFUNCTION":
                member = True
                if t_rec.class_type_id and t_rec.class_type_id in types_db:
                    self_view = types_db[t_rec.class_type_id].name
            
            if t_rec.field_list_id and t_rec.field_list_id in types_db:
                for i, arg_item in enumerate(types_db[t_rec.field_list_id].args):
                    t_name = arg_item["type_name"]
                    kind_str, _ = ffi_kind(t_name)
                    arg_dict = {"name": f"arg{i}", "kind": kind_str}
                    view = pointee_struct(t_name)
                    if view: arg_dict["view"] = view
                    args.append(arg_dict)
                    
        out.append({
            "flat": _flat(qname), "mangled": qname, "member": member,
            "self_view": self_view, "rva": fn["rva"], "loc": None,
            "ret": ret, "args": args
        })
    return out

def extract_globals(globals_raw):
    return [{"name": g["name"], "kind": ffi_kind(g["type_name"])[0], "addr": g["rva"]} for g in globals_raw]

def extract_typedefs(typedefs_raw):
    seen = set()
    out = []
    for t in typedefs_raw:
        if t["name"] not in seen:
            seen.add(t["name"])
            out.append({"alias": t["name"], "kind": ffi_kind(t["type_name"])[0]})
    return out

def assemble_pdb(text):
    types_db, functions_raw, globals_raw, typedefs_raw = parse_pdb_dump(text)
    
    structs = extract_structs(types_db)
    struct_names = {s["name"] for s in structs}
    
    functions = extract_functions(functions_raw, types_db, struct_names)
    functions.sort(key=lambda f: (f["flat"], f["mangled"]))
    
    return {
        "version": 2,
        "functions": functions,
        "structs": sorted(structs, key=lambda s: s["name"]),
        "enums": sorted(extract_enums(types_db), key=lambda e: e["name"]),
        "globals": sorted(extract_globals(globals_raw), key=lambda g: g["name"]),
        "typedefs": sorted(extract_typedefs(typedefs_raw), key=lambda t: t["alias"])
    }