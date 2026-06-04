#include "augment/augment.hpp"
#include "vanilla/game.hpp"
#include <stdio.h>

// -- Patch: damage_boost --
//
// Intercepts Combat::calculateDamage(float base, float mul) in the BEFORE phase.
// Reads args[0] (base damage) and scales it by 1.5x before the original runs.
// The original function then receives the modified value and returns base*mul*1.5.

Combat gCombat;

static void damage_boost_hook(AugmentCtx* ctx, void* /*userdata*/) {
    float* base = static_cast<float*>(ctx->args[0]);
    *base *= 1.5f;
}

// -- Register patch --
static void apply_patch() {
    AugmentRegOpts opts{};
    opts.priority   = 10;
    opts.tag        = "combat";
    opts.augment_id = "damage_boost";

    int ok = augment_register(
        "Combat::calculateDamage", // symbol to hook
        AUGMENT_PHASE_BEFORE,       // run before the original
        damage_boost_hook,             // our callback
        nullptr,                 // no userdata needed
        &opts                        // patch options
    );

    if (!ok)
        fprintf(stderr, "augment_register failed\n");
}

float doAction() {
    float base = 40.0f;
    float mul  = 2.0f;
    return gCombat.calculateDamage(base, mul);
}

int main() {
    printf("--- Running game patch example ---\n");

    printf("---       Vanilla test         ---\n");
    printf("  Output: %.2f\n", doAction());         // 80.00

    printf("---      Applying patch        ---\n");
    apply_patch();
    augment_install_all();

    printf("---       Patched test         ---\n");
    printf("  Output: %.2f\n", doAction());         // 120.00  (40*1.5 * 2)

    printf("---     Inspecting chain       ---\n");
    printf("  %s\n", augment_inspect("Combat::calculateDamage"));

    printf("---     Removing patch         ---\n");
    augment_unregister("damage_boost");
    printf("  Output: %.2f\n", doAction());         // 80.00  (restored)

    augment_clear();
    return 0;
}