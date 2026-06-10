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

extern "C" int augment_plat_selftest_target(int x);
extern "C" int augment_plat_selftest_replacement(int x);

namespace augment::plat {

uint64_t func_gap(void* target);
void     selftest_bind_orig(void* orig);

bool hook_install(void* target, void* replacement, void** out_original) {
    if (!target || func_gap(target) < 16) return false;
    return DobbyHook(target, replacement, out_original) == 0;
}

bool hook_remove(void* target) {
    return target && DobbyDestroy(target) == 0;
}

bool self_test(void) {
    volatile int arg = 5;
    int before = augment_plat_selftest_target(arg);
    void* out = nullptr;
    if (!hook_install(reinterpret_cast<void*>(augment_plat_selftest_target),
                      reinterpret_cast<void*>(augment_plat_selftest_replacement), &out)) {
        return false;
    }
    selftest_bind_orig(out);
    int hooked = augment_plat_selftest_target(arg);
    hook_remove(reinterpret_cast<void*>(augment_plat_selftest_target));
    int restored = augment_plat_selftest_target(arg);
    return hooked == before + 100 && restored == before;
}

} // namespace augment::plat
