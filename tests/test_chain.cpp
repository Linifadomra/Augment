#include "runtime/chain.hpp"
#include <cassert>
#include <cstdio>

// helpers
static augment::Entry make_entry(AugmentPhase phase, AugmentFn fn,
                                  void* userdata = nullptr,
                                  int priority = 0,
                                  const char* mod_id = "test_mod") {
    augment::Entry e{};
    e.phase    = phase;
    e.fn       = fn;
    e.userdata = userdata;
    e.priority = priority;
    e.mod_id   = mod_id;
    return e;
}

static AugmentCtx make_ctx(void* self = nullptr) {
    AugmentCtx ctx{};
    ctx.self = self;
    return ctx;
}

// tests
static void test_before_runs_before_original() {
    augment::Chain chain;
    chain.symbol = "Test::fn";

    bool before_ran = false;
    bool original_ran = false;

    chain.add(make_entry(AUGMENT_PHASE_BEFORE, [](AugmentCtx* ctx, void* ud) {
        *static_cast<bool*>(ud) = true;
    }, &before_ran));

    // simulate original via saved
    static bool* orig_flag = &original_ran;
    static bool* before_flag = &before_ran;
    chain.saved = reinterpret_cast<void*>(+[](void*) -> int {
        assert(*before_flag); // before must have run first
        *orig_flag = true;
        return 0;
    });

    auto ctx = make_ctx();
    chain.dispatch(ctx);

    assert(before_ran);
    assert(original_ran);
    std::printf("PASS test_before_runs_before_original\n");
}

static void test_after_always_runs() {
    augment::Chain chain;
    chain.symbol = "Test::fn";

    bool after_ran = false;

    chain.add(make_entry(AUGMENT_PHASE_BEFORE, [](AugmentCtx* ctx, void* ud) {
        ctx->cancelled = 1; // cancel before original
    }));

    chain.add(make_entry(AUGMENT_PHASE_AFTER, [](AugmentCtx* ctx, void* ud) {
        *static_cast<bool*>(ud) = true;
    }, &after_ran));

    auto ctx = make_ctx();
    chain.dispatch(ctx);

    assert(after_ran); // after must run even when cancelled
    std::printf("PASS test_after_always_runs\n");
}

static void test_replace_skips_original() {
    augment::Chain chain;
    chain.symbol = "Test::fn";

    bool original_ran = false;
    chain.saved = reinterpret_cast<void*>(+[](void*) -> int {
        // should never reach here
        assert(false);
        return 0;
    });

    chain.add(make_entry(AUGMENT_PHASE_REPLACE, [](AugmentCtx* ctx, void* ud) {
        // replace does nothing, just suppresses original
    }));

    auto ctx = make_ctx();
    chain.dispatch(ctx);

    assert(!original_ran);
    std::printf("PASS test_replace_skips_original\n");
}

static void test_priority_order() {
    augment::Chain chain;
    chain.symbol = "Test::fn";

    int order = 0;
    int first = -1, second = -1;

    struct Capture { int* order; int* out; };
    static Capture a{ &order, &first  };
    static Capture b{ &order, &second };

    chain.add(make_entry(AUGMENT_PHASE_BEFORE, [](AugmentCtx* ctx, void* ud) {
        auto* c = static_cast<Capture*>(ud);
        *c->out = (*c->order)++;
    }, &a, /*priority=*/5));

    chain.add(make_entry(AUGMENT_PHASE_BEFORE, [](AugmentCtx* ctx, void* ud) {
        auto* c = static_cast<Capture*>(ud);
        *c->out = (*c->order)++;
    }, &b, /*priority=*/10)); // higher priority, should run first

    auto ctx = make_ctx();
    chain.dispatch(ctx);

    assert(second == 0); // priority 10 ran first
    assert(first  == 1); // priority 5 ran second
    std::printf("PASS test_priority_order\n");
}

static void test_remove_mod() {
    augment::Chain chain;
    chain.symbol = "Test::fn";

    bool mod_a_ran = false;
    bool mod_b_ran = false;

    chain.add(make_entry(AUGMENT_PHASE_BEFORE, [](AugmentCtx* ctx, void* ud) {
        *static_cast<bool*>(ud) = true;
    }, &mod_a_ran, 0, "mod_a"));

    chain.add(make_entry(AUGMENT_PHASE_BEFORE, [](AugmentCtx* ctx, void* ud) {
        *static_cast<bool*>(ud) = true;
    }, &mod_b_ran, 0, "mod_b"));

    chain.remove_mod("mod_a");

    auto ctx = make_ctx();
    chain.dispatch(ctx);

    assert(!mod_a_ran);
    assert(mod_b_ran);
    std::printf("PASS test_remove_mod\n");
}

static void test_replace_count() {
    augment::Chain chain;
    chain.symbol = "Test::fn";

    assert(chain.replace_count() == 0);

    chain.add(make_entry(AUGMENT_PHASE_REPLACE, [](AugmentCtx*, void*) {}));
    assert(chain.replace_count() == 1);

    chain.add(make_entry(AUGMENT_PHASE_BEFORE, [](AugmentCtx*, void*) {}));
    assert(chain.replace_count() == 1);

    std::printf("PASS test_replace_count\n");
}

int main() {
    std::printf("--- chain tests ---\n");
    test_before_runs_before_original();
    test_after_always_runs();
    test_replace_skips_original();
    test_priority_order();
    test_remove_mod();
    test_replace_count();
    std::printf("--- all passed ---\n");
    return 0;
}