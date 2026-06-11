"""
extractor/extract.py

Entry point. Wires compile_db → walker → binary backend → merge → JSON.

Usage:
    python -m extractor.extract \\
        --binary   path/to/binary_or.pdb \\
        --compile-commands path/to/compile_commands.json \\
        --output   manifest.json \\
        [--debug-format dwarf|pdb]   # inferred from binary extension if omitted
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List

def _require_libclang() -> None:
    try:
        import clang.cindex  # noqa: F401
    except ImportError:
        sys.exit(
            "extract: requires the libclang Python bindings.\n"
            "  pip install libclang"
        )

def _select_backend(binary_path: str, debug_format: str | None):
    ext = Path(binary_path).suffix.lower()
    fmt = debug_format or ("pdb" if ext == ".pdb" else "dwarf")

    if fmt == "pdb":
        from extractor.binary.pdb import PdbBackend
        return PdbBackend()
    elif fmt == "dwarf":
        from extractor.binary.dwarf import DwarfBackend
        return DwarfBackend()
    else:
        sys.exit(f"extract: unknown --debug-format {fmt!r} (expected dwarf or pdb)")

def run(
    binary_path: str,
    compile_commands_path: str,
    output_path: str,
    debug_format: str | None = None,
) -> Dict:
    _require_libclang()

    # 1. Load compile database
    from extractor.ast.compile_db import load as load_compile_db
    flag_map = load_compile_db(compile_commands_path)

    if not flag_map:
        print("warning: compile_commands.json is empty — no files to walk")

    # 2. Walk all translation units
    from extractor.ast.walker import walk
    import clang.cindex as _cx

    index = _cx.Index.create()
    combined: Dict[str, list] = {
        "structs": [], "functions": [], "enums": [], "typedefs": []
    }
    seen: Dict[str, set] = {k: set() for k in combined}

    for source_file, flags in flag_map.items():
        try:
            result = walk(source_file, flags, index=index)
        except RuntimeError as e:
            print(f"warning: {e}", file=sys.stderr)
            continue

        for key in combined:
            for record in result[key]:
                dedup_key = _dedup_key(key, record)
                if dedup_key not in seen[key]:
                    seen[key].add(dedup_key)
                    combined[key].append(record)

    # 3. Extract RVAs from binary
    backend = _select_backend(binary_path, debug_format)
    rva_map = backend.extract_rvas(binary_path)

    # 4. Merge
    from extractor.merge import merge
    manifest = merge(combined, rva_map)

    # 5. Write output — JSON for inspection, binary for runtime
    from extractor.output.pack import pack
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    json_path = out.with_suffix(".json")
    agmf_path = out.with_suffix(".agmf")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    with open(agmf_path, "wb") as f:
        f.write(pack(manifest))

    print(
        f"extract: {len(manifest['functions'])} fns "
        f"({sum(1 for f in manifest['functions'] if f['rva'] is not None)} with RVA), "
        f"{len(manifest['structs'])} structs, "
        f"{len(manifest['enums'])} enums, "
        f"{len(manifest['typedefs'])} typedefs "
        f"-> {json_path}, {agmf_path}"
    )

    return manifest

def _dedup_key(section: str, record: dict) -> str:
    if section == "functions":
        return record.get("mangled", "")
    if section == "structs":
        return record.get("name", "")
    if section == "enums":
        return record.get("name", "")
    if section == "typedefs":
        return record.get("alias", "")
    return str(record)

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="extract",
        description="Extract a function/type manifest from a binary and its sources.",
    )
    p.add_argument("--binary",           required=True,
                   help="Path to the compiled binary or .pdb file")
    p.add_argument("--compile-commands", required=True, dest="compile_commands",
                   help="Path to compile_commands.json")
    p.add_argument("--output",           required=True,
                   help="Path to write the manifest JSON")
    p.add_argument("--debug-format",     dest="debug_format",
                   choices=["dwarf", "pdb"], default=None,
                   help="Force debug-info format (inferred from extension if omitted)")
    return p

def main(argv: list | None = None) -> None:
    args = _build_parser().parse_args(argv)
    run(
        binary_path=args.binary,
        compile_commands_path=args.compile_commands,
        output_path=args.output,
        debug_format=args.debug_format,
    )

if __name__ == "__main__":
    main()
