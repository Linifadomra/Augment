// test_registry.cpp

#include "runtime/registry.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>

// helpers

static void noop_fn(AugmentCtx*, void*) {}

static AugmentRegOpts make_opts(const char* augment_id, int priority = 0,
                                 AugmentContract contract = {}) {
    AugmentRegOpts opts{};
    opts.augment_id   = augment_id;
    opts.priority = priority;
    opts.contract = contract;
    return opts;
}

// ensures each test starts with a clean registry
struct RegistryGuard {
    RegistryGuard()  { augment::Registry::instance().clear(); }
    ~RegistryGuard() { augment::Registry::instance().clear(); }
};

// tests

static void test_register_succeeds() {
    RegistryGuard g;
    auto opts = make_opts("mod_a");
    bool ok = augment::Registry::instance().register_augment(
        "Foo::bar", AUGMENT_PHASE_BEFORE, noop_fn, nullptr, &opts);
    assert(ok);
    std::printf("PASS test_register_succeeds\n");
}

static void test_register_null_symbol_fails() {
    RegistryGuard g;
    bool ok = augment::Registry::instance().register_augment(
        nullptr, AUGMENT_PHASE_BEFORE, noop_fn, nullptr, nullptr);
    assert(!ok);
    std::printf("PASS test_register_null_symbol_fails\n");
}

static void test_register_null_fn_fails() {
    RegistryGuard g;
    bool ok = augment::Registry::instance().register_augment(
        "Foo::bar", AUGMENT_PHASE_BEFORE, nullptr, nullptr, nullptr);
    assert(!ok);
    std::printf("PASS test_register_null_fn_fails\n");
}

static void test_replace_conflict_rejected() {
    RegistryGuard g;
    auto opts_a = make_opts("mod_a");
    auto opts_b = make_opts("mod_b");

    bool first = augment::Registry::instance().register_augment(
        "Foo::bar", AUGMENT_PHASE_REPLACE, noop_fn, nullptr, &opts_a);
    bool second = augment::Registry::instance().register_augment(
        "Foo::bar", AUGMENT_PHASE_REPLACE, noop_fn, nullptr, &opts_b);

    assert(first);
    assert(!second); // hard conflict, must be rejected
    std::printf("PASS test_replace_conflict_rejected\n");
}

static void test_write_conflict_equal_priority_rejected() {
    RegistryGuard g;
    static const char* w[] = { "health" };
    AugmentContract contract{ nullptr, 0, nullptr, 0, w, 1 };

    auto opts_a = make_opts("mod_a", 5, contract);
    auto opts_b = make_opts("mod_b", 5, contract);

    bool first = augment::Registry::instance().register_augment(
        "Foo::bar", AUGMENT_PHASE_BEFORE, noop_fn, nullptr, &opts_a);
    bool second = augment::Registry::instance().register_augment(
        "Foo::bar", AUGMENT_PHASE_BEFORE, noop_fn, nullptr, &opts_b);

    assert(first);
    assert(!second);
    std::printf("PASS test_write_conflict_equal_priority_rejected\n");
}

static void test_write_conflict_different_priority_allowed() {
    RegistryGuard g;
    static const char* w[] = { "health" };
    AugmentContract contract{ nullptr, 0, nullptr, 0, w, 1 };

    auto opts_a = make_opts("mod_a", 5,  contract);
    auto opts_b = make_opts("mod_b", 10, contract);

    bool first = augment::Registry::instance().register_augment(
        "Foo::bar", AUGMENT_PHASE_BEFORE, noop_fn, nullptr, &opts_a);
    bool second = augment::Registry::instance().register_augment(
        "Foo::bar", AUGMENT_PHASE_BEFORE, noop_fn, nullptr, &opts_b);

    assert(first);
    assert(second); // class 2, warns but allows
    std::printf("PASS test_write_conflict_different_priority_allowed\n");
}

static void test_unregister_augment_removes_entries() {
    RegistryGuard g;
    auto opts_a = make_opts("mod_a");
    auto opts_b = make_opts("mod_b");

    augment::Registry::instance().register_augment(
        "Foo::bar", AUGMENT_PHASE_BEFORE, noop_fn, nullptr, &opts_a);
    augment::Registry::instance().register_augment(
        "Foo::bar", AUGMENT_PHASE_AFTER, noop_fn, nullptr, &opts_b);

    augment::Registry::instance().unregister_augment("mod_a");

    // mod_b still registered, mod_a gone
    // inspect should only show mod_b
    const char* json = augment::Registry::instance().inspect("Foo::bar");
    assert(std::strstr(json, "mod_b") != nullptr);
    assert(std::strstr(json, "mod_a") == nullptr);
    std::printf("PASS test_unregister_augment_removes_entries\n");
}

