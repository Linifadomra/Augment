// Augment Copyright (C) 2026 Liam
//
// Licensed under the MIT License.
// See LICENSE for details.

// Hook self-test replacement (separate TU from augment_plat_selftest_target).

static int (*s_selftest_orig)(int) = nullptr;

namespace augment::plat {
void selftest_bind_orig(void* orig) {
    s_selftest_orig = reinterpret_cast<int (*)(int)>(orig);
}
} // namespace augment::plat

#if defined(_MSC_VER)
__declspec(noinline)
#else
__attribute__((noinline))
#endif
extern "C" int augment_plat_selftest_replacement(int x) {
    return s_selftest_orig(x) + 100;
}
