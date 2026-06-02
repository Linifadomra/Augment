#include "runtime/conflict.hpp"
#include <cassert>
#include <cstdio>

// helpers
static void noop_fn(AugmentCtx*, void*) {}

static augment::Entry make_entry(AugmentPhase phase,
                                  int priority = 0,
                                  const char* mod_id = "mod_a",
                                  AugmentContract contract = {}) {
    augment::Entry e{};
    e.phase    = phase;
    e.fn       = noop_fn;
    e.priority = priority;
    e.mod_id   = mod_id;
    e.contract = contract;
    return e;
}

static augment::Chain make_chain(std::initializer_list<augment::Entry> entries) {
    augment::Chain c;
    c.symbol = "Test::fn";
    for (auto& e : entries) c.add(e);
    return c;
}

// tests
static void test_no_conflict_composable() {
    // two before hooks, no contracts, should be class 1
    auto chain = make_chain({ make_entry(AUGMENT_PHASE_BEFORE, 0, "mod_a") });
    auto result = augment::conflict_check(chain, make_entry(AUGMENT_PHASE_BEFORE, 0, "mod_b"));
    assert(result.cls == augment::ConflictClass::None);
    std::printf("PASS test_no_conflict_composable\n");
}

static void test_replace_vs_replace_hard() {
    auto chain = make_chain({ make_entry(AUGMENT_PHASE_REPLACE, 0, "mod_a") });
    auto result = augment::conflict_check(chain, make_entry(AUGMENT_PHASE_REPLACE, 0, "mod_b"));
    assert(result.cls == augment::ConflictClass::Hard);
    assert(result.reason != nullptr);
    std::printf("PASS test_replace_vs_replace_hard\n");
}

static void test_write_write_equal_priority_hard() {
    static const char* w[] = { "health" };
    AugmentContract contract{ nullptr, 0, nullptr, 0, w, 1 };

    auto chain = make_chain({ make_entry(AUGMENT_PHASE_BEFORE, 5, "mod_a", contract) });
    auto result = augment::conflict_check(chain, make_entry(AUGMENT_PHASE_BEFORE, 5, "mod_b", contract));
    assert(result.cls == augment::ConflictClass::Hard);
    std::printf("PASS test_write_write_equal_priority_hard\n");
}

static void test_write_write_different_priority_order() {
    static const char* w[] = { "health" };
    AugmentContract contract{ nullptr, 0, nullptr, 0, w, 1 };

    auto chain = make_chain({ make_entry(AUGMENT_PHASE_BEFORE, 5,  "mod_a", contract) });
    auto result = augment::conflict_check(chain, make_entry(AUGMENT_PHASE_BEFORE, 10, "mod_b", contract));
    assert(result.cls == augment::ConflictClass::Order);
    std::printf("PASS test_write_write_different_priority_order\n");
}

static void test_read_write_equal_priority_order() {
    static const char* w[] = { "health" };
    static const char* r[] = { "health" };
    AugmentContract writer{ nullptr, 0, nullptr, 0, w, 1 };
    AugmentContract reader{ nullptr, 0, r, 1,    nullptr, 0 };

    auto chain = make_chain({ make_entry(AUGMENT_PHASE_BEFORE, 5, "mod_a", writer) });
    auto result = augment::conflict_check(chain, make_entry(AUGMENT_PHASE_BEFORE, 5, "mod_b", reader));
    assert(result.cls == augment::ConflictClass::Order);
    std::printf("PASS test_read_write_equal_priority_order\n");
}

static void test_read_write_different_priority_none() {
    // different priority resolves ordering, should be silent
    static const char* w[] = { "health" };
    static const char* r[] = { "health" };
    AugmentContract writer{ nullptr, 0, nullptr, 0, w, 1 };
    AugmentContract reader{ nullptr, 0, r, 1,    nullptr, 0 };

    auto chain = make_chain({ make_entry(AUGMENT_PHASE_BEFORE, 10, "mod_a", writer) });
    auto result = augment::conflict_check(chain, make_entry(AUGMENT_PHASE_BEFORE, 5,  "mod_b", reader));
    assert(result.cls == augment::ConflictClass::None);
    std::printf("PASS test_read_write_different_priority_none\n");
}

static void test_no_contract_no_conflict() {
    // mods with no contract declared should pass through cleanly
    auto chain = make_chain({
        make_entry(AUGMENT_PHASE_BEFORE, 0, "mod_a"),
        make_entry(AUGMENT_PHASE_AFTER,  0, "mod_b"),
    });
    auto result = augment::conflict_check(chain, make_entry(AUGMENT_PHASE_BEFORE, 0, "mod_c"));
    assert(result.cls == augment::ConflictClass::None);
    std::printf("PASS test_no_contract_no_conflict\n");
}

static void test_disjoint_domains_no_conflict() {
    // two mods writing different domains, no conflict
    static const char* w_a[] = { "health" };
    static const char* w_b[] = { "stamina" };
    AugmentContract ca{ nullptr, 0, nullptr, 0, w_a, 1 };
    AugmentContract cb{ nullptr, 0, nullptr, 0, w_b, 1 };

    auto chain = make_chain({ make_entry(AUGMENT_PHASE_BEFORE, 5, "mod_a", ca) });
    auto result = augment::conflict_check(chain, make_entry(AUGMENT_PHASE_BEFORE, 5, "mod_b", cb));
    assert(result.cls == augment::ConflictClass::None);
    std::printf("PASS test_disjoint_domains_no_conflict\n");
}

static void test_write_read_incoming_writes_existing_reads_order() {
    // incoming writes what existing reads at equal priority
    static const char* w[] = { "position" };
    static const char* r[] = { "position" };
    AugmentContract writer{ nullptr, 0, nullptr, 0, w, 1 };
    AugmentContract reader{ nullptr, 0, r, 1,    nullptr, 0 };

    auto chain = make_chain({ make_entry(AUGMENT_PHASE_BEFORE, 5, "mod_a", reader) });
    auto result = augment::conflict_check(chain, make_entry(AUGMENT_PHASE_BEFORE, 5, "mod_b", writer));
    assert(result.cls == augment::ConflictClass::Order);
    std::printf("PASS test_write_read_incoming_writes_existing_reads_order\n");
}

static void test_replace_vs_before_no_conflict() {
    // replace vs before with no contract, not a structural conflict
    auto chain = make_chain({ make_entry(AUGMENT_PHASE_BEFORE, 0, "mod_a") });
    auto result = augment::conflict_check(chain, make_entry(AUGMENT_PHASE_REPLACE, 0, "mod_b"));
    assert(result.cls == augment::ConflictClass::None);
    std::printf("PASS test_replace_vs_before_no_conflict\n");
}

int main() {
    std::printf("--- conflict tests ---\n");
    test_no_conflict_composable();
    test_replace_vs_replace_hard();
    test_write_write_equal_priority_hard();
    test_write_write_different_priority_order();
    test_read_write_equal_priority_order();
    test_read_write_different_priority_none();
    test_no_contract_no_conflict();
    test_disjoint_domains_no_conflict();
    test_write_read_incoming_writes_existing_reads_order();
    test_replace_vs_before_no_conflict();
    std::printf("--- all passed ---\n");
    return 0;
}