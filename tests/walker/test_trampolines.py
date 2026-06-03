"""
test_trampolines.py
Verifies augment_trampolines.cpp output: function signatures, augment_invoke
call, return handling, args array shape.
"""

from conftest import trampolines_cpp


# ---------------------------------------------------------------------------
# File is emitted
# ---------------------------------------------------------------------------

def test_trampolines_cpp_exists(run_walker):
    out = run_walker("simple.hpp")
    assert (out / "augment_trampolines.cpp").exists()


def test_trampolines_includes_ctx_hpp(run_walker):
    out = run_walker("simple.hpp")
    assert '#include "augment_ctx.hpp"' in trampolines_cpp(out)


def test_trampolines_includes_augment_h(run_walker):
    out = run_walker("simple.hpp")
    assert '#include "augment/augment.h"' in trampolines_cpp(out)


def test_trampolines_declares_augment_invoke(run_walker):
    out = run_walker("simple.hpp")
    assert "augment_invoke" in trampolines_cpp(out)


# ---------------------------------------------------------------------------
# Function names
# ---------------------------------------------------------------------------

def test_trampoline_fn_name_member(run_walker):
    out = run_walker("simple.hpp")
    assert "augment_dispatch_Combat_calculateDamage" in trampolines_cpp(out)


def test_trampoline_fn_name_void(run_walker):
    out = run_walker("simple.hpp")
    assert "augment_dispatch_Combat_applyDamage" in trampolines_cpp(out)


def test_trampoline_fn_name_free(run_walker):
    out = run_walker("free_functions.hpp")
    assert "augment_dispatch_globalDamageScale" in trampolines_cpp(out)


def test_trampoline_fn_name_namespaced(run_walker):
    out = run_walker("namespaced.hpp")
    assert "augment_dispatch_Game_Combat_System_calculateDamage" in trampolines_cpp(out)


# ---------------------------------------------------------------------------
# Self parameter in signature
# ---------------------------------------------------------------------------

def test_member_trampoline_has_self_param(run_walker):
    out = run_walker("simple.hpp")
    cpp = trampolines_cpp(out)
    start = cpp.index("augment_dispatch_Combat_calculateDamage")
    sig   = cpp[start: cpp.index(")", start) + 1]
    assert "__self" in sig


def test_free_trampoline_no_self_param(run_walker):
    out = run_walker("free_functions.hpp")
    cpp = trampolines_cpp(out)
    start = cpp.index("augment_dispatch_globalDamageScale")
    sig   = cpp[start: cpp.index(")", start) + 1]
    assert "__self" not in sig


# ---------------------------------------------------------------------------
# augment_invoke call
# ---------------------------------------------------------------------------

def test_trampoline_calls_augment_invoke(run_walker):
    out = run_walker("simple.hpp")
    cpp = trampolines_cpp(out)
    fn  = "augment_dispatch_Combat_calculateDamage"
    start = cpp.index(fn)
    block = cpp[start: cpp.index("}", start) + 1]
    assert 'augment_invoke("Combat::calculateDamage"' in block


def test_trampoline_passes_actx(run_walker):
    out = run_walker("simple.hpp")
    cpp = trampolines_cpp(out)
    fn  = "augment_dispatch_Combat_calculateDamage"
    start = cpp.index(fn)
    block = cpp[start: cpp.index("}", start) + 1]
    assert "&__actx" in block


# ---------------------------------------------------------------------------
# Args array
# ---------------------------------------------------------------------------

def test_args_array_sized_correctly(run_walker):
    """calculateDamage has 2 params so args array must be size 2."""
    out = run_walker("simple.hpp")
    cpp = trampolines_cpp(out)
    fn  = "augment_dispatch_Combat_calculateDamage"
    start = cpp.index(fn)
    block = cpp[start: cpp.index("}", start) + 1]
    assert "void* __args[2]" in block


def test_args_array_no_params(run_walker):
    """countHits has 0 params; emits the null placeholder array."""
    out = run_walker("simple.hpp")
    cpp = trampolines_cpp(out)
    fn  = "augment_dispatch_Combat_countHits"
    start = cpp.index(fn)
    block = cpp[start: cpp.index("}", start) + 1]
    assert "nullptr" in block


# ---------------------------------------------------------------------------
# Return handling
# ---------------------------------------------------------------------------

def test_non_void_has_ret_slot(run_walker):
    out = run_walker("simple.hpp")
    cpp = trampolines_cpp(out)
    fn  = "augment_dispatch_Combat_calculateDamage"
    start = cpp.index(fn)
    block = cpp[start: cpp.index("}", start) + 1]
    assert "__ret" in block
    assert "return __ret" in block


def test_void_no_return_statement(run_walker):
    out = run_walker("simple.hpp")
    cpp = trampolines_cpp(out)
    fn  = "augment_dispatch_Combat_applyDamage"
    start = cpp.index(fn)
    block = cpp[start: cpp.index("}", start) + 1]
    assert "return __ret" not in block


def test_void_ret_ptr_is_nullptr(run_walker):
    out = run_walker("simple.hpp")
    cpp = trampolines_cpp(out)
    fn  = "augment_dispatch_Combat_applyDamage"
    start = cpp.index(fn)
    block = cpp[start: cpp.index("}", start) + 1]
    assert "__ret_ptr = nullptr" in block


# ---------------------------------------------------------------------------
# AugmentCtx initialisation
# ---------------------------------------------------------------------------

def test_actx_constructed(run_walker):
    out = run_walker("simple.hpp")
    cpp = trampolines_cpp(out)
    fn  = "augment_dispatch_Combat_calculateDamage"
    start = cpp.index(fn)
    block = cpp[start: cpp.index("}", start) + 1]
    assert "AugmentCtx __actx" in block


def test_member_actx_self_is_self(run_walker):
    out = run_walker("simple.hpp")
    cpp = trampolines_cpp(out)
    fn  = "augment_dispatch_Combat_calculateDamage"
    start = cpp.index(fn)
    block = cpp[start: cpp.index("}", start) + 1]
    assert "(void*)__self" in block


def test_free_fn_actx_self_is_nullptr(run_walker):
    out = run_walker("free_functions.hpp")
    cpp = trampolines_cpp(out)
    fn  = "augment_dispatch_globalDamageScale"
    start = cpp.index(fn)
    block = cpp[start: cpp.index("}", start) + 1]
    assert "nullptr" in block