//    Augment Copyright (C) 2026 Liam
//
//    This program is free software: you can redistribute it and/or modify
//    it under the terms of the GNU General Public License as published by
//    the Free Software Foundation, either version 3 of the License, or
//    (at your option) any later version.
//
//    This program is distributed in the hope that it will be useful,
//    but WITHOUT ANY WARRANTY; without even the implied warranty of
//    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
//    GNU General Public License for more details.
//
//    You should have received a copy of the GNU General Public License
//    along with this program.  If not, see <https://www.gnu.org/licenses/>.

#include <dobby.h>

#include <cstdint>

namespace augment::plat {

uint64_t func_gap(void* target);

bool hook_install(void* target, void* replacement, void** out_original) {
    if (!target || func_gap(target) < 16) return false;
    return DobbyHook(target, replacement, out_original) == 0;
}

bool hook_remove(void* target) {
    return target && DobbyDestroy(target) == 0;
}

#if defined(_MSC_VER)
__declspec(noinline)
#else
__attribute__((noinline))
#endif
static int selftest_target(int x) { return x + 1; }
static int (*selftest_orig)(int) = nullptr;
static int selftest_replacement(int x) { return selftest_orig(x) + 100; }

bool self_test(void) {
    volatile int arg = 5;
    int before = selftest_target(arg);
    void* out = nullptr;
    if (!hook_install((void*)selftest_target, (void*)selftest_replacement, &out)) return false;
    selftest_orig = (int(*)(int))out;
    int hooked = selftest_target(arg);
    hook_remove((void*)selftest_target);
    int restored = selftest_target(arg);
    return hooked == before + 100 && restored == before;
}

} // namespace augment::plat
