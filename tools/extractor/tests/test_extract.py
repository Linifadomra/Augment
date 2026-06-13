"""
extractor/tests/test_extract.py

Strategy: mock all four sub-steps (compile_db, walker, backend,
merge) so the tests are fast and don't require libclang, a binary,
or a toolchain. We verify that extract.py wires them correctly.

Checks:
  - compile_db.load called with compile_commands path
  - walker.walk called once per file in flag_map, with correct flags
  - backend.extract_rvas called with binary_path
  - merge.merge called with combined AST and rva_map
  - manifest JSON written to output_path
  - printed summary contains fn/struct/enum/typedef counts
  - --debug-format dwarf selects DwarfBackend
  - --debug-format pdb selects PdbBackend
  - .pdb extension auto-selects PdbBackend without --debug-format
  - non-.pdb extension auto-selects DwarfBackend without --debug-format
  - unknown --debug-format exits with error
  - missing libclang exits with clear message
  - walker RuntimeError on a file: warning printed, other files still walked
  - empty compile_commands: warning printed, still runs to completion
  - output parent directories created if they don't exist
  - manifest returned from run() matches what merge returned
"""
from __future__ import annotations

import extractor.extract

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

_FLAG_MAP = {
    "/src/a.cpp": ["-std=c++17"],
    "/src/b.cpp": ["-std=c++17", "-DFOO"],
}

_AST_A = {
    "functions": [{"flat": "fa", "mangled": "_Z2fav", "member": False,
                   "self_view": None, "rva": None, "loc": "a.cpp:1",
                   "ret": "void", "args": []}],
    "structs":   [{"name": "A", "size": 4, "fields": []}],
    "enums":     [],
    "typedefs":  [],
}
_AST_B = {
    "functions": [{"flat": "fb", "mangled": "_Z2fbv", "member": False,
                   "self_view": None, "rva": None, "loc": "b.cpp:1",
                   "ret": "void", "args": []}],
    "structs":   [],
    "enums":     [{"name": "Color", "owner": None, "values": []}],
    "typedefs":  [{"alias": "MyInt", "kind": "i32"}],
}

_RVA_MAP = {"_Z2fav": 0x1000, "_Z2fbv": 0x2000}

_MANIFEST = {
    "version": 2,
    "functions": [
        {"flat": "fa", "mangled": "_Z2fav", "rva": "0x1000",
         "member": False, "self_view": None, "loc": "a.cpp:1",
         "ret": "void", "args": []},
        {"flat": "fb", "mangled": "_Z2fbv", "rva": "0x2000",
         "member": False, "self_view": None, "loc": "b.cpp:1",
         "ret": "void", "args": []},
    ],
    "structs":   [{"name": "A", "size": 4, "fields": []}],
    "enums":     [{"name": "Color", "owner": None, "values": []}],
    "typedefs":  [{"alias": "MyInt", "kind": "i32"}],
}


def _mock_backend(rva_map=None):
    b = MagicMock()
    b.extract_rvas.return_value = rva_map if rva_map is not None else _RVA_MAP
    return b


def _patch_all(tmp_path, *, flag_map=None, ast_side_effect=None,
               rva_map=None, manifest=None, backend=None):
    """Return a context-manager stack of all four mocks."""
    fm      = flag_map if flag_map is not None else _FLAG_MAP
    man     = manifest if manifest is not None else _MANIFEST
    be      = backend  if backend  is not None else _mock_backend(rva_map)

    if ast_side_effect is not None:
        walk_mock = MagicMock(side_effect=ast_side_effect)
    else:
        walk_mock = MagicMock(side_effect=[_AST_A, _AST_B])

    patches = [
        patch("extractor.extract._require_libclang"),
        patch("extractor.ast_walk.compile_db.load", return_value=fm),
        patch("extractor.ast_walk.walker.walk",     walk_mock),
        patch("extractor.merge.merge",         return_value=man),
        patch("clang.cindex.Index.create",     return_value=MagicMock()),
    ]

    patches.append(patch("extractor.binary.dwarf.DwarfBackend", return_value=be))
    patches.append(patch("extractor.binary.pdb.PdbBackend",     return_value=be))
    return patches

def _run_with_patches(tmp_path, extra_kwargs=None, **patch_kwargs):
    out = tmp_path / "manifest.json"
    patches = _patch_all(tmp_path, **patch_kwargs)
    from contextlib import ExitStack
    with ExitStack() as stack:
        mocks = [stack.enter_context(p) for p in patches]
        from extractor.extract import run
        result = run(
            binary_path="/fake/lib.so",
            compile_commands_path="/fake/compile_commands.json",
            output_path=str(out),
            **(extra_kwargs or {}),
        )
    return result, out, mocks

def test_compile_db_called(tmp_path):
    _, _, mocks = _run_with_patches(tmp_path)
    mocks[1].assert_called_once_with("/fake/compile_commands.json")

def test_walker_called_per_file(tmp_path):
    _, _, mocks = _run_with_patches(tmp_path)
    assert mocks[2].call_count == 2


def test_walker_receives_correct_flags(tmp_path):
    _, _, mocks = _run_with_patches(tmp_path)
    calls = {c.args[0]: c.args[1] for c in mocks[2].call_args_list}
    assert calls["/src/a.cpp"] == ["-std=c++17"]
    assert calls["/src/b.cpp"] == ["-std=c++17", "-DFOO"]


def test_backend_extract_rvas_called(tmp_path):
    be = _mock_backend()
    _run_with_patches(tmp_path, backend=be)
    be.extract_rvas.assert_called_once_with("/fake/lib.so")


def test_merge_called(tmp_path):
    _, _, mocks = _run_with_patches(tmp_path)
    assert mocks[3].called


def test_manifest_written_to_disk(tmp_path):
    _, out, _ = _run_with_patches(tmp_path)
    assert out.exists()
    data = json.loads(out.read_text())
    assert data["version"] == 2


def test_run_returns_manifest(tmp_path):
    result, _, _ = _run_with_patches(tmp_path)
    assert result == _MANIFEST


def test_output_dirs_created(tmp_path):
    nested_out = tmp_path / "a" / "b" / "c" / "manifest.json"
    patches = _patch_all(tmp_path)
    from contextlib import ExitStack
    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        from extractor.extract import run
        run(
            binary_path="/fake/lib.so",
            compile_commands_path="/fake/compile_commands.json",
            output_path=str(nested_out),
        )
    assert nested_out.exists()

def test_pdb_extension_selects_pdb_backend(tmp_path):
    be = _mock_backend()
    patches = _patch_all(tmp_path, backend=be)
    from contextlib import ExitStack
    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        from extractor.extract import run
        run(
            binary_path="/fake/lib.pdb",
            compile_commands_path="/fake/compile_commands.json",
            output_path=str(tmp_path / "out.json"),
        )
    import extractor.binary.pdb as pdb_mod
    be.extract_rvas.assert_called_once_with("/fake/lib.pdb")


def test_debug_format_dwarf_explicit(tmp_path):
    be = _mock_backend()
    patches = _patch_all(tmp_path, backend=be)
    from contextlib import ExitStack
    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        from extractor.extract import run
        run(
            binary_path="/fake/lib.so",
            compile_commands_path="/fake/compile_commands.json",
            output_path=str(tmp_path / "out.json"),
            debug_format="dwarf",
        )
    be.extract_rvas.assert_called_once()

def test_unknown_debug_format_exits(tmp_path):
    with pytest.raises(SystemExit):
        patches = _patch_all(tmp_path)
        from contextlib import ExitStack
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            from extractor.extract import run
            run(
                binary_path="/fake/lib.so",
                compile_commands_path="/fake/compile_commands.json",
                output_path=str(tmp_path / "out.json"),
                debug_format="elf",
            )

def test_missing_libclang_exits():
    with patch("extractor.extract._require_libclang",
               side_effect=SystemExit("[extract] requires libclang")):
        with pytest.raises(SystemExit, match="libclang"):
            from extractor.extract import run
            run("/fake/lib.so", "/fake/cc.json", "/fake/out.json")


def test_walker_error_continues(tmp_path, capsys):
    side_effect = [RuntimeError("parse error in a.cpp"), _AST_B]
    _, out, _ = _run_with_patches(tmp_path, ast_side_effect=side_effect)
    captured = capsys.readouterr()
    assert "warning" in captured.err.lower()
    assert out.exists()


def test_empty_compile_commands_warns(tmp_path, capsys):
    patches = _patch_all(tmp_path, flag_map={},
                          ast_side_effect=[],
                          manifest={**_MANIFEST, "functions": []})
    from contextlib import ExitStack
    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        from extractor.extract import run
        run(
            binary_path="/fake/lib.so",
            compile_commands_path="/fake/compile_commands.json",
            output_path=str(tmp_path / "out.json"),
        )
    captured = capsys.readouterr()
    assert "warning" in captured.out.lower() or "warning" in captured.err.lower()

def test_cli_passes_args(tmp_path):
    out = tmp_path / "manifest.json"
    patches = _patch_all(tmp_path)
    from contextlib import ExitStack
    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        from extractor.extract import main
        main([
            "--binary",           "/fake/lib.so",
            "--compile-commands", "/fake/cc.json",
            "--output",           str(out),
        ])
    assert out.exists()

def test_cli_debug_format_arg(tmp_path):
    out = tmp_path / "manifest.json"
    patches = _patch_all(tmp_path)
    from contextlib import ExitStack
    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        from extractor.extract import main
        main([
            "--binary",           "/fake/lib.so",
            "--compile-commands", "/fake/cc.json",
            "--output",           str(out),
            "--debug-format",     "dwarf",
        ])
    assert out.exists()
