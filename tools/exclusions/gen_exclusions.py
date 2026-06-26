#!/usr/bin/env python3
"""
gen_exclusions.py
A zero-dependency runtime exclusion table consumed by the
Augment dispatch layer to block symbol hooking.

Usage:
    gen_exclusions.py
        --prefix-file    <path>   # newline-delimited prefix patterns
        --substr-file    <path>   # newline-delimited substring patterns
        --output         <path>   # destination .hpp file
"""

from __future__ import annotations
from datetime import datetime, timezone
import argparse
import os


def _read_lines(path: str) -> list[str]:
    """Read non-empty, non-comment lines from a file."""
    with open(path, encoding="utf-8") as fh:
        return [
            ln.strip()
            for ln in fh
            if ln.strip() and not ln.strip().startswith("#")
        ]


def _escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def generate(
    prefixes: list[str],
    substrings: list[str],
    output_path: str,
) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _string_array(name: str, items: list[str]) -> str:
        if not items:
            return (
                f"inline constexpr const char* {name}[] = {{nullptr}};\n"
                f"inline constexpr std::size_t {name}_count = 0;\n"
            )
        entries = "\n".join(f'    "{_escape(e)}",' for e in items)
        return (
            f"inline constexpr const char* {name}[] = {{\n"
            f"{entries}\n"
            f"    nullptr,\n"
            f"}};\n"
            f"inline constexpr std::size_t {name}_count = {len(items)};\n"
        )

    prefix_block    = _string_array("augment_excluded_prefixes",    prefixes)
    substring_block = _string_array("augment_excluded_substrings",  substrings)

    header = f"""\
// augment_exclusions.hpp. AUTO-GENERATED, DO NOT EDIT
// Generated: {ts}
// Source:    cmake/AugmentExclusions.cmake + tools/exclusions/gen_exclusions.py
//
// Consumed by the Augment runtime dispatch layer.
#pragma once
#include <cstddef>
#include <cstring>

namespace augment {{

// == Prefix exclusions ==
// A symbol whose demangled name *starts with* any of these strings is blocked.
{prefix_block}
// == Substring exclusions ==
// A symbol whose demangled name *contains* any of these strings is blocked.
{substring_block}
// == Runtime check ==
/// Returns true when the symbol identified by `demangled_name` must not be resolved.
/// See `platform/sym_resolve.cpp`
[[nodiscard]]
inline bool augment_should_exclude(const char* demangled_name) noexcept {{
    if (!demangled_name) return true;

    for (std::size_t i = 0; i < augment_excluded_prefixes_count; ++i) {{
        const char* pat = augment_excluded_prefixes[i];
        if (std::strncmp(demangled_name, pat, std::strlen(pat)) == 0)
            return true;
    }}

    for (std::size_t i = 0; i < augment_excluded_substrings_count; ++i) {{
        if (std::strstr(demangled_name, augment_excluded_substrings[i]))
            return true;
    }}

    return false;
}}

}} // namespace augment
"""

    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(header)

    print(f"[Augment] exclusions -> {output_path}  "
          f"({len(prefixes)} prefixes, {len(substrings)} substrings)")


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate augment_exclusions.hpp")
    ap.add_argument("--prefix-file",    required=True)
    ap.add_argument("--substr-file",    required=True)
    ap.add_argument("--output",         required=True)
    args = ap.parse_args()

    prefixes   = _read_lines(args.prefix_file)
    substrings = _read_lines(args.substr_file)
    generate(prefixes, substrings, args.output)


if __name__ == "__main__":
    main()
