"""
extractor/ast/compile_db.py

Loads a compile_commands.json and returns a flag map for the AST walker.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

import sys

def _fix_flags(flags: list[str]) -> list[str]:
    result = []
    for tok in flags:
        if tok.startswith('-include') and len(tok) > len('-include') and not tok.startswith('-include-'):
            result.append('-include')
            result.append(tok[len('-include'):])
        else:
            result.append(tok)
    return result

def _win_split(command: str) -> list[str]:
    import ctypes
    shell32 = ctypes.windll.shell32
    shell32.CommandLineToArgvW.restype = ctypes.POINTER(ctypes.c_wchar_p)
    shell32.CommandLineToArgvW.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int)]
    
    argc = ctypes.c_int(0)
    argv_ptr = shell32.CommandLineToArgvW(command, ctypes.byref(argc))
    if not argv_ptr:
        import shlex
        return shlex.split(command)
    try:
        return [argv_ptr[i] for i in range(argc.value)]
    finally:
        ctypes.windll.kernel32.LocalFree(argv_ptr)


def _normalize_msvc_flags(flags: list[str]) -> list[str]:
    import re

    REMAP = {
        "/TP": "-x c++", "/TC": "-x c",
        "-TP": "-x c++", "-TC": "-x c",
        "/EHsc": "-fexceptions", "/EHs": "-fexceptions",
        "-EHsc": "-fexceptions", "-EHs": "-fexceptions",
        "/GR-": "-fno-rtti",
        "/W0": "-w", "/W1": "-Wall", "/W2": "-Wall",
        "/W3": "-Wall", "/W4": "-Wextra", "/WX": "-Werror",
    }
    STD = {
        "/std:c++14": "-std=c++14", "/std:c++17": "-std=c++17",
        "/std:c++20": "-std=c++20", "/std:c++23": "-std=c++23",
        "/std:c++latest": "-std=c++23",
        "-std:c++14": "-std=c++14", "-std:c++17": "-std=c++17",
        "-std:c++20": "-std=c++20", "-std:c++23": "-std=c++23",
        "-std:c++latest": "-std=c++23",
    }
    DROP = re.compile(
        r'^[/-](nologo|bigobj|MD[d]?|MT[d]?|GR$|GS|GL|Gy|Gw'
        r'|RTC\w*|Zc:[^:]+|Z[iIdHp]\w*|F[dorpexa]\w*'
        r'|O[0-9xdstb]*|W[^X]|wd\d+|we\d+|wo\d+'
        r'|external:W\d*|analyze.*|Yu.*|Yc.*|fp:\w+)$'
    )

    result = []
    i = 0
    while i < len(flags):
        tok = flags[i]

        if tok in REMAP:
            result += REMAP[tok].split()
        elif tok in STD:
            result.append(STD[tok])
        elif DROP.match(tok):
            pass
        # /external:I<path> or -external:I<path>
        elif re.match(r'^[/-]external:I(.+)', tok):
            result += ["-isystem", re.match(r'^[/-]external:I(.+)', tok).group(1)]
        elif re.match(r'^[/-]external:I$', tok) and i + 1 < len(flags):
            result += ["-isystem", flags[i + 1]]
            i += 1
        # /I or -I
        elif re.match(r'^[/-]I(.+)', tok):
            result.append("-I" + re.match(r'^[/-]I(.+)', tok).group(1))
        elif tok in ("/I", "-I") and i + 1 < len(flags):
            result += ["-I", flags[i + 1]]
            i += 1
        # /D or -D
        elif re.match(r'^[/-]D(.+)', tok):
            result.append("-D" + re.match(r'^[/-]D(.+)', tok).group(1))
        elif tok in ("/D", "-D") and i + 1 < len(flags):
            result += ["-D", flags[i + 1]]
            i += 1
        elif tok.startswith("-std="):
            result.append(tok)
        elif tok.startswith("-"):
            result.append(tok)

        i += 1

    return result


def load(compile_commands_path: str | Path) -> Dict[str, List[str]]:
    """
    Parse a compile_commands.json and return {absolute_file_path: [flags]}.

    Flags are the compiler arguments with the following stripped out:
      - the compiler executable (argv[0])
      - -o / --output and its following argument
      - the source file itself (last positional argument)

    Everything else (includes, defines, std, warnings, …) is preserved
    and forwarded to libclang unchanged.
    """
    path = Path(compile_commands_path).resolve()
    with path.open(encoding="utf-8") as f:
        entries = json.load(f)

    result: Dict[str, List[str]] = {}

    for entry in entries:
        file_path = _resolve_file(entry, path.parent)
        flags = _extract_flags(entry, file_path)
        # last writer wins for duplicate entries (matches clang's behaviour)
        result[file_path] = flags

    return result

def _resolve_file(entry: dict, db_dir: Path) -> str:
    """Return the absolute path to the source file for this entry."""
    file_val = entry.get("file", "")
    p = Path(file_val)
    if not p.is_absolute():
        directory = entry.get("directory", "")
        base = Path(directory) if directory else db_dir
        p = base / p
    return str(p.resolve())


def _extract_flags(entry: dict, file_path: str) -> List[str]:
    if "arguments" in entry:
        argv = list(entry["arguments"])
    elif "command" in entry:
        if sys.platform == "win32":
            import subprocess
            argv = _win_split(entry["command"])
        else:
            import shlex
            argv = shlex.split(entry["command"])
    else:
        return []

    flags = _strip_non_flags(argv, file_path)
    flags = _fix_flags(flags)

    if sys.platform == "win32":
        flags = _normalize_msvc_flags(flags)

    return flags


def _strip_non_flags(argv: List[str], file_path: str) -> List[str]:
    flags: List[str] = []
    skip_next = False
    file_path_obj = Path(file_path)

    for i, arg in enumerate(argv):
        if i == 0:
            continue
        if skip_next:
            skip_next = False
            continue
        if arg in ("-o", "--output"):
            skip_next = True
            continue
        if arg.startswith("-o") and len(arg) > 2:
            continue
        if arg in ("-c", "-MD", "-MMD", "-MP"):
            continue
        if arg in ("-MF", "-MT", "-MQ"):
            skip_next = True
            continue
        if not arg.startswith("-"):
            arg_path = Path(arg)
            if arg_path.suffix in (".c", ".cpp", ".cc", ".cxx", ".h", ".hpp"):
                continue
        flags.append(arg)
    return flags
