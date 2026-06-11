"""
extractor/tests/test_binary_pdb.py

Strategy: monkey-patch subprocess.run to return a canned llvm-pdbutil
text fixture, then assert on the RVA map produced. The full
_parse_section_headers + _parse_function_rvas stack runs for real.

Checks:
  - Is a DebugInfoBackend subclass
  - name == "pdb"
  - extract_rvas returns Dict[str, int]
  - Keys are strings, values are non-negative ints
  - Correct mangled->RVA mapping (seg:off resolved through section table)
  - S_LPROC32 entries are also captured (not just S_GPROC32)
  - Records without an addr line are excluded
  - addr with seg == 0 is excluded
  - Duplicate records for the same mangled name: highest RVA wins
  - Empty input -> empty dict
  - binary_path is passed to llvm-pdbutil as the last positional argument
"""
import types
from unittest.mock import MagicMock, patch

import pytest

from extractor.binary.pdb import PdbBackend
from extractor.binary.interface import DebugInfoBackend

# ===
# Fixture
# ===
# Section table:
#   section 1: VA = 0x1000  (code)
#   section 2: VA = 0x3000  (data)
#
# Expected RVAs:
#   _ZN3Foo3barEi  seg=0001 off=0100  ->  0x1000 + 0x100  = 0x1100
#   _ZN3Foo3bazEv  seg=0001 off=0200  ->  0x1000 + 0x200  = 0x1200
#   _ZN3Foo9lprocEv (S_LPROC32) seg=0001 off=0300 -> 0x1300
#   _ZN3Foo6dupFnEv appears twice; 0x1080 then 0x1400 -> 0x1400 wins
#   _ZN3Foo7noAddrEv has no addr line  -> excluded
#   zero_seg has seg=0000 -> excluded

_FIXTURE = """\
Summary
=======

Types (TPI Stream)
==================

Symbols
=======
Mod 0000 | `foo.obj`:

      32 | S_GPROC32_ID [size = 56] `_ZN3Foo3barEi`
           type = `0x1002 (int (Foo*, int))`
           addr = 0001:00000100
           code size = 20, flags = none

      96 | S_GPROC32_ID [size = 56] `_ZN3Foo3bazEv`
           type = `0x1004 (void (Foo*))`
           addr = 0001:00000200
           code size = 12, flags = none

     160 | S_LPROC32_ID [size = 56] `_ZN3Foo9lprocEv`
           type = `0x1006 (void (Foo*))`
           addr = 0001:00000300
           code size = 8, flags = none

     224 | S_GPROC32_ID [size = 56] `_ZN3Foo6dupFnEv`
           type = `0x1008`
           addr = 0001:00000080

     288 | S_GPROC32_ID [size = 56] `_ZN3Foo6dupFnEv`
           type = `0x1008`
           addr = 0001:00000400

     352 | S_GPROC32_ID [size = 56] `_ZN3Foo7noAddrEv`
           type = `0x100a`

     416 | S_GPROC32_ID [size = 56] `_ZN3Foo7zeroSegEv`
           type = `0x100c`
           addr = 0000:00000500

     480 | S_END

Section Headers
===============

SECTION HEADER #1
         1000 virtual address
         1000 virtual size

SECTION HEADER #2
         3000 virtual address
          800 virtual size
"""

_EMPTY = ""

def _make_run(text: str):
    mock = MagicMock()
    mock.return_value = types.SimpleNamespace(stdout=text)
    return mock

def _run(text: str, path: str = "/fake/lib.pdb"):
    with patch("extractor.binary.pdb.subprocess.run", _make_run(text)):
        return PdbBackend().extract_rvas(path)

def test_is_debug_info_backend():
    assert isinstance(PdbBackend(), DebugInfoBackend)

def test_name():
    assert PdbBackend.name == "pdb"

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

def test_lproc32_captured():
    result = _run(_FIXTURE)
    assert result["_ZN3Foo9lprocEv"] == 0x1300

def test_no_addr_excluded():
    result = _run(_FIXTURE)
    assert "_ZN3Foo7noAddrEv" not in result

def test_zero_seg_excluded():
    result = _run(_FIXTURE)
    assert "_ZN3Foo7zeroSegEv" not in result

def test_duplicate_highest_rva_wins():
    result = _run(_FIXTURE)
    assert result["_ZN3Foo6dupFnEv"] == 0x1400

def test_empty_output_returns_empty_dict():
    assert _run(_EMPTY) == {}

def test_binary_path_passed_to_pdbutil():
    mock_run = _make_run(_EMPTY)
    with patch("extractor.binary.pdb.subprocess.run", mock_run):
        PdbBackend().extract_rvas("/specific/path/foo.pdb")
    call_args = mock_run.call_args[0][0]
    assert call_args[-1] == "/specific/path/foo.pdb"