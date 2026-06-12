"""
extractor/extract.py

Entry point. Wires compile_db -> walker -> binary backend -> merge -> JSON.

Subcommands
===
Phase 1 runs the libclang AST walk, writes ast_manifest.json and
        augment_generated_registry.cpp. Runs pre-build.

Phase 2 loads ast_manifest.json, extracts RVAs from the built binary,
        merges, and packs. Runs POST_BUILD.

Most consumers will just use augment_manifest (Located in `cmake/AugmentManifest.cmake`)

Usage
===
# Phase 1 (pre-build)
python -m extractor.extract phase1 \\
    --compile-commands build/compile_commands.json \\
    --project-root     . \\
    --ast-out          build/ast_manifest.json \\
    --registry-out     src/augment_generated_registry.cpp

# Phase 2 (post-build)
python -m extractor.extract phase2 \\
    --ast-manifest build/ast_manifest.json \\
    --binary       build/game.elf \\
    --output       build/augment.bin
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, Optional, 


_KEY_FIELD = {"functions": "mangled", "structs": "name", "enums": "name", "typedefs": "alias"}


def _richness(fn: dict) -> int:
    return (
        bool(fn.get("loc")) +
        bool(fn.get("self_view")) +
        bool(fn.get("member"))
    )


def _require_libclang() -> None:
    try:
        import clang.cindex  # noqa: F401
    except ImportError:
        sys.exit(
            "[extract] Requires the libclang Python bindings.\n"
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
        sys.exit(f"[extract] unknown --debug-format {fmt!r} (expected dwarf or pdb)")


_EMPTY: dict = {"structs": (), "functions": (), "enums": (), "typedefs": ()}


def _walk_one(args: Tuple[str, List[str], str]) -> dict:
    source_file, flags, project_root = args

    from extractor.logger import get_logger
    log = get_logger("walker.worker")

    log.debug("parsing TU: %s", source_file)
    log.debug("  flags: %s", " ".join(flags))

    from extractor.ast_walk.walker import set_project_root, walk
    set_project_root(project_root)

    try:
        result = walk(source_file, flags)
        log.debug("  done: %s", {k: len(v) for k, v in result.items()})
        return result
    except RuntimeError as exc:
        log.error("walker error in %s: %s", source_file, exc)
        return _EMPTY
    except Exception as exc:
        log.error(
            "Failed to parse TU. File will be skipped.\n"
            "  path : %s\n  flags: %s\n  error: %s: %s",
            source_file, " ".join(flags), type(exc).__name__, exc,
        )
        return _EMPTY


def _is_excluded(src: str, exclude_paths: tuple[str, ...]) -> bool:
    return any(frag in src for frag in exclude_paths)


def phase1(
    compile_commands_path: str,
    project_root: str,
    ast_out: str,
    registry_out: Optional[str] = None,
    jobs: int | None = None,
    log_file: Optional[str] = None,
    verbose: bool = False,
    exclude_prefixes: tuple[str, ...] = (),
    exclude_paths: tuple[str, ...] = ()
) -> Dict:
    from extractor.logger import configure, get_logger
    configure(
        level="DEBUG" if verbose else "WARNING",
        log_file=log_file,
        verbose=verbose,
        enabled=bool(log_file or verbose),
    )
    log = get_logger("extract.phase1")

    _require_libclang()

    from extractor.ast_walk.walker import set_project_root
    set_project_root(project_root)

    from extractor.ast_walk.compile_db import load as load_compile_db
    log.info("loading compile_commands: %s", compile_commands_path)
    flag_map = load_compile_db(compile_commands_path)
    if not flag_map:
        log.warning("[extract] Warning: compile_commands.json is empty. No files to walk.")

    combined: Dict[str, list] = {"structs": [], "functions": [], "enums": [], "typedefs": []}
    seen_index: Dict[str, Dict[str, int]] = {k: {} for k in combined}
    richness_cache: Dict[str, List[int]] = {k: [] for k in combined}

    workers = jobs or int(os.environ.get("AUGMENT_JOBS", 0)) or max(1, round(os.cpu_count() / 2))
    items = [
        (src, flags, project_root)
        for src, flags in flag_map.items()
        if not _is_excluded(src, exclude_paths)
    ]
    total = len(items)
    chunksize = max(4, total // (workers * 8))
    skipped = 0

    log.info("walking %d TUs with %d workers (chunksize=%d)", total, workers, chunksize)

    from extractor.utility.spinner import Progress
    from multiprocessing import Pool

    with Progress("TUs", total=total) as progress:
        with Pool(processes=workers) as pool:
            for result in pool.imap_unordered(_walk_one, items, chunksize=chunksize):
                progress.increment()
                try:
                    if not any(result.values()):
                        skipped += 1
                        continue
                    for key in combined:
                        for record in result[key]:
                            dk = record.get(_KEY_FIELD.get(key, ""), "")
                            if not dk:
                                continue
                            existing = seen_index[key].get(dk)
                            if existing is None:
                                seen_index[key][dk] = len(combined[key])
                                combined[key].append(record)
                                richness_cache[key].append(_richness(record))
                            elif key == "functions":
                                r = _richness(record)
                                if r > richness_cache[key][existing]:
                                    combined[key][existing] = record
                                    richness_cache[key][existing] = r
                except Exception as exc:
                    log.error("merge error: %s: %s", type(exc).__name__, exc)
                    skipped += 1

    if skipped:
        msg = (
            f"[extract] Warning: {skipped}/{total} TUs were skipped or empty. "
            + (f"See {log_file}" if log_file else "Rerun with --log-file <path> to capture details.")
        )
        log.warning(msg)
        print(msg, file=sys.stderr)

    log.info(
        "walk complete: structs=%d functions=%d enums=%d typedefs=%d",
        len(combined["structs"]), len(combined["functions"]),
        len(combined["enums"]), len(combined["typedefs"]),
    )

    ast_path = Path(ast_out)
    ast_path.parent.mkdir(parents=True, exist_ok=True)
    with open(ast_path, "w", encoding="utf-8") as f:
        json.dump(combined, f, indent=2)

    summary = (
        f"[extract] Phase 1: {len(combined['functions'])} fns, "
        f"{len(combined['structs'])} structs, "
        f"{len(combined['enums'])} enums, "
        f"{len(combined['typedefs'])} typedefs "
        f"-> {ast_path}"
    )
    print(summary)
    log.info(summary)

    if registry_out:
        from extractor.codegen.registry import generate_registry
        generate_registry(combined, registry_out)

    return combined


# Phase 2: binary backend + merge + pack
def phase2(
    ast_manifest_path: str,
    binary_path: str,
    output_path: str,
    debug_format: str | None = None,
    log_file: Optional[str] = None,
    verbose: bool = False,
    exclude_prefixes: tuple[str, ...] = (),
    exclude_paths: tuple[str, ...] = ()
) -> Dict:
    """
    Load the ast_manifest.json produced by phase1, extract RVAs from the
    built binary, merge, and pack the final manifest.

    Returns the merged manifest dict.
    """
    from extractor.logger import configure, get_logger
    configure(
        level="DEBUG" if verbose else "WARNING",
        log_file=log_file,
        verbose=verbose,
        enabled=bool(log_file or verbose),
    )
    log = get_logger("extract.phase2")

    log.info("loading ast manifest: %s", ast_manifest_path)
    with open(ast_manifest_path, "r", encoding="utf-8") as f:
        ast = json.load(f)

    log.info("extracting RVAs from %s", binary_path)
    backend = _select_backend(binary_path, debug_format)
    rva_map = backend.extract_rvas(binary_path)
    log.info("got %d RVA entries", len(rva_map))

    from extractor.merge import merge
    manifest = merge(ast, rva_map, exclude_prefixes=exclude_prefixes)

    from extractor.output.pack import pack
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    json_path = out.with_suffix(".json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    with open(out, "wb") as f:
        f.write(pack(manifest))

    summary = (
        f"[extract] Phase 2: {len(manifest['functions'])} fns "
        f"({sum(1 for fn in manifest['functions'] if fn['rva'] is not None)} with RVA), "
        f"{len(manifest['structs'])} structs, "
        f"{len(manifest['enums'])} enums, "
        f"{len(manifest['typedefs'])} typedefs "
        f"-> {json_path}, {out}"
    )
    print(summary)
    log.info(summary)

    return manifest


def _add_common_args(p: argparse.ArgumentParser) -> None:
    """Logging/filtering flags shared by all subcommands."""
    p.add_argument("--exclude-prefix", dest="exclude_prefixes",
                   action="append", default=[],
                   help="Exclude functions whose demangled name starts with this prefix (repeatable)")
    p.add_argument("--log-file", dest="log_file", default=None,
                   help="Write structured log output to this file")
    p.add_argument("--verbose", "-v", action="store_true", default=False,
                   help="Set log level to DEBUG (very noisy; pair with --log-file)")
    p.add_argument("--exclude-path", dest="exclude_paths",
               action="append", default=[],
               help="Exclude any cursor whose path contains this fragment (repeatable)")


def _build_parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="extract",
        description="Extract a function/type manifest from a binary and its sources.",
    )
    sub = root.add_subparsers(dest="subcommand")

    # Phase 1
    p1 = sub.add_parser("phase1", help="AST walk (pre-build). Writes ast_manifest.json and optional registry codegen.")
    p1.add_argument("--compile-commands", required=True, dest="compile_commands",
                    help="Path to compile_commands.json")
    p1.add_argument("--project-root", dest="project_root", default=None,
                    help="Project root directory for filtering system headers")
    p1.add_argument("--ast-out", required=True, dest="ast_out",
                    help="Path to write the AST manifest JSON (no RVAs)")
    p1.add_argument("--registry-out", dest="registry_out", default=None,
                    help="Path to write augment_generated_registry.cpp (optional)")
    p1.add_argument("--jobs", "-j", type=int, default=None,
                    help="Parallel worker count (default: cpu_count / 2)")
    _add_common_args(p1)

    # Phase 2
    p2 = sub.add_parser("phase2", help="Binary RVA extraction + merge + pack (post-build).")
    p2.add_argument("--ast-manifest", required=True, dest="ast_manifest",
                    help="Path to ast_manifest.json produced by phase1")
    p2.add_argument("--binary", required=True,
                    help="Path to the compiled binary or .pdb file")
    p2.add_argument("--output", required=True,
                    help="Path to write the final manifest (.bin + .json)")
    p2.add_argument("--debug-format", dest="debug_format",
                    choices=["dwarf", "pdb"], default=None,
                    help="Force debug-info format (inferred from extension if omitted)")
    _add_common_args(p2)

    return root


def main(argv: list | None = None) -> None:
    args = _build_parser().parse_args(argv)

    if args.subcommand == "phase1":
        phase1(
            compile_commands_path=args.compile_commands,
            project_root=args.project_root or ".",
            ast_out=args.ast_out,
            registry_out=args.registry_out,
            jobs=args.jobs,
            log_file=args.log_file,
            verbose=args.verbose,
            exclude_prefixes=tuple(args.exclude_prefixes),
            exclude_paths=tuple(args.exclude_paths)
        )

    elif args.subcommand == "phase2":
        phase2(
            ast_manifest_path=args.ast_manifest,
            binary_path=args.binary,
            output_path=args.output,
            debug_format=args.debug_format,
            log_file=args.log_file,
            verbose=args.verbose,
            exclude_prefixes=tuple(args.exclude_prefixes),
            exclude_paths=tuple(args.exclude_paths)
        )

if __name__ == "__main__":
    main()
