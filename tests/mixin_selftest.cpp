// mixin_selftest.cpp

#include "augment/augment.hpp"
#include <cstdio>

namespace augtest {
__attribute__((noinline)) float scale(float base, float mul);
}

float augtest::scale(float base, float mul) {
    volatile float b = base;
    volatile float m = mul;
    return b * m;
}

// Hand-written stand-in for what walk.py emits for augtest::scale.
static float dispatch_scale(float base, float mul) {
    void* __args[2] = { (void*)&base, (void*)&mul };
    float __ret{};
    AugmentCtx __actx = { nullptr, __args, (void*)&__ret, 0, nullptr };

    void* __saved = augment_before("augtest::scale", &__actx);
    if (__saved)
        __ret = reinterpret_cast<float(*)(float, float)>(__saved)(base, mul);
    augment_after("augtest::scale", &__actx);
    return __ret;
}

static void boost(AugmentCtx* ctx, void*) {
    float* base = static_cast<float*>(ctx->args[0]);
    *base *= 1.5f;
}

int main() {
    float baseline = augtest::scale(40.0f, 2.0f);   // 80

    augment_register_ptr("augtest::scale", reinterpret_cast<void*>(&dispatch_scale));

    AugmentRegOpts opts{};
    opts.augment_id = "boost";
    int ok = augment_register("augtest::scale", AUGMENT_PHASE_BEFORE, boost, nullptr, &opts);
    augment_install_all();

    float hooked = augtest::scale(40.0f, 2.0f);     // (40 * 1.5) * 2 = 120

    int fails = 0;
    if (!ok)               { std::printf("FAIL register\n");                     ++fails; }
    if (baseline != 80.0f) { std::printf("FAIL baseline %.1f\n", baseline);      ++fails; }
    if (hooked != 120.0f)  { std::printf("FAIL hooked %.1f (want 120)\n", hooked); ++fails; }

    std::printf("baseline=%.1f hooked=%.1f\n", baseline, hooked);
    std::printf("%s\n", fails == 0 ? "mixin selftest PASSED" : "mixin selftest FAILED");
    return fails;
}
