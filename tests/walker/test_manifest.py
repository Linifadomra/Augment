"""
test_manifest.py
Verifies symbols.json shape and field correctness for known inputs.
"""

import pytest
from conftest import load_manifest, get_symbol


# ---------------------------------------------------------------------------
# Manifest structure
# ---------------------------------------------------------------------------

def test_manifest_has_version(run_walker):
    out = run_walker("simple.hpp")
    manifest = load_manifest(out)
    assert manifest["version"] == 1


def test_manifest_has_symbols_list(run_walker):
    out = run_walker("simple.hpp")
    manifest = load_manifest(out)
    assert isinstance(manifest["symbols"], list)
    assert len(manifest["symbols"]) > 0


# ---------------------------------------------------------------------------
# Symbol fields; simple member functions
# ---------------------------------------------------------------------------

def test_symbol_qualified_name(run_walker):
    out = run_walker("simple.hpp")
    manifest = load_manifest(out)
    names = [s["symbol"] for s in manifest["symbols"]]
    assert "Combat::calculateDamage" in names


def test_symbol_return_type_float(run_walker):
    out = run_walker("simple.hpp")
    sym = get_symbol(load_manifest(out), "Combat::calculateDamage")
    assert sym["return_type"] == "float"


def test_symbol_returns_void_false(run_walker):
    out = run_walker("simple.hpp")
    sym = get_symbol(load_manifest(out), "Combat::calculateDamage")
    assert sym["returns_void"] is False


def test_symbol_returns_void_true(run_walker):
    out = run_walker("simple.hpp")
    sym = get_symbol(load_manifest(out), "Combat::applyDamage")
    assert sym["returns_void"] is True


def test_symbol_is_member_true(run_walker):
    out = run_walker("simple.hpp")
    sym = get_symbol(load_manifest(out), "Combat::calculateDamage")
    assert sym["is_member"] is True


def test_symbol_param_count(run_walker):
    out = run_walker("simple.hpp")
    sym = get_symbol(load_manifest(out), "Combat::calculateDamage")
    assert len(sym["params"]) == 2


def test_symbol_param_names(run_walker):
    out = run_walker("simple.hpp")
    sym = get_symbol(load_manifest(out), "Combat::calculateDamage")
    names = [p["name"] for p in sym["params"]]
    assert names == ["base", "multiplier"]


def test_symbol_param_types(run_walker):
    out = run_walker("simple.hpp")
    sym = get_symbol(load_manifest(out), "Combat::calculateDamage")
    types = [p["type"] for p in sym["params"]]
    assert types == ["float", "float"]


def test_symbol_no_params(run_walker):
    out = run_walker("simple.hpp")
    sym = get_symbol(load_manifest(out), "Combat::countHits")
    assert sym["params"] == []


# ---------------------------------------------------------------------------
# Ref and pointer params
# ---------------------------------------------------------------------------

def test_ref_param_is_ref_true(run_walker):
    out = run_walker("refs_and_ptrs.hpp")
    sym = get_symbol(load_manifest(out), "Combat::applyDamage")
    target = next(p for p in sym["params"] if p["name"] == "target")
    assert target["is_ref"] is True


def test_ref_param_pointee_type(run_walker):
    out = run_walker("refs_and_ptrs.hpp")
    sym = get_symbol(load_manifest(out), "Combat::applyDamage")
    target = next(p for p in sym["params"] if p["name"] == "target")
    assert "Entity" in target["pointee_type"]


def test_pointer_param_is_pointer_true(run_walker):
    out = run_walker("refs_and_ptrs.hpp")
    sym = get_symbol(load_manifest(out), "Combat::applyDamagePtr")
    target = next(p for p in sym["params"] if p["name"] == "target")
    assert target["is_pointer"] is True


def test_value_param_is_ref_false(run_walker):
    out = run_walker("simple.hpp")
    sym = get_symbol(load_manifest(out), "Combat::calculateDamage")
    base = next(p for p in sym["params"] if p["name"] == "base")
    assert base["is_ref"] is False
    assert base["is_pointer"] is False


# ---------------------------------------------------------------------------
# Free functions
# ---------------------------------------------------------------------------

def test_free_function_is_member_false(run_walker):
    out = run_walker("free_functions.hpp")
    sym = get_symbol(load_manifest(out), "globalDamageScale")
    assert sym["is_member"] is False


def test_free_function_no_class(run_walker):
    out = run_walker("free_functions.hpp")
    sym = get_symbol(load_manifest(out), "globalDamageScale")
    assert sym["class"] == ""


def test_free_function_params(run_walker):
    out = run_walker("free_functions.hpp")
    sym = get_symbol(load_manifest(out), "globalDamageScale")
    assert len(sym["params"]) == 1
    assert sym["params"][0]["name"] == "base"


def test_free_function_no_params_void_return(run_walker):
    out = run_walker("free_functions.hpp")
    sym = get_symbol(load_manifest(out), "resetGameState")
    assert sym["params"] == []
    assert sym["returns_void"] is True


# ---------------------------------------------------------------------------
# Namespaced symbols
# ---------------------------------------------------------------------------

def test_namespaced_qualified_name(run_walker):
    out = run_walker("namespaced.hpp")
    manifest = load_manifest(out)
    names = [s["symbol"] for s in manifest["symbols"]]
    assert "Game::Combat::System::calculateDamage" in names


def test_namespaced_class_field(run_walker):
    out = run_walker("namespaced.hpp")
    sym = get_symbol(load_manifest(out), "Game::Combat::System::calculateDamage")
    assert sym["class"] == "System"


# ---------------------------------------------------------------------------
# Symbol prefix filter
# ---------------------------------------------------------------------------

def test_prefix_filter_includes_match(run_walker):
    out = run_walker("mixed_classes.hpp",
                     extra_args=["--symbol-prefix", "Combat::"])
    manifest = load_manifest(out)
    names = [s["symbol"] for s in manifest["symbols"]]
    assert any(n.startswith("Combat::") for n in names)


def test_prefix_filter_excludes_non_match(run_walker):
    out = run_walker("mixed_classes.hpp",
                     extra_args=["--symbol-prefix", "Combat::"])
    manifest = load_manifest(out)
    names = [s["symbol"] for s in manifest["symbols"]]
    assert not any(n.startswith("Audio::") for n in names)


# ---------------------------------------------------------------------------
# json-only flag
# ---------------------------------------------------------------------------

def test_json_only_emits_manifest(run_walker):
    out = run_walker("simple.hpp", extra_args=["--json-only"])
    assert (out / "symbols.json").exists()


def test_json_only_no_ctx_hpp(run_walker):
    out = run_walker("simple.hpp", extra_args=["--json-only"])
    assert not (out / "augment_ctx.hpp").exists()


def test_json_only_no_trampolines(run_walker):
    out = run_walker("simple.hpp", extra_args=["--json-only"])
    assert not (out / "augment_trampolines.cpp").exists()