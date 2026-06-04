// platform_selftest.cpp

#include "augment/platform_compat.hpp"
#include <cstdio>

namespace augment::plat {
    bool  hook_install(void* target, void* replacement, void** out_original);
    bool  hook_remove(void* target);
    void* sym_resolve(const char* symbol);
}

extern "C" AUGMENT_NOINLINE int augment_selftest_target(int x) {
    volatile int a = x;
    a += 7;
    a *= 3;
    a -= 2;
    return a;
}

static int (*augment_selftest_orig)(int) = nullptr;

extern "C" int augment_selftest_replacement(int x) {
    return augment_selftest_orig(x) + 1000;
}

int main() {
    int fails = 0;

    void* resolved = augment::plat::sym_resolve("augment_selftest_target");
    if (resolved == reinterpret_cast<void*>(&augment_selftest_target)) {
        std::printf("ok   sym_resolve -> %p\n", resolved);
    } else {
        std::printf("FAIL sym_resolve got %p want %p\n",
                    resolved, reinterpret_cast<void*>(&augment_selftest_target));
        ++fails;
    }

    int before = augment_selftest_target(5);
    if (!augment::plat::hook_install(reinterpret_cast<void*>(&augment_selftest_target),
                                     reinterpret_cast<void*>(&augment_selftest_replacement),
                                     reinterpret_cast<void**>(&augment_selftest_orig))) {
        std::printf("FAIL hook_install\n");
        return 1;
    }
    int hooked   = augment_selftest_target(5);
    augment::plat::hook_remove(reinterpret_cast<void*>(&augment_selftest_target));
    int restored = augment_selftest_target(5);

    if (hooked == before + 1000 && restored == before) {
        std::printf("ok   hook before=%d hooked=%d restored=%d\n", before, hooked, restored);
    } else {
        std::printf("FAIL hook before=%d hooked=%d restored=%d\n", before, hooked, restored);
        ++fails;
    }

    std::printf("%s\n", fails == 0 ? "platform selftest PASSED" : "platform selftest FAILED");
    return fails;
}
