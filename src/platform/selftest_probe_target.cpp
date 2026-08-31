// Augment Copyright (C) 2026 Liam
//
// Licensed under the MIT License.
// See LICENSE for details.

// Hook self-test target (separate TU so func_gap >= 16 on Darwin).

#if defined(_MSC_VER)
__declspec(noinline)
#else
__attribute__((noinline))
#endif
extern "C" int augment_plat_selftest_target(int x) {
    volatile int v = x;
    return v + 1;
}
