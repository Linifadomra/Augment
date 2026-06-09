#!/usr/bin/env python3
import re

_RECORD_RE = re.compile(r'^\s*(0x[0-9a-fA-F]+)\s*\|\s*([A-Z0-9_]+)\s+\[size = \d+\](?:\s+`([^`]+)`)?')
_FIELD_LIST_RE = re.compile(r'field list\s*[=:]\s*(0x[0-9a-fA-F]+)')
_SIZEOF_RE = re.compile(r'sizeof\s+(\d+)')
_RETURN_TYPE_RE = re.compile(r'return type\s*=\s*(0x[0-9a-fA-F]+)\s*\((.+?)\)')
_CLASS_TYPE_RE = re.compile(r'class type\s*[=:]\s*(0x[0-9a-fA-F]+)')
_PARAM_LIST_RE = re.compile(r'(?:param|arg) list\s*=\s*(0x[0-9a-fA-F]+)')
_REFERENT_RE = re.compile(r'(?:referent(?: type)?|element type|modified type|underlying type)\s*[=:]\s*(0x[0-9a-fA-F]+)')

_LF_MEMBER_RE = re.compile(r'^\s*-\s+LF_MEMBER\s+\[name\s*=\s*`([^`]+)`,\s*Type\s*=\s*(0x[0-9a-fA-F]+)(?:\s*\((.+?)\))?,\s*offset\s*=\s*(\d+)')
_LF_ENUMERATE_RE = re.compile(r'^\s*-\s+LF_ENUMERATE\s+\[name\s*=\s*`([^`]+)`,\s*value\s*=\s*(-?\d+|0x[0-9a-fA-F]+)')
_ARG_TYPE_RE = re.compile(r'^\s*(?:-\s+ArgType\s*=\s*|<type:\s*)(0x[0-9a-fA-F]+)\s*\(([^)]+)\)')

_SYM_RECORD_RE = re.compile(
    r'^\s*(\d+|0x[0-9a-fA-F]+)\s*\|\s*'
    r'(S_[A-Z0-9_]+)'
    r'(?:\s+\[size = \d+\])?(?:\s+`([^`]+)`)?'
)

_SYM_TYPE_RE = re.compile(r'type\s*=\s*`?(0x[0-9a-fA-F]+)\s*(?:\((.+)\))?')
_SYM_ADDR_RE = re.compile(
    r'addr\s*=\s*([0-9a-fA-F]+)\s*:\s*([0-9a-fA-F]+)'
)

_SEC_NUM_RE = re.compile(r'SECTION HEADER #(\d+)', re.IGNORECASE)
_SEC_VA_RE  = re.compile(r'([0-9a-fA-F]+)\s+virtual address', re.IGNORECASE)

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

def ffi_kind(type_name):
    if not type_name:
        return "unknown", None
        
    type_name = type_name.strip().replace("`", "")
    
    if type_name.endswith("]"):
        match = re.search(r'\[(\d+)\]$', type_name)
        array_len = int(match.group(1)) if match else None
        return "array", array_len

    if type_name.endswith("*"):
        return "ptr", None

    primitive_map = {
        "void": ("void", None), "char": ("i8", None), "signed char": ("i8", None), "s8": ("i8", None),
        "unsigned char": ("u8", None), "u8": ("u8", None), "short": ("i16", None), "unsigned short": ("u16", None),
        "u16": ("u16", None), "int": ("i32", None), "unsigned int": ("u32", None), "unsigned": ("u32", None),
        "long": ("i32", None), "u32": ("u32", None), "float": ("f32", None), "f32": ("f32", None),
    }
    
    if type_name in primitive_map:
        return primitive_map[type_name]
        
    return "struct", None

def resolve_field_schema(type_name):
    if not type_name:
        return {"kind": "ptr"}
        
    type_name = type_name.strip().replace("`", "")
    
    primitive_map = {
        "unsigned char": "u8", "u8": "u8",
        "char": "i8", "signed char": "i8", "s8": "i8",
        "unsigned short": "u16", "u16": "u16",
        "short": "i16", "s16": "i16",
        "unsigned int": "u32", "unsigned": "u32", "u32": "u32",
        "int": "i32", "s32": "i32",
        "float": "f32", "f32": "f32"
    }
    
    if type_name in primitive_map:
        return {"kind": primitive_map[type_name]}
        
    if "[" in type_name:
        return {"kind": "ptr"}
        
    if type_name.endswith("*"):
        base_type = type_name[:-1].strip()
        if base_type in ("void", "int", "char", "unsigned char", "float"):
            return {"kind": "ptr"}
        return {"kind": "ptr", "view": base_type}
        
    return {"kind": "ptr"}

