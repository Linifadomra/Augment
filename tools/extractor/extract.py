"""
extractor/extract.py

Entry point. Wires compile_db -> walker -> binary backend -> merge -> JSON.

Usage:
    python -m extractor.extract \\
        --binary   path/to/binary_or.pdb \\
        --compile-commands path/to/compile_commands.json \\
        --output   manifest.json \\
        [--debug-format dwarf|pdb]   # inferred from binary extension if omitted
        [--jobs N]                   # parallel workers (default: cpu_count / 2)
        [--log-file path/to/run.log] # also write log output to a file
        [--verbose]                  # set log level to DEBUG
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

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

def _walk_one(args: Tuple[str, List[str]]) -> dict:
    """
    Worker entry point: parse one translation unit and return its records.
    """
    source_file, flags = args

    from extractor.logger import get_logger
    log = get_logger("walker.worker")

    log.debug("parsing TU: %s", source_file)
    log.debug("  flags: %s", " ".join(flags))

    _EMPTY: dict = {"structs": [], "functions": [], "enums": [], "typedefs": []}

    from extractor.ast_walk.walker import walk
    try:
        result = walk(source_file, flags)
        counts = {k: len(v) for k, v in result.items()}
        log.debug("  done: %s", counts)
        return result

    except RuntimeError as exc:
        log.error(
            "walker error in %s: %s",
            source_file, exc,
        )
        return _EMPTY

    except Exception as exc:
        log.error(
            "Failed to parse TU. File will be skipped.\n"
            "  path : %s\n"
            "  flags: %s\n"
            "  error: %s: %s",
            source_file,
            " ".join(flags),
            type(exc).__name__,
            exc,
        )
        return _EMPTY

def _progress_printer(counter: list, total: int, stop: threading.Event) -> None:
    start = time.time()
    i = 0
    while not stop.is_set():
        done = counter[0]
        elapsed = time.time() - start
        rate = done / elapsed if elapsed > 0 else 0
        eta = (total - done) / rate if rate > 0 else 0
        pct = done / total * 100 if total > 0 else 0
        bar_filled = int(pct / 2)
        bar = "█" * bar_filled + "░" * (50 - bar_filled)
        spin = _SPINNER[i % len(_SPINNER)]
        print(
            f"\r{spin} [{bar}] {pct:5.1f}%  {done}/{total} TUs  "
            f"ETA {int(eta//60)}m{int(eta%60):02d}s   ",
            end="", flush=True
        )
        i += 1
        time.sleep(0.1)
    print(f"\r✓ [{('█' * 50)}] 100.0%  {total}/{total} TUs  done{' ' * 20}")

def run(
    binary_path: str,
    compile_commands_path: str,
    output_path: str,
    debug_format: str | None = None,
    jobs: int | None = None,
    log_file: Optional[str] = None,
    verbose: bool = False,
) -> Dict:
    from extractor.logger import configure, get_logger
    configure(
        level="DEBUG" if verbose else "WARNING",
        log_file=log_file,
        verbose=verbose,
        enabled=bool(log_file or verbose),
    )
    log = get_logger("extract")

    _require_libclang()

    # 1. Load compile database
    from extractor.ast_walk.compile_db import load as load_compile_db
    log.info("loading compile_commands: %s", compile_commands_path)
    flag_map = load_compile_db(compile_commands_path)

    if not flag_map:
        print("Warning: compile_commands.json is empty. No files to walk")

    # 2. Walk all translation units in parallel
    combined: Dict[str, list] = {
        "structs": [], "functions": [], "enums": [], "typedefs": []
    }
    seen: Dict[str, set] = {k: set() for k in combined}

    workers = jobs or round(os.cpu_count() / 2) or 1
    items   = list(flag_map.items())
    total   = len(items)

    log.info("walking %d TUs with %d workers", total, workers)
    print(f"[extract] walking {total} TUs with {workers} workers...")

    counter      = [0]
    skipped      = [0]   # TUs that returned empty due to a parse error
    stop         = threading.Event()
    printer      = threading.Thread(
        target=_progress_printer, args=(counter, total, stop), daemon=True
    )
    printer.start()

    from concurrent.futures import ProcessPoolExecutor, as_completed
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_walk_one, item): item[0] for item in items}
        for future in as_completed(futures):
            counter[0] += 1
            source_file = futures[future]

            try:
                result = future.result()
            except Exception as exc:
                # Defensive: _walk_one itself should not raise, but if it does
                # we log and continue rather than crashing the main process.
                log.error(
                    "unexpected exception from worker for %s: %s: %s",
                    source_file, type(exc).__name__, exc,
                )
                skipped[0] += 1
                continue

            record_counts = {k: len(v) for k, v in result.items()}
            all_empty = all(n == 0 for n in record_counts.values())
            if all_empty:
                skipped[0] += 1
                log.debug("TU produced no records (skipped or errored): %s", source_file)

            for key in combined:
                for record in result[key]:
                    dedup_key = _dedup_key(key, record)
                    if dedup_key not in seen[key]:
                        seen[key].add(dedup_key)
                        combined[key].append(record)

    stop.set()
    printer.join()

    if skipped[0]:
        log.warning(
            "%d/%d TUs produced no records (parse errors or genuinely empty); "
            "check log output for ERROR entries to identify failing files",
            skipped[0], total,
        )
        print(
            f"[extract] Warning: {skipped[0]}/{total} TUs were skipped or empty. "
            f"{'See ' + log_file if log_file else 'Rerun with --log-file <path> to capture details.'}",
            file=sys.stderr,
        )

    log.info(
        "walk complete: structs=%d functions=%d enums=%d typedefs=%d",
        len(combined["structs"]),
        len(combined["functions"]),
        len(combined["enums"]),
        len(combined["typedefs"]),
    )

    # 3. Extract RVAs from binary
    log.info("extracting RVAs from %s", binary_path)
    backend = _select_backend(binary_path, debug_format)
    rva_map = backend.extract_rvas(binary_path)
    log.info("got %d RVA entries", len(rva_map))

    # 4. Merge
    from extractor.merge import merge
    manifest = merge(combined, rva_map)

    # 5. Write output
    from extractor.output.pack import pack
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    json_path = out.with_suffix(".json")
    agmf_path = out
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    with open(agmf_path, "wb") as f:
        f.write(pack(manifest))

    summary = (
        f"[extract] {len(manifest['functions'])} fns "
        f"({sum(1 for f in manifest['functions'] if f['rva'] is not None)} with RVA), "
        f"{len(manifest['structs'])} structs, "
        f"{len(manifest['enums'])} enums, "
        f"{len(manifest['typedefs'])} typedefs "
        f"-> {json_path}, {agmf_path}"
    )
    print(summary)
    log.info(summary)

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
    p.add_argument("--jobs", "-j",       type=int, default=None,
                   help="Parallel worker count (default: cpu_count / 2)")
    p.add_argument("--log-file",         dest="log_file", default=None,
                   help="Write structured log output to this file")
    p.add_argument("--verbose", "-v",    action="store_true", default=False,
                   help="Set log level to DEBUG (very noisy; pair with --log-file)")
    return p

def main(argv: list | None = None) -> None:
    args = _build_parser().parse_args(argv)
    run(
        binary_path=args.binary,
        compile_commands_path=args.compile_commands,
        output_path=args.output,
        debug_format=args.debug_format,
        jobs=args.jobs,
        log_file=args.log_file,
        verbose=args.verbose,
    )

if __name__ == "__main__":
    main()