static void test_unregister_all_mods_removes_chain() {
    RegistryGuard g;
    auto opts_a = make_opts("mod_a");

    augment::Registry::instance().register_augment(
        "Foo::bar", AUGMENT_PHASE_BEFORE, noop_fn, nullptr, &opts_a);

    augment::Registry::instance().unregister_augment("mod_a");

    // chain should be gone entirely
    const char* json = augment::Registry::instance().inspect("Foo::bar");
    assert(std::strcmp(json, "[]") == 0);
    std::printf("PASS test_unregister_all_mods_removes_chain\n");
}

static void test_inspect_unknown_symbol_returns_empty() {
    RegistryGuard g;
    const char* json = augment::Registry::instance().inspect("Does::notExist");
    assert(std::strcmp(json, "[]") == 0);
    std::printf("PASS test_inspect_unknown_symbol_returns_empty\n");
}

static void test_inspect_null_returns_empty() {
    RegistryGuard g;
    const char* json = augment::Registry::instance().inspect(nullptr);
    assert(std::strcmp(json, "[]") == 0);
    std::printf("PASS test_inspect_null_returns_empty\n");
}

static void test_inspect_contains_registered_mod() {
    RegistryGuard g;
    auto opts = make_opts("mod_a", 10);
    augment::Registry::instance().register_augment(
        "Foo::bar", AUGMENT_PHASE_BEFORE, noop_fn, nullptr, &opts);

    const char* json = augment::Registry::instance().inspect("Foo::bar");
    assert(std::strstr(json, "mod_a")  != nullptr);
    assert(std::strstr(json, "before") != nullptr);
    assert(std::strstr(json, "10")     != nullptr);
    std::printf("PASS test_inspect_contains_registered_mod\n");
}

static void test_dispatch_no_chain_returns_false() {
    RegistryGuard g;
    AugmentCtx ctx{};
    bool dispatched = augment::Registry::instance().dispatch("Does::notExist", ctx);
    assert(!dispatched);
    std::printf("PASS test_dispatch_no_chain_returns_false\n");
}

static void test_dispatch_fires_hook() {
    RegistryGuard g;
    bool fired = false;
    auto opts = make_opts("mod_a");

    augment::Registry::instance().register_augment(
        "Foo::bar", AUGMENT_PHASE_BEFORE,
        [](AugmentCtx*, void* ud) { *static_cast<bool*>(ud) = true; },
        &fired, &opts);

    AugmentCtx ctx{};
    bool dispatched = augment::Registry::instance().dispatch("Foo::bar", ctx);
    assert(dispatched);
    assert(fired);
    std::printf("PASS test_dispatch_fires_hook\n");
}

static void test_c_api_register_and_inspect() {
    RegistryGuard g;
    AugmentRegOpts opts{};
    opts.augment_id = "augment_id_c_api";

    int ok = augment_register("Foo::bar", AUGMENT_PHASE_AFTER, noop_fn, nullptr, &opts);
    assert(ok);

    const char* json = augment_inspect("Foo::bar");
    assert(std::strstr(json, "augment_id_c_api") != nullptr);
    assert(std::strstr(json, "after")     != nullptr);
    std::printf("PASS test_c_api_register_and_inspect\n");
}

static void test_c_api_unregister_augment() {
    RegistryGuard g;
    AugmentRegOpts opts{};
    opts.augment_id = "augment_c_api";

    augment_register("Foo::bar", AUGMENT_PHASE_BEFORE, noop_fn, nullptr, &opts);
    augment_unregister("augment_c_api");

    const char* json = augment_inspect("Foo::bar");
    assert(std::strcmp(json, "[]") == 0);
    std::printf("PASS test_c_api_unregister_augment\n");
}

int main() {
    std::printf("--- registry tests ---\n");
    test_register_succeeds();
    test_register_null_symbol_fails();
    test_register_null_fn_fails();
    test_replace_conflict_rejected();
    test_write_conflict_equal_priority_rejected();
    test_write_conflict_different_priority_allowed();
    test_unregister_augment_removes_entries();
    test_unregister_all_mods_removes_chain();
    test_inspect_unknown_symbol_returns_empty();
    test_inspect_null_returns_empty();
    test_inspect_contains_registered_mod();
    test_dispatch_no_chain_returns_false();
    test_dispatch_fires_hook();
    test_c_api_register_and_inspect();
    test_c_api_unregister_augment();
    std::printf("--- all passed ---\n");
    return 0;
}