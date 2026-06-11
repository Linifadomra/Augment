"""
extractor/tests/test_binary_interface.py

Tests DebugInfoBackend ABC contract.

Checks:
  - ABC cannot be instantiated directly
  - Concrete subclass missing extract_rvas cannot be instantiated
  - Valid subclass can be instantiated and called
  - extract_rvas return type is Dict[str, int] (str keys, int values)
  - Empty result is valid (no symbols with addresses)
  - 'name' class attribute is present and a str
  - binary_path is forwarded to the implementation unchanged
"""

import pytest
from extractor.binary.interface import DebugInfoBackend

class _GoodBackend(DebugInfoBackend):
    name = "test"

    def __init__(self):
        self._last_path = None

    def extract_rvas(self, binary_path: str):
        self._last_path = binary_path
        return {
            "_ZN3FooC1Ev": 0x1000,
            "_ZN3FooD1Ev": 0x1080,
            "_ZN3Foo3barEi": 0x1100,
        }


class _EmptyBackend(DebugInfoBackend):
    name = "empty"

    def extract_rvas(self, binary_path: str):
        return {}


class _MissingMethod(DebugInfoBackend):
    name = "broken"
    # intentionally omits extract_rvas

def test_abc_cannot_be_instantiated():
    with pytest.raises(TypeError):
        DebugInfoBackend()

def test_subclass_missing_extract_rvas_cannot_be_instantiated():
    with pytest.raises(TypeError):
        _MissingMethod()

def test_valid_subclass_instantiates():
    b = _GoodBackend()
    assert isinstance(b, DebugInfoBackend)

def test_extract_rvas_returns_dict():
    result = _GoodBackend().extract_rvas("/fake/path/lib.so")
    assert isinstance(result, dict)

def test_extract_rvas_keys_are_strings():
    result = _GoodBackend().extract_rvas("/fake/path/lib.so")
    assert all(isinstance(k, str) for k in result)

def test_extract_rvas_values_are_ints():
    result = _GoodBackend().extract_rvas("/fake/path/lib.so")
    assert all(isinstance(v, int) for v in result.values())

def test_extract_rvas_values_are_non_negative():
    result = _GoodBackend().extract_rvas("/fake/path/lib.so")
    assert all(v >= 0 for v in result.values())

def test_extract_rvas_empty_is_valid():
    result = _EmptyBackend().extract_rvas("/fake/path/lib.so")
    assert result == {}

def test_binary_path_forwarded():
    b = _GoodBackend()
    b.extract_rvas("/specific/path/libfoo.so")
    assert b._last_path == "/specific/path/libfoo.so"


def test_binary_path_forwarded_windows_style():
    b = _GoodBackend()
    b.extract_rvas(r"C:\project\build\foo.pdb")
    assert b._last_path == r"C:\project\build\foo.pdb"

def test_name_attribute_is_str():
    b = _GoodBackend()
    assert isinstance(b.name, str)


def test_name_attribute_non_empty_for_concrete():
    b = _GoodBackend()
    assert b.name != ""

def test_empty_backend_name():
    b = _EmptyBackend()
    assert b.name == "empty"

def test_two_backends_independent():
    good = _GoodBackend()
    empty = _EmptyBackend()
    assert good.extract_rvas("x") != empty.extract_rvas("x")


def test_backend_is_instance_of_abc():
    assert isinstance(_GoodBackend(), DebugInfoBackend)
    assert isinstance(_EmptyBackend(), DebugInfoBackend)
