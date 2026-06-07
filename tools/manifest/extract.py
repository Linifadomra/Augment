#!/usr/bin/env python3
import sys, json, subprocess, shutil
import dwarf

DWARFDUMP = shutil.which("llvm-dwarfdump") or shutil.which("dwarfdump")
CXXFILT   = shutil.which("llvm-cxxfilt") or shutil.which("c++filt")

def _demangle(mangled_names):
    if not CXXFILT:
        raise RuntimeError("extract: requires llvm-cxxfilt or c++filt")
    if not mangled_names:
        return {}
    dem = subprocess.run([CXXFILT, "-n"], input="\n".join(mangled_names),
                         capture_output=True, text=True, encoding="utf-8").stdout.splitlines()
    return dict(zip(mangled_names, dem))

def assemble(text, demangle=None):
    roots = dwarf.parse_dies(text)
    mangled = []
    def collect(die):
        if die.tag == "DW_TAG_subprogram" and die.attr("DW_AT_linkage_name"):
            mangled.append(die.attr("DW_AT_linkage_name"))
        for c in die.children:
            collect(c)
    for r in roots:
        collect(r)
    if demangle is None:
        demangle = _demangle(sorted(set(mangled)))

    structs = dwarf.extract_structs(roots)
    struct_names = {s["name"] for s in structs}
    functions = dwarf.extract_functions(roots, demangle, struct_names)
    functions.sort(key=lambda f: (f["flat"], f["mangled"]))
    structs = sorted(structs, key=lambda s: s["name"])
    enums = sorted(dwarf.extract_enums(roots), key=lambda e: e["name"])
    globals_ = sorted(dwarf.extract_globals(roots), key=lambda g: g["name"])
    typedefs = sorted(dwarf.extract_typedefs(roots), key=lambda t: t["alias"])
    return {"version": 2, "functions": functions, "structs": structs,
            "enums": enums, "globals": globals_, "typedefs": typedefs}

def main():
    binpath, outpath = sys.argv[1], sys.argv[2]
    is_pdb = binpath.lower().endswith('.pdb')


    if is_pdb:
        if not PDBUTIL:
            sys.exit("extract: requires llvm-pdbutil to process PDB files on Windows")
            
        import pdb_parser
        
        text = subprocess.run([PDBUTIL, "dump", "-types", "-symbols", "-publics", binpath],
                             capture_output=True, text=True, encoding="utf-8", errors="ignore").stdout
        m = pdb_parser.assemble_pdb(text)
    else:
        if not DWARFDUMP:
            sys.exit("extract: requires llvm-dwarfdump")
        if not CXXFILT:
            sys.exit("extract: requires llvm-cxxfilt or c++filt")
        text = subprocess.run([DWARFDUMP, "--debug-info", binpath],
                            capture_output=True, text=True, encoding="utf-8").stdout
        m = assemble(text)
       
    if not m["functions"]:
        sys.exit(f"extract: no DWARF functions in {binpath}; build with -g")
    with open(outpath, "w") as f:
        json.dump(m, f, indent=2)
    print(f"extract: {len(m['functions'])} fns, {len(m['structs'])} structs, "
          f"{len(m['enums'])} enums, {len(m['globals'])} globals -> {outpath}")

if __name__ == "__main__":
    main()
