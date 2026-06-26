// platform_selftest.cpp

#include "augment/platform_compat.hpp"
#include <cstdio>
#include <cstdint>
#include <cstring>

namespace augment::plat {
    bool  hook_install(void* target, void* replacement, void** out_original);
    bool  hook_remove(void* target);
    void* sym_resolve(const char* symbol);
}

extern "C" AUGMENT_NOINLINE int aug_selftest_target(int x) {
    volatile int a = x;
    a += 7;
    a *= 3;
    a -= 2;
    return a;
}

static int (*augment_selftest_orig)(int) = nullptr;

extern "C" int aug_selftest_replacement(int x) {
    return augment_selftest_orig(x) + 1000;
}

void* follow_thunk(void* address) {
    if (!address) return nullptr;

    uint8_t* code = reinterpret_cast<uint8_t*>(address);

    while (true) {

        if (code[0] == 0xE9) {
            int32_t rel = 0;
            std::memcpy(&rel, code + 1, sizeof(rel));
            code = code + 5 + rel;
            continue;
        }

        if (code[0] == 0xFF && code[1] == 0x25) {

#if defined(__x86_64__) || defined(_M_X64)
            int32_t rel = 0;
            std::memcpy(&rel, code + 2, sizeof(rel));

            void** target = reinterpret_cast<void**>(code + 6 + rel);

#else
            uint32_t abs = 0;
            std::memcpy(&abs, code + 2, sizeof(abs));

            void** target = reinterpret_cast<void**>(abs);
#endif

            if (target && *target) {
                code = reinterpret_cast<uint8_t*>(*target);
                continue;
            }
        }

        return code;
    }
}

int main() {
    int fails = 0;
    void* target = follow_thunk((void*)&aug_selftest_target);
    void* resolved = augment::plat::sym_resolve("aug_selftest_target");
    if (resolved == target) {
        std::printf("ok   sym_resolve -> %p\n", resolved);
    } else {
        std::printf("FAIL sym_resolve got %p want %p\n",
                    resolved, target);
        ++fails;
    }

    int before = aug_selftest_target(5);
    if (!augment::plat::hook_install(target,
                                     reinterpret_cast<void*>(&aug_selftest_replacement),
                                     reinterpret_cast<void**>(&augment_selftest_orig))) {
        std::printf("FAIL hook_install\n");
        return 1;
    }
    int hooked   = aug_selftest_target(5);
    augment::plat::hook_remove(target);
    int restored = aug_selftest_target(5);

    if (hooked == before + 1000 && restored == before) {
        std::printf("ok   hook before=%d hooked=%d restored=%d\n", before, hooked, restored);
    } else {
        std::printf("FAIL hook before=%d hooked=%d restored=%d\n", before, hooked, restored);
        ++fails;
    }

    std::printf("%s\n", fails == 0 ? "platform selftest PASSED" : "platform selftest FAILED");
    return fails;
}
