"""
extractor/ast_walk/pch.py

Helpers to generate a temporary pre-compiled header
used at runtime to avoid duplicated work.
"""
from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
from typing import Optional

from extractor.utility.exclude import is_excluded


def _pch_is_stale(output_pch: str, compile_commands_path: str) -> bool:
    """
    Invalidate the PCH if compile_commands.json has changed since it was built.
    """
    pch = Path(output_pch)
    hash_file = pch.with_suffix(".md5")

    if not pch.exists() or not hash_file.exists():
        return True

    current = hashlib.md5(
        Path(compile_commands_path).read_bytes()
    ).hexdigest()

    return current != hash_file.read_text().strip()


def _write_stale_hash(output_pch: str, compile_commands_path: str) -> None:
    hash_file = Path(output_pch).with_suffix(".md5")
    current = hashlib.md5(
        Path(compile_commands_path).read_bytes()
    ).hexdigest()
    hash_file.write_text(current)


def _run_dep_scan(args):
    src, flags, project_root = args
    import subprocess
    from pathlib import Path

    try:
        cmd = ["clang++", "-M", src] + flags
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return []

        root = Path(project_root).resolve().as_posix().lower()
        headers = []

        for line in result.stdout.splitlines():
            dep = line.strip().rstrip("\\").strip()
            dep_path = Path(dep)
            if dep_path.suffix not in (".h", ".hpp", ".hh"):
                continue

            try:
                dep_norm = dep_path.resolve().as_posix().lower()
            except Exception:
                continue

            if dep_norm.startswith(root):
                headers.append(dep_path.as_posix())

        return headers
    except Exception:
        return []


def _extract_include_order(flag_map: dict, project_root: str) -> list[str]:
    from concurrent.futures import ThreadPoolExecutor, as_completed

    items = list(flag_map.items())[:20]
    seen: dict[str, int] = {}
    position = 0

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [
            pool.submit(_run_dep_scan, (src, flags, project_root))
            for src, flags in items
        ]
        for future in as_completed(futures):
            for h in future.result():
                if h not in seen:
                    seen[h] = position
                    position += 1

    return [h for h, _ in sorted(seen.items(), key=lambda x: x[1])]

def normalize_include(p: str) -> str:
    return Path(p).as_posix()

def build_pch(
    project_root: str,
    output_pch: str,
    compile_commands_path: str,
    compile_flags: list[str],
    flag_map: dict,
    exclude_paths: tuple[str, ...] = (),
) -> Optional[str]:
    import clang.cindex as cl
    import sys
    from extractor.logger import get_logger
    log = get_logger("pch")

    if not _pch_is_stale(output_pch, compile_commands_path):
        log.info("PCH is up to date, skipping rebuild")
        return output_pch

    merged_flags: list[str] = []
    seen_flags: set[str] = set()
    
    if sys.platform == "win32":
        merged_flags.extend([
            "-target", "x86_64-pc-windows-msvc",
            "-fms-compatibility",
            "-fms-extensions",
            "-fms-volatile",
            "-fdeclspec",
            "-D__AST_WALK_PCH_GENERATION__",
            "-D_ALLOW_COMPILER_AND_STL_VERSION_MISMATCH",
            "-D_SILENCE_ALL_CXX17_DEPRECATION_WARNINGS",
            "-DBSWAP16(x)=__builtin_bswap16(x)",
            "-DBSWAP32(x)=__builtin_bswap32(x)",
            "-DBSWAP64(x)=__builtin_bswap64(x)",
        ])

    for flags in flag_map.values():
        i = 0
        while i < len(flags):
            flag = flags[i]
            if flag.startswith(("/", "-Wno-")) and not flag.startswith(("-I", "-D", "-std", "-include")):
                i += 1
                continue
            if flag.startswith(("-std:", "-std=c++11", "-std=c++14", "-std=c++17")):
                i += 1
                continue

            if flag.startswith(("-I", "-D", "-std", "-include")):
                if flag.startswith("-I"):
                    if len(flag) > 2:
                        flag = "-I" + Path(flag[2:]).as_posix()
                    elif i + 1 < len(flags):
                        flag = f"-I{Path(flags[i + 1]).as_posix()}"
                        i += 1
                elif flag.startswith("-D") and "\\" in flag:
                    flag = flag.replace("\\", "/")

                if flag not in seen_flags:
                    seen_flags.add(flag)
                    merged_flags.append(flag)
            i += 1

    log.info("PCH: merged %d unique flags from %d TUs", len(merged_flags), len(flag_map))
    merged_flags.append("-std=c++20")

    ordered_headers = _extract_include_order(flag_map, project_root)
    filtered = [
        h for h in ordered_headers
        if not is_excluded(h, exclude_paths)
    ]

    if not filtered:
        log.warning("PCH: no headers found, skipping")
        return None

    log.info("PCH: %d headers collected", len(filtered))

    umbrella_path = None
    try:
        with tempfile.NamedTemporaryFile(
            suffix=".h", mode="w", delete=False
        ) as f:
            umbrella_path = f.name
            for h in filtered:
                f.write(f'#include "{normalize_include(h)}"\n')

        clang_args = ["-x", "c++-header"] + merged_flags

        from extractor.utility.spinner import Progress
        with Progress("PCH", total=1) as progress:
            index = cl.Index.create()
            tu = index.parse(
                umbrella_path,
                args=clang_args, 
                options=cl.TranslationUnit.PARSE_NONE
            )
            progress.increment()

        errors = [d for d in tu.diagnostics if d.severity >= cl.Diagnostic.Error]
        if errors:
            for d in errors:
                log.warning("PCH compile error: %s", d.spelling)
            log.warning("PCH build failed, falling back to no PCH")
            return None

        Path(output_pch).parent.mkdir(parents=True, exist_ok=True)
        tu.save(output_pch)
        _write_stale_hash(output_pch, compile_commands_path)
        log.info("PCH saved to %s", output_pch)
        return output_pch

    except Exception as exc:
        log.warning("PCH build exception: %s: %s", type(exc).__name__, exc)
        return None

    finally:
        if umbrella_path:
            Path(umbrella_path).unlink(missing_ok=True)
