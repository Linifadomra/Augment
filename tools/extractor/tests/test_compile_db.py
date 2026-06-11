"""
extractor/tests/test_ast_compile_db.py

Gate for Step 5: compile_db.load()

Strategy: write compile_commands.json fixtures to a tmp directory,
call load(), assert on the flag map.

Checks:
  - 'arguments' form: flags extracted correctly
  - 'command' string form: flags extracted correctly
  - compiler executable stripped
  - -o FILE stripped (space-separated)
  - -oFILE stripped (joined form)
  - source file argument stripped
  - includes, defines, -std preserved
  - relative file path resolved against entry 'directory'
  - relative file path resolved against db location when no 'directory'
  - duplicate entries: last writer wins
  - entry with no 'command' or 'arguments': empty flag list, file still present
  - empty compile_commands.json: empty dict
"""
import json
from pathlib import Path

import pytest

from extractor.ast.compile_db import load

def _write_db(tmp_path: Path, entries: list) -> Path:
    p = tmp_path / "compile_commands.json"
    p.write_text(json.dumps(entries), encoding="utf-8")
    return p

def test_arguments_form(tmp_path):
    src = tmp_path / "foo.cpp"
    db = _write_db(tmp_path, [{
        "file": str(src),
        "directory": str(tmp_path),
        "arguments": ["clang++", "-std=c++17", "-Iinclude", str(src)],
    }])
    result = load(db)
    assert str(src) in result
    assert result[str(src)] == ["-std=c++17", "-Iinclude"]

def test_command_string_form(tmp_path):
    src = tmp_path / "bar.cpp"
    db = _write_db(tmp_path, [{
        "file": str(src),
        "directory": str(tmp_path),
        "command": f"clang++ -DFOO=1 -Iinclude {src}",
    }])
    result = load(db)
    assert result[str(src)] == ["-DFOO=1", "-Iinclude"]

def test_compiler_stripped(tmp_path):
    src = tmp_path / "a.cpp"
    db = _write_db(tmp_path, [{
        "file": str(src),
        "arguments": ["g++", "-Wall", str(src)],
    }])
    flags = load(db)[str(src)]
    assert "g++" not in flags

def test_output_flag_space_separated_stripped(tmp_path):
    src = tmp_path / "a.cpp"
    db = _write_db(tmp_path, [{
        "file": str(src),
        "arguments": ["clang++", "-o", "a.o", "-std=c++20", str(src)],
    }])
    flags = load(db)[str(src)]
    assert "-o" not in flags
    assert "a.o" not in flags
    assert "-std=c++20" in flags

def test_output_flag_joined_stripped(tmp_path):
    src = tmp_path / "a.cpp"
    db = _write_db(tmp_path, [{
        "file": str(src),
        "arguments": ["clang++", "-oa.o", "-std=c++20", str(src)],
    }])
    flags = load(db)[str(src)]
    assert "-oa.o" not in flags
    assert "-std=c++20" in flags

def test_source_file_stripped(tmp_path):
    src = tmp_path / "a.cpp"
    db = _write_db(tmp_path, [{
        "file": str(src),
        "arguments": ["clang++", "-Wall", str(src)],
    }])
    flags = load(db)[str(src)]
    assert str(src) not in flags

def test_includes_defines_std_preserved(tmp_path):
    src = tmp_path / "a.cpp"
    db = _write_db(tmp_path, [{
        "file": str(src),
        "arguments": ["clang++", "-std=c++17", "-DNDEBUG", "-I/usr/include", "-Wextra", str(src)],
    }])
    flags = load(db)[str(src)]
    assert "-std=c++17" in flags
    assert "-DNDEBUG" in flags
    assert "-I/usr/include" in flags
    assert "-Wextra" in flags

def test_relative_file_resolved_against_directory(tmp_path):
    src = tmp_path / "src" / "foo.cpp"
    src.parent.mkdir()
    db = _write_db(tmp_path, [{
        "file": "src/foo.cpp",
        "directory": str(tmp_path),
        "arguments": ["clang++", "src/foo.cpp"],
    }])
    result = load(db)
    assert str(src.resolve()) in result

def test_relative_file_resolved_against_db_location(tmp_path):
    src = tmp_path / "foo.cpp"
    db = _write_db(tmp_path, [{
        "file": "foo.cpp",
        "arguments": ["clang++", "foo.cpp"],
    }])
    result = load(db)
    assert str(src.resolve()) in result

def test_duplicate_entries_last_writer_wins(tmp_path):
    src = tmp_path / "a.cpp"
    db = _write_db(tmp_path, [
        {"file": str(src), "arguments": ["clang++", "-DFIRST", str(src)]},
        {"file": str(src), "arguments": ["clang++", "-DSECOND", str(src)]},
    ])
    flags = load(db)[str(src)]
    assert "-DSECOND" in flags
    assert "-DFIRST" not in flags

def test_entry_without_command_or_arguments(tmp_path):
    src = tmp_path / "a.cpp"
    db = _write_db(tmp_path, [{"file": str(src)}])
    result = load(db)
    assert str(src) in result
    assert result[str(src)] == []

def test_empty_db(tmp_path):
    db = _write_db(tmp_path, [])
    assert load(db) == {}