def pointee_struct(t):
    t = t.strip()
    if "*" in t or "&" in t:
        base = t.replace("*", "").replace("&", "").replace("const", "").replace("volatile", "").strip()
        if _IDENT_RE.match(base) and base not in _PRIM:
            return base
    return None

def _flat(qname):
    base = qname.split("(")[0].strip().replace("::", "_").replace(" ", "")
    return base

def parse_section_headers(text):
    sections = {}
    current_seg = None
    for line in text.splitlines():
        m = _SEC_NUM_RE.search(line)
        if m:
            current_seg = int(m.group(1))
            continue
        if current_seg is not None:
            m = _SEC_VA_RE.search(line)
            if m:
                sections[current_seg] = int(m.group(1), 16)
    return sections

def _resolve_rva(seg_str, off_str, section_map):
    if seg_str is None or off_str is None:
        return None

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

    return f"0x{base + off:x}"

class PdbType:
    __slots__ = ("kind", "name", "fields", "enum_values", "args", "byte_size", 
                 "field_list_id", "return_type_name", "class_type_id", "inline_type_id", "referent_id")
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
        self.inline_type_id = None
        self.referent_id = None

def parse_pdb_dump(text):
    types_db = {}
    functions = []
    globals_list = []
    typedefs = []
    
    current_type = None
    current_sym = None
    current_func = None

    for line in text.splitlines():
        m_rec = _RECORD_RE.match(line)
        if m_rec:
            current_sym = None
            current_func = None
            tid, kind, name = m_rec.group(1), m_rec.group(2), m_rec.group(3) or ""
            current_type = PdbType(kind, name)
            types_db[tid] = current_type
            
            if kind in ("LF_FUNC_ID", "LF_MFUNC_ID"):
                inline_m = re.search(r'(?<!class\s)(?<!return\s)\btype\s*=\s*(0x[0-9a-fA-F]+)', line)
                if inline_m:
                    current_type.inline_type_id = inline_m.group(1)
            continue

        m_sym = _SYM_RECORD_RE.match(line)
        if m_sym:
            current_type = None
            sym_kind, sym_name = m_sym.group(2), m_sym.group(3) or ""
            
            if sym_kind in ("S_GPROC32", "S_LPROC32", "S_GPROC32_ID", "S_LPROC32_ID"):
                current_func = {
                    "kind": sym_kind,
                    "name": sym_name,
                    "type_id": None,
                    "type_name": "",
                    "_addr": None,
                    "params": []
                }
                functions.append(current_func)
                current_sym = current_func
                
            elif sym_kind == "S_LOCAL":
                if current_func is not None:
                    current_sym = {
                        "kind": sym_kind, "name": sym_name,
                        "type_id": None, "type_name": "", "is_param": False
                    }
                    current_func["params"].append(current_sym)
                else:
                    current_sym = None
                    
            elif sym_kind in ("S_END", "S_INLINESITE_END", "S_PROC_ID_END"):
                current_func = None
                current_sym = None
                
            elif sym_kind in ("S_GDATA32", "S_LDATA32"):
                current_sym = { "name": sym_name, "kind": sym_kind, "type_id": None, "type_name": "", "_addr": None }
                globals_list.append(current_sym)
            elif sym_kind == "S_UDT":
                current_sym = { "name": sym_name, "kind": sym_kind }
                typedefs.append(current_sym)
            else:
                current_sym = None 
            continue

        if current_type is not None:
            sz_m = _SIZEOF_RE.search(line)
            if sz_m and current_type.kind in ("LF_STRUCTURE", "LF_CLASS", "LF_UNION"):
                current_type.byte_size = int(sz_m.group(1))

            fl_m = _FIELD_LIST_RE.search(line)
            if fl_m and current_type.kind in ("LF_STRUCTURE", "LF_CLASS", "LF_UNION"):
                current_type.field_list_id = fl_m.group(1)
                
            ret_m = _RETURN_TYPE_RE.search(line)
            if ret_m: current_type.return_type_name = ret_m.group(2)
                
            cls_m = _CLASS_TYPE_RE.search(line)
            if cls_m: current_type.class_type_id = cls_m.group(1)
                
            p_m = _PARAM_LIST_RE.search(line)
            if p_m: current_type.field_list_id = p_m.group(1)

            ref_m = _REFERENT_RE.search(line)
            if ref_m:
                current_type.referent_id = ref_m.group(1)

            if current_type.kind in ("LF_FUNC_ID", "LF_MFUNC_ID"):
                inline_m = re.search(r'(?<!class\s)(?<!return\s)\btype\s*=\s*(0x[0-9a-fA-F]+)', line)
                if inline_m:
                    current_type.inline_type_id = inline_m.group(1)

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
            
        elif current_sym is not None:
            if current_sym.get("kind") in ("S_GPROC32", "S_LPROC32", "S_GPROC32_ID", "S_LPROC32_ID", "S_GDATA32", "S_LDATA32", "S_UDT"):
                t_m = _SYM_TYPE_RE.search(line)
                if t_m and not current_sym.get("type_id"): 
                    current_sym["type_id"] = t_m.group(1)
                    if t_m.group(2): current_sym["type_name"] = t_m.group(2)
                
                addr_m = _SYM_ADDR_RE.search(line)
                if addr_m and not current_sym.get("_addr"):
                    current_sym["_addr"] = (addr_m.group(1), addr_m.group(2))
                    
            elif current_sym.get("kind") == "S_LOCAL":
                t_m = re.search(r'type\s*=\s*`?(0x[0-9a-fA-F]+)\s*(?:\(([^)]+)\))?`?', line)
                if t_m:
                    current_sym["type_id"] = t_m.group(1)
                    if t_m.group(2): current_sym["type_name"] = t_m.group(2)
                
                if re.search(r'flags\s*=[^,]*\bparam\b', line):
                    current_sym["is_param"] = True

    return types_db, functions, globals_list, typedefs

