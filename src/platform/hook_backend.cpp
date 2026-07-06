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

#include <cstdint>
#include <cstring>

#if defined(_WIN32)
#include <MinHook.h>
#else
#include <dobby.h>
#endif

extern "C" int augment_plat_selftest_target(int x);
extern "C" int augment_plat_selftest_replacement(int x);

namespace augment::plat {
void selftest_bind_orig(void* orig);

#if defined(_WIN32)

namespace {
    bool mh_initialized = false;
}

bool hook_install(void* target, void* replacement, void** out_original) {
    if (!target) return false;
    if (!mh_initialized) {
        if (MH_Initialize() != MH_OK) return false;
        mh_initialized = true;
    }
    if (MH_CreateHook(target, replacement, out_original) != MH_OK) return false;
    return MH_EnableHook(target) == MH_OK;
}

bool hook_remove(void* target) {
    if (!target) return false;
    MH_DisableHook(target);
    return MH_RemoveHook(target) == MH_OK;
}

#else

uint64_t func_gap(void* target);

bool hook_install(void* target, void* replacement, void** out_original) {
    if (!target || func_gap(target) < 16) return false;
    return DobbyHook(target, replacement, out_original) == 0;
}

bool hook_remove(void* target) {
    return target && DobbyDestroy(target) == 0;
}

#endif

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
