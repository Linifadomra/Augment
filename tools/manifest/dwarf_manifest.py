#!/usr/bin/env python3
import subprocess, sys, re, shutil

DWARFDUMP = shutil.which("llvm-dwarfdump") or shutil.which("dwarfdump")
CXXFILT = shutil.which("llvm-cxxfilt") or shutil.which("c++filt")
if not DWARFDUMP:
    print("dwarf_manifest: requires llvm-dwarfdump (install LLVM)", file=sys.stderr)
    sys.exit(1)
if not CXXFILT:
    print("dwarf_manifest: requires llvm-cxxfilt or c++filt (install LLVM)", file=sys.stderr)
    sys.exit(1)

PRIM = {
    "void": "void", "bool": "u8", "char": "i8", "signed char": "i8",
    "unsigned char": "u8", "short": "i16", "short int": "i16",
    "short unsigned int": "u16", "unsigned short": "u16",
    "int": "i32", "unsigned int": "u32", "long": "i64", "long int": "i64",
    "unsigned long": "u64", "long unsigned int": "u64", "long long": "i64",
    "long long int": "i64", "unsigned long long": "u64",
    "long long unsigned int": "u64", "float": "f32", "double": "f64",
    "long double": "f64", "wchar_t": "i16", "char16_t": "u16", "char32_t": "u32",
    "s8": "i8", "u8": "u8", "s16": "i16", "u16": "u16", "s32": "i32", "u32": "u32",
    "s64": "i64", "u64": "u64", "f32": "f32", "f64": "f64", "BOOL": "i32",
    "int8_t": "i8", "uint8_t": "u8", "int16_t": "i16", "uint16_t": "u16",
    "int32_t": "i32", "uint32_t": "u32", "int64_t": "i64", "uint64_t": "u64",
    "size_t": "u64", "intptr_t": "i64", "uintptr_t": "u64", "ptrdiff_t": "i64",
}


def ffi_of(t):
    t = t.strip()
    if not t:
        return "void"
    if t.endswith("*") or t.endswith("&"):
        return "ptr"
    t = t.replace("const", "").replace("volatile", "").strip()
    return PRIM.get(t, "ptr")


def parse(text):
    funcs = {}
    cur = None
    for line in text.splitlines():
        s = line.strip()
        if "DW_TAG_subprogram" in s:
            if cur and cur["mangled"]:
                funcs[cur["mangled"]] = cur
            cur = {"mangled": None, "ret": "void", "params": [], "member": False}
        elif cur is None:
            continue
        elif "DW_TAG_formal_parameter" in s:
            cur["params"].append({"type": "", "art": False})
        elif "DW_TAG" in s:
            cur["params"].append({"type": "done", "art": False})  # block further return/param capture
        elif "DW_AT_linkage_name" in s:
            m = re.search(r'\("([^"]+)"\)', s)
            if m:
                cur["mangled"] = m.group(1)
        elif "DW_AT_type" in s:
            m = re.search(r'"([^"]*)"\)\s*$', s)
            t = m.group(1) if m else ""
            if cur["params"] and cur["params"][-1]["type"] == "":
                cur["params"][-1]["type"] = t
            elif not cur["params"]:
                cur["ret"] = t
        elif "DW_AT_artificial" in s and cur["params"] and cur["params"][-1]["type"] != "done":
            cur["params"][-1]["art"] = True
    if cur and cur["mangled"]:
        funcs[cur["mangled"]] = cur

    out = {}
    for m, c in funcs.items():
        member = any(p["art"] for p in c["params"])
        params = [ffi_of(p["type"]) for p in c["params"] if not p["art"] and p["type"] != "done"]
        out[m] = (member, ffi_of(c["ret"]), params)
    return out


DIE_RE = re.compile(r'^0x[0-9a-fA-F]+:(\s*)(DW_TAG_\w+)')
F_NAME_RE = re.compile(r'DW_AT_name\s*\("([^"]*)"\)')
F_LOC_RE = re.compile(r'DW_AT_data_member_location\s*\([^)]*?(0x[0-9a-fA-F]+|\d+)\)')
F_TYPE_RE = re.compile(r'DW_AT_type\s*\([^"]*"([^"]*)"\)')


def parse_fields(text):
    out = []          # (qualified, offset, kind)
    stack = []        # (indent, struct_name or None)
    cur = None

    def finalize(c):
        if c is None:
            return
        while stack and stack[-1][0] >= c["indent"]:
            stack.pop()
        if c["kind"] == "type":
            stack.append((c["indent"], c["name"]))
        elif c["kind"] == "member" and stack and c["name"] and c["loc"] is not None:
            s = stack[-1][1]
            if s and " " not in s and " " not in c["name"]:
                out.append((s + "::" + c["name"], c["loc"], ffi_of(c["type"] or "")))

    for line in text.splitlines():
        m = DIE_RE.match(line)
        if m:
            finalize(cur)
            indent, tag = len(m.group(1)), m.group(2)
            if tag in ("DW_TAG_structure_type", "DW_TAG_class_type", "DW_TAG_union_type"):
                cur = {"kind": "type", "indent": indent, "name": None}
            elif tag == "DW_TAG_member":
                cur = {"kind": "member", "indent": indent, "name": None, "loc": None, "type": None}
            else:
                cur = {"kind": "other", "indent": indent}
        elif cur is not None:
            if cur["kind"] in ("type", "member") and cur["name"] is None:
                nm = F_NAME_RE.search(line)
                if nm:
                    cur["name"] = nm.group(1)
                    continue
            if cur["kind"] == "member":
                lm = F_LOC_RE.search(line)
                if lm:
                    cur["loc"] = int(lm.group(1), 0)
                elif cur["type"] is None:
                    tm = F_TYPE_RE.search(line)
                    if tm:
                        cur["type"] = tm.group(1)
    finalize(cur)
    return out


def main():
    dsym, outpath = sys.argv[1], sys.argv[2]
    text = subprocess.run([DWARFDUMP, "--debug-info", dsym],
                          capture_output=True, text=True, encoding="utf-8").stdout
    funcs = parse(text)

    if not funcs:
        print(f"dwarf_manifest: no DWARF in {dsym}; build with debug info (-g) "
              f"so the signature manifest can be generated", file=sys.stderr)
        sys.exit(1)

    mangled = list(funcs.keys())
    dem = subprocess.run([CXXFILT, "-n"], input="\n".join(mangled),
                         capture_output=True, text=True, encoding="utf-8").stdout.splitlines()
    qmap = dict(zip(mangled, dem))

    fields = parse_fields(text)

    n = 0
    with open(outpath, "w") as f:
        for m, (member, ret, params) in funcs.items():
            q = qmap.get(m, m).split("(")[0].strip()
            if " " in q or not q:
                q = m
            f.write(" ".join([m, q, "1" if member else "0", ret] + params) + "\n")
            n += 1
        seen = set()
        nf = 0
        for name, off, kind in fields:
            if name in seen:
                continue
            seen.add(name)
            f.write(f"@ {name} {off} {kind}\n")
            nf += 1
    print(f"dwarf_manifest: {n} functions, {nf} fields -> {outpath}")


if __name__ == "__main__":
    main()
