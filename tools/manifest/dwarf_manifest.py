#!/usr/bin/env python3
import subprocess, sys, re

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


def main():
    dsym, outpath = sys.argv[1], sys.argv[2]
    text = subprocess.run(["dwarfdump", "--debug-info", dsym],
                          capture_output=True, text=True).stdout
    funcs = parse(text)

    if not funcs:
        print(f"dwarf_manifest: no DWARF in {dsym}; build with debug info (-g) "
              f"so the signature manifest can be generated", file=sys.stderr)
        sys.exit(1)

    mangled = list(funcs.keys())
    dem = subprocess.run(["c++filt", "-n"], input="\n".join(mangled),
                         capture_output=True, text=True).stdout.splitlines()
    qmap = dict(zip(mangled, dem))

    n = 0
    with open(outpath, "w") as f:
        for m, (member, ret, params) in funcs.items():
            q = qmap.get(m, m).split("(")[0].strip()
            if " " in q or not q:
                q = m
            f.write(" ".join([m, q, "1" if member else "0", ret] + params) + "\n")
            n += 1
    print(f"dwarf_manifest: {n} functions -> {outpath}")


if __name__ == "__main__":
    main()