def _named_count(f):
    return len(f.get("args", []))

def resolve_type_name(tid, types_db, depth=0):
    if not tid or depth > 10:
        return ""
    t = types_db.get(tid)
    if not t:
        return ""
    if t.name:
        return t.name
        
    if t.referent_id:
        base_name = resolve_type_name(t.referent_id, types_db, depth + 1)
        if base_name:
            if t.kind == "LF_POINTER":
                return base_name + "*"
            elif t.kind == "LF_ARRAY":
                return base_name + "[]"
            return base_name
    return ""

def extract_functions(functions_raw, types_db, struct_names, section_map):
    out = []
    for fn in functions_raw:
        qname    = fn["name"]
        ret      = "void"
        member   = False
        self_view = None
        args     = []

        tid = fn.get("type_id")
        t_rec = types_db.get(tid) if tid else None
        
        if t_rec and t_rec.kind in ("LF_FUNC_ID", "LF_MFUNC_ID") and t_rec.inline_type_id:
            t_rec = types_db.get(t_rec.inline_type_id)

        if t_rec:
            ret = ffi_kind(t_rec.return_type_name)[0]

            if t_rec.kind == "LF_MFUNCTION":
                member = True
                if t_rec.class_type_id and t_rec.class_type_id in types_db:
                    self_view = types_db[t_rec.class_type_id].name

        if ret == "void" and fn.get("type_name"):
            t_name = fn["type_name"].strip()
            if '(' in t_name and t_name.endswith(')'):
                idx = t_name.rindex('(')
                possible_ret = t_name[:idx].strip()
                if possible_ret:
                    ret = ffi_kind(possible_ret)[0]

        if "params" in fn and any(p.get("is_param") for p in fn["params"]):
            for p in fn["params"]:
                if p.get("is_param"):
                    t_name = p.get("type_name")
                    if not t_name:
                        t_name = resolve_type_name(p.get("type_id"), types_db) or "void*"
                    kind_str, _ = ffi_kind(t_name)
                    arg_dict = {"name": p["name"], "kind": kind_str}
                    view = pointee_struct(t_name)
                    if view:
                        arg_dict["view"] = view
                    args.append(arg_dict)
        else:
            if t_rec and t_rec.field_list_id and t_rec.field_list_id in types_db:
                for i, arg_item in enumerate(types_db[t_rec.field_list_id].args):
                    t_name = arg_item.get("type_name")
                    if not t_name:
                        t_name = resolve_type_name(arg_item.get("type_id"), types_db) or "void*"
                    kind_str, _ = ffi_kind(t_name)
                    arg_dict = {"name": f"arg{i}", "kind": kind_str}
                    view = pointee_struct(t_name)
                    if view:
                        arg_dict["view"] = view
                    args.append(arg_dict)

        addr = fn.get("_addr")
        rva  = _resolve_rva(*addr, section_map) if addr else None

        out.append({
            "flat":      _flat(qname),
            "mangled":   qname,
            "member":    member,
            "self_view": self_view,
            "rva":       rva,
            "loc":       None,
            "ret":       ret,
            "args":      args,
        })

    def valid_rva(r):
        return r is not None and r != "0x0"
    
    best = {}
    for f in out:
        key = f["mangled"]
        cur = best.get(key)
        if cur is None:
            best[key] = f
        elif valid_rva(f["rva"]) and not valid_rva(cur["rva"]):
            best[key] = f
        elif valid_rva(f["rva"]) == valid_rva(cur["rva"]) and _named_count(f) > _named_count(cur):
            best[key] = f
    return list(best.values())

