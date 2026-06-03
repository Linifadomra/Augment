"""
test_ctx_gen.py
Verifies augment_ctx.hpp output: struct names, fields, field types.
"""

from conftest import ctx_hpp, load_manifest


# ---------------------------------------------------------------------------
# File is emitted
# ---------------------------------------------------------------------------

def test_ctx_hpp_exists(run_walker):
    out = run_walker("simple.hpp")
    assert (out / "augment_ctx.hpp").exists()


def test_ctx_hpp_has_pragma_once(run_walker):
    out = run_walker("simple.hpp")
    assert "#pragma once" in ctx_hpp(out)


def test_ctx_hpp_includes_augment_h(run_walker):
    out = run_walker("simple.hpp")
    assert '#include "augment/augment.h"' in ctx_hpp(out)


# ---------------------------------------------------------------------------
# Struct names
# ---------------------------------------------------------------------------

def test_ctx_struct_name_member(run_walker):
    out = run_walker("simple.hpp")
    assert "struct ctx_Combat_calculateDamage" in ctx_hpp(out)


def test_ctx_struct_name_void_method(run_walker):
    out = run_walker("simple.hpp")
    assert "struct ctx_Combat_applyDamage" in ctx_hpp(out)


def test_ctx_struct_name_namespaced(run_walker):
    out = run_walker("namespaced.hpp")
    assert "struct ctx_Game_Combat_System_calculateDamage" in ctx_hpp(out)


def test_ctx_struct_name_free_function(run_walker):
    out = run_walker("free_functions.hpp")
    assert "struct ctx_globalDamageScale" in ctx_hpp(out)


# ---------------------------------------------------------------------------
# self field
# ---------------------------------------------------------------------------

def test_member_fn_has_self_field(run_walker):
    out = run_walker("simple.hpp")
    hpp = ctx_hpp(out)
    # Find the struct block for calculateDamage
    start = hpp.index("struct ctx_Combat_calculateDamage")
    block = hpp[start: hpp.index("};", start) + 2]
    assert "void*" in block and "self" in block


def test_free_fn_has_no_self_field(run_walker):
    out = run_walker("free_functions.hpp")
    hpp = ctx_hpp(out)
    start = hpp.index("struct ctx_globalDamageScale")
    block = hpp[start: hpp.index("};", start) + 2]
    assert "self" not in block


# ---------------------------------------------------------------------------
# Parameter fields
# ---------------------------------------------------------------------------

def test_value_param_stored_as_value(run_walker):
    out = run_walker("simple.hpp")
    hpp = ctx_hpp(out)
    start = hpp.index("struct ctx_Combat_calculateDamage")
    block = hpp[start: hpp.index("};", start) + 2]
    assert "float" in block
    assert "base" in block
    assert "multiplier" in block


def test_ref_param_stored_as_pointer(run_walker):
    """Entity& target must become Entity* in the ctx struct."""
    out = run_walker("refs_and_ptrs.hpp")
    hpp = ctx_hpp(out)
    start = hpp.index("struct ctx_Combat_applyDamage {")
    block = hpp[start: hpp.index("};", start) + 2]
    assert "Entity*" in block
    assert "target" in block


def test_pointer_param_stored_as_pointer(run_walker):
    out = run_walker("refs_and_ptrs.hpp")
    hpp = ctx_hpp(out)
    start = hpp.index("struct ctx_Combat_applyDamagePtr")
    block = hpp[start: hpp.index("};", start) + 2]
    assert "Entity *" in block or "Entity*" in block


# ---------------------------------------------------------------------------
# __return field
# ---------------------------------------------------------------------------

def test_non_void_has_return_field(run_walker):
    out = run_walker("simple.hpp")
    hpp = ctx_hpp(out)
    start = hpp.index("struct ctx_Combat_calculateDamage")
    block = hpp[start: hpp.index("};", start) + 2]
    assert "__return" in block


def test_void_has_no_return_field(run_walker):
    out = run_walker("void_return.hpp")
    hpp = ctx_hpp(out)
    start = hpp.index("struct ctx_Effects_applyBurn")
    block = hpp[start: hpp.index("};", start) + 2]
    assert "__return" not in block


def test_int_return_type_in_field(run_walker):
    out = run_walker("simple.hpp")
    hpp = ctx_hpp(out)
    start = hpp.index("struct ctx_Combat_countHits")
    block = hpp[start: hpp.index("};", start) + 2]
    assert "int" in block
    assert "__return" in block


# ---------------------------------------------------------------------------
# cancelled field always present
# ---------------------------------------------------------------------------

def test_cancelled_field_present_member(run_walker):
    out = run_walker("simple.hpp")
    hpp = ctx_hpp(out)
    start = hpp.index("struct ctx_Combat_calculateDamage")
    block = hpp[start: hpp.index("};", start) + 2]
    assert "cancelled" in block


def test_cancelled_field_present_void(run_walker):
    out = run_walker("void_return.hpp")
    hpp = ctx_hpp(out)
    start = hpp.index("struct ctx_Effects_applyBurn")
    block = hpp[start: hpp.index("};", start) + 2]
    assert "cancelled" in block


def test_cancelled_field_present_free_fn(run_walker):
    out = run_walker("free_functions.hpp")
    hpp = ctx_hpp(out)
    start = hpp.index("struct ctx_globalDamageScale")
    block = hpp[start: hpp.index("};", start) + 2]
    assert "cancelled" in block


# ---------------------------------------------------------------------------
# Pack function emitted per struct
# ---------------------------------------------------------------------------

def test_pack_fn_emitted(run_walker):
    out = run_walker("simple.hpp")
    assert "augment_ctx_pack_Combat_calculateDamage" in ctx_hpp(out)


def test_pack_fn_takes_augment_ctx(run_walker):
    out = run_walker("simple.hpp")
    hpp = ctx_hpp(out)
    fn  = "augment_ctx_pack_Combat_calculateDamage"
    start = hpp.index(fn)
    block = hpp[start: hpp.index("}", start) + 1]
    assert "AugmentCtx" in block