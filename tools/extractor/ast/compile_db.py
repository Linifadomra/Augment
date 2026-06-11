"""
extractor/ast/compile_db.py

Loads a compile_commands.json and returns a flag map for the AST walker.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List


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
    """
    Extract the compiler flags from an entry that uses either the
    'command' (string) or 'arguments' (list) form.
    """
    if "arguments" in entry:
        argv = list(entry["arguments"])
    elif "command" in entry:
        import shlex
        argv = shlex.split(entry["command"])
    else:
        return []

    return _strip_non_flags(argv, file_path)

def _strip_non_flags(argv: List[str], file_path: str) -> List[str]:
    """
    Remove the compiler executable, output flag pairs, and the source
    file argument from an argument vector, returning only the flags.
    """
    flags: List[str] = []
    skip_next = False

    for i, arg in enumerate(argv):
        if i == 0:
            # compiler executable
            continue
        if skip_next:
            skip_next = False
            continue
        if arg in ("-o", "--output"):
            skip_next = True
            continue
        if arg.startswith("-o") and len(arg) > 2:
            # -oFILE form
            continue
        if arg == file_path or Path(arg).resolve() == Path(file_path).resolve():
            continue
        flags.append(arg)

    return flags