def extract_structs(types_db):
    best = {}

    for t_id, t in types_db.items():
        if t.kind in ("LF_STRUCTURE", "LF_CLASS", "LF_UNION"):
            if not t.name: continue
            has_fields = t.field_list_id and t.field_list_id in types_db
            field_count = len(types_db[t.field_list_id].fields) if has_fields else 0
            existing = best.get(t.name)
            
            if existing is None:
                best[t.name] = t
            else:
                existing_has_fields = existing.field_list_id and existing.field_list_id in types_db
                existing_count = len(types_db[existing.field_list_id].fields) if existing_has_fields else 0
                if field_count > existing_count or (field_count == existing_count and t.byte_size > existing.byte_size):
                    best[t.name] = t
                
    final_output = []
    for name, t in best.items():
        fields = []
        if t.field_list_id and t.field_list_id in types_db:
            for fld in types_db[t.field_list_id].fields:
                fld_name = fld["name"]
                fld_offset = fld["offset"]
                raw_type_name = fld.get("type_name", "")
                
                if not raw_type_name or not raw_type_name.strip():
                    raw_type_name = resolve_type_name(fld["type_id"], types_db)
                
                schema_props = resolve_field_schema(raw_type_name)
                f_info = {"name": fld_name, "offset": fld_offset}
                f_info.update(schema_props)
                fields.append(f_info)
                
        final_output.append({"name": name, "size": t.byte_size, "fields": fields})
    return final_output

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

    best = {}
    for e in out:
        cur = best.get(e["name"])
        if cur is None or len(e["values"]) > len(cur["values"]):
            best[e["name"]] = e
    return list(best.values())

def extract_globals(globals_raw, section_map, types_db):
    out = []
    for g in globals_raw:
        addr = g.get("_addr")
        rva  = _resolve_rva(*addr, section_map) if addr else None
        
        t_name = g.get("type_name")
        if not t_name:
            t_name = resolve_type_name(g.get("type_id"), types_db)
            
        out.append({
            "name": g["name"],
            "kind": ffi_kind(t_name)[0],
            "addr": rva,
        })
    return out

def extract_typedefs(typedefs_raw, types_db):
    seen = set()
    out = []
    for t in typedefs_raw:
        alias = t.get("name")
        if not alias or alias in seen:
            continue
            
        t_name = t.get("type_name")
        
        if not t_name and t.get("type_id"):
            t_name = resolve_type_name(t["type_id"], types_db)
        
        if not t_name:
            t_rec = types_db.get(t.get("type_id"))
            if t_rec:
                if t_rec.kind in ("LF_POINTER", "LF_ARRAY"):
                    t_name = "void*"
                elif t_rec.kind == "LF_ENUM":
                    t_name = "int"
        
        if not t_name:
            if t.get("type_id"):
                t_name = "void*"
            else: 
                continue
                
        seen.add(alias)
        out.append({"alias": alias, "kind": ffi_kind(t_name)[0]})
        
    return out

def assemble_pdb(text):
    section_map = parse_section_headers(text)
    types_db, functions_raw, globals_raw, typedefs_raw = parse_pdb_dump(text)
    
    structs = extract_structs(types_db)
    struct_names = {s["name"] for s in structs}
    
    functions = extract_functions(functions_raw, types_db, struct_names, section_map)
    functions.sort(key=lambda f: (f["flat"], f["mangled"]))
    
    return {
        "version": 2,
        "functions": functions,
        "structs": sorted(structs, key=lambda s: s["name"]),
        "enums": sorted(extract_enums(types_db), key=lambda e: e["name"]),
        "globals": sorted(extract_globals(globals_raw, section_map, types_db), key=lambda g: g["name"]),
        "typedefs": sorted(extract_typedefs(typedefs_raw, types_db), key=lambda t: t["alias"])
    }