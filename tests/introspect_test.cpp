#include "augment/augment.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>

int main() {
    int n = augment_manifest_load("fixtures/sample.manifest");
    assert(n == 5);

    assert(augment_fn_count("daCow_c_Execute") == 1);
    assert(std::strcmp(augment_fn_mangled("daCow_c_Execute", 0), "_ZN7daCow_c7ExecuteEv") == 0);

    assert(augment_fn_count("init") == 2);
    assert(std::strcmp(augment_resolve_sig("init", "i32"), "_ZL4initi") == 0);
    assert(std::strcmp(augment_resolve_sig("init", ""), "_ZL4initv") == 0);

#if AUGMENT_FFI
    assert(augment_make_closure("_ZN7daCow_c7ExecuteEv") != nullptr);
#endif

    const AugmentArg* args = nullptr;
    int na = augment_fn_params("_Z8setStageP7daCph_ci", &args);
    assert(na == 2);
    assert(std::strcmp(args[0].name, "stage") == 0 && std::strcmp(args[0].view, "daCph_c") == 0);

    const AugmentField* fields = nullptr;
    int nf = augment_struct_fields("daCow_c", &fields);
    assert(nf == 3);
    bool found = false;
    for (int i = 0; i < nf; i++)
        if (std::strcmp(fields[i].name, "mName") == 0) { assert(fields[i].offset == 64 && fields[i].len == 8); found = true; }
    assert(found);

    const AugmentEnumVal* evs = nullptr;
    int ne = augment_enum_values("daCow_c::Action", &evs);
    assert(ne == 2);

    const char* gkind = nullptr; void* gaddr = nullptr;
    assert(augment_global_addr("g_dComIfG", &gkind, &gaddr));
    assert((uintptr_t)gaddr == 0x804000);

    assert(std::strcmp(augment_fn_self_view("_ZN7daCow_c7ExecuteEv"), "daCow_c") == 0);
    assert(std::strcmp(augment_fn_self_view("_Z8setStageP7daCph_ci"), "") == 0);

#if AUGMENT_FFI
    assert(augment_make_closure("_Z6addVec4cXyzS_") != nullptr);
#endif

    std::printf("PASS introspect_load\n");
    return 0;
}
