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

} // namespace augment::plat
