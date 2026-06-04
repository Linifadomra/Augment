#include "augment/augment.hpp"

#include <cstdio>

extern "C" __attribute__((noinline, visibility("default")))
int augment_dyntest(int a, float b) {
    volatile int   x = a;
    volatile float y = b;
    return x + (int)y;
}

static void before_hook(AugmentCtx* ctx, void*) {
    *static_cast<int*>(ctx->args[0]) += 10;
}

int main() {
    int base = augment_dyntest(5, 2.0f);

    const char* atypes[2] = { "i32", "f32" };
    augment_register_signature("augment_dyntest", 0, "i32", atypes, 2);

    AugmentRegOpts opts{};
    opts.augment_id = "dyntest";
    augment_register("augment_dyntest", AUGMENT_PHASE_BEFORE, before_hook, nullptr, &opts);

    augment_install_all();

    int hooked = augment_dyntest(5, 2.0f);
    std::printf("dynamic trampoline (registry path): base=%d hooked=%d  %s\n",
                base, hooked, hooked == 17 ? "PASS" : "FAIL");
    return hooked == 17 ? 0 : 1;
}
