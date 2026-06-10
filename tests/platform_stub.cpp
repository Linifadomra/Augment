// platform_stub.cpp
// Minimal platform stub for registry tests.
// Satisfies the linker without any real hooking behavior.
#include <cstdint>
namespace augment::plat {
    bool  hook_install(void*, void*, void** out_original) {
        if (out_original) *out_original = nullptr;
        return true;
    }
    bool  hook_remove(void*) { return true; }
    void* sym_resolve(const char*) { return reinterpret_cast<void*>(0x1); }
    intptr_t image_slide() { return 0; }
}