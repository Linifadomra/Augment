// test_all.cpp
// Regression test for augment pipeline behavior.

#include "augment/augment.hpp"
#include "test_all.hpp"

#include <cstdio>
#include <cassert>

void Entity::die() { dead = true; }

float Combat::calculateDamage(float base, float multiplier) {
    return base * multiplier;
}

void Combat::applyDamage(Entity& target, float amount) {
    target.health -= amount;
    if (target.health <= 0.f) target.die();
}

Combat gCombat;

static void damage_boost_hook(AugmentCtx* ctx, void* /*userdata*/) {
    float* base = static_cast<float*>(ctx->args[0]);
    *base *= 1.5f;
}

static void apply_patch() {
    AugmentRegOpts opts{};
    opts.priority   = 10;
    opts.tag        = "combat";
    opts.augment_id = "damage_boost";

    int ok = augment_register(
        "Combat::calculateDamage",
        AUGMENT_PHASE_BEFORE,
        damage_boost_hook,
        nullptr,
        &opts
    );

    assert(ok && "augment_register failed");
}

static float doAction() {
    float base = 40.0f;
    float mul  = 2.0f;
    return gCombat.calculateDamage(base, mul);
}

static void test_vanilla_behavior() {
    float result = doAction();
    assert(result == 80.0f);
}

static void test_patched_behavior() {
    apply_patch();
    augment_install_all();

    float result = doAction();
    assert(result == 120.0f);
}

static void test_chain_inspection() {
    const char* info = augment_inspect("Combat::calculateDamage");
    assert(info != nullptr);
}

static void test_unpatch_restore() {
    augment_unregister("damage_boost");

    float result = doAction();
    assert(result == 80.0f);
}

int main() {
    test_vanilla_behavior();
    test_patched_behavior();
    test_chain_inspection();
    test_unpatch_restore();

    augment_clear();
    return 0;
}