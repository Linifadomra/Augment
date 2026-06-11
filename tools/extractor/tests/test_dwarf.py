"""
extractor/tests/test_binary_dwarf.py

Gate for Step 3: DwarfBackend.

Strategy: we don't shell out to dwarfdump in unit tests. Instead, we
monkey-patch subprocess.run to return a canned dwarfdump text fixture,
then assert on the RVA map produced.

Checks:
  - Is a DebugInfoBackend subclass
  - extract_rvas returns Dict[str, int]
  - Correct mangled->RVA mapping from fixture
  - Subprograms without DW_AT_low_pc are excluded
  - Subprograms without DW_AT_linkage_name are excluded
  - Duplicate DIEs for the same mangled name: highest RVA wins
  - Empty dwarfdump output -> empty dict
  - binary_path is passed to dwarfdump as the last positional argument
"""

import subprocess
import types
from unittest.mock import MagicMock, patch

import pytest

from extractor.binary.dwarf import DwarfBackend
from extractor.binary.interface import DebugInfoBackend

_FIXTURE = """\
0x0000000b: DW_TAG_compile_unit
              DW_AT_producer    ("clang version 17.0.0")
              DW_AT_language    (DW_LANG_C_plus_plus)

0x00000030:   DW_TAG_subprogram
                DW_AT_name            ("bar")
                DW_AT_linkage_name    ("_ZN3Foo3barEi")
                DW_AT_low_pc          (0x0000000000001100)
                DW_AT_decl_file       ("foo.cpp")
                DW_AT_decl_line       (12)

0x00000060:   DW_TAG_subprogram
                DW_AT_name            ("baz")
                DW_AT_linkage_name    ("_ZN3Foo3bazEv")
                DW_AT_low_pc          (0x0000000000001200)

0x00000090:   DW_TAG_subprogram
                DW_AT_name            ("no_linkage")
                DW_AT_low_pc          (0x0000000000001300)

0x000000c0:   DW_TAG_subprogram
                DW_AT_name            ("no_address")
                DW_AT_linkage_name    ("_ZN3Foo10no_addressEv")

0x000000f0:   DW_TAG_subprogram
                DW_AT_name            ("dup_low")
                DW_AT_linkage_name    ("_ZN3Foo6dupLowEv")
                DW_AT_low_pc          (0x0000000000001080)

0x00000120:   DW_TAG_subprogram
                DW_AT_name            ("dup_high")
                DW_AT_linkage_name    ("_ZN3Foo6dupLowEv")
                DW_AT_low_pc          (0x0000000000001400)
"""

_EMPTY = ""

def _make_run(text):
    """Return a mock for subprocess.run that yields the given stdout."""
    mock = MagicMock()
    mock.return_value = types.SimpleNamespace(stdout=text)
    return mock

def _run(text, path="/fake/lib.so"):
    with patch("extractor.binary.dwarf.subprocess.run", _make_run(text)):
        return DwarfBackend().extract_rvas(path)

def test_is_debug_info_backend():
    assert isinstance(DwarfBackend(), DebugInfoBackend)

def test_name():
    assert DwarfBackend.name == "dwarf"

def test_returns_dict():
    assert isinstance(_run(_FIXTURE), dict)


def test_values_are_ints():
    result = _run(_FIXTURE)
    assert all(isinstance(v, int) for v in result.values())


def test_keys_are_strings():
    result = _run(_FIXTURE)
    assert all(isinstance(k, str) for k in result)

def test_known_rvas():
    result = _run(_FIXTURE)
    assert result["_ZN3Foo3barEi"] == 0x1100
    assert result["_ZN3Foo3bazEv"] == 0x1200

def test_no_linkage_name_excluded():
    result = _run(_FIXTURE)
    # "no_linkage" has low_pc but no linkage_name. Must not appear
    assert not any("no_linkage" in k for k in result)


def test_no_low_pc_excluded():
    result = _run(_FIXTURE)
    assert "_ZN3Foo10no_addressEv" not in result

def test_duplicate_highest_rva_wins():
    result = _run(_FIXTURE)
    assert result["_ZN3Foo6dupLowEv"] == 0x1400

def test_empty_output_returns_empty_dict():
    assert _run(_EMPTY) == {}

def test_binary_path_passed_to_dwarfdump():
    mock_run = _make_run(_EMPTY)
    with patch("extractor.binary.dwarf.subprocess.run", mock_run):
        DwarfBackend().extract_rvas("/specific/path/libfoo.so")

    call_args = mock_run.call_args[0][0]
    assert call_args[-1] == "/specific/path/libfoo.so"
