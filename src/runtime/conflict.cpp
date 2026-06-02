#include "runtime/conflict.hpp"
#include <cstring>

namespace augment {

namespace {

bool domains_intersect(const char* const* a, int na,
                       const char* const* b, int nb) {
    for (int i = 0; i < na; ++i)
        for (int j = 0; j < nb; ++j)
            if (a[i] && b[j] && std::strcmp(a[i], b[j]) == 0)
                return true;
    return false;
}

bool has_writes(const AugmentContract& c) { return c.n_writes > 0; }
bool has_reads (const AugmentContract& c) { return c.n_reads  > 0; }

} // anonymous namespace

ConflictResult conflict_check(const Chain& chain, const Entry& incoming) {
    ConflictResult worst{};

    for (const auto& e : chain.entries) {

        // Class 3
        if (incoming.phase == AUGMENT_PHASE_REPLACE &&
            e.phase        == AUGMENT_PHASE_REPLACE) {
            return ConflictResult{
                ConflictClass::Hard,
                "two replace hooks on the same symbol are structurally incompatible"
            };
        }

        // Contract checks
        const bool incoming_writes = has_writes(incoming.contract);
        const bool existing_writes = has_writes(e.contract);
        const bool incoming_reads  = has_reads (incoming.contract);

        // write vs write
        if (incoming_writes && existing_writes) {
            if (domains_intersect(
                    incoming.contract.writes, incoming.contract.n_writes,
                    e.contract.writes,        e.contract.n_writes)) {

                if (incoming.priority == e.priority) {
                    return ConflictResult{
                        ConflictClass::Hard,
                        "two hooks write the same domain at equal priority with no resolution"
                    };
                } else {
                    if (worst.cls < ConflictClass::Order) {
                        worst = ConflictResult{
                            ConflictClass::Order,
                            "two hooks write the same domain: execution order is priority-dependent"
                        };
                    }
                }
            }
        }

        // read vs write
        if (incoming_reads && existing_writes) {
            if (domains_intersect(
                    incoming.contract.reads,  incoming.contract.n_reads,
                    e.contract.writes,        e.contract.n_writes)) {

                if (incoming.priority == e.priority) {
                    if (worst.cls < ConflictClass::Order) {
                        worst = ConflictResult{
                            ConflictClass::Order,
                            "hook reads a domain written by another hook at equal priority: result depends on load order"
                        };
                    }
                }
            }
        }

        // write vs read (incoming writes what existing reads)
        if (incoming_writes && has_reads(e.contract)) {
            if (domains_intersect(
                    incoming.contract.writes, incoming.contract.n_writes,
                    e.contract.reads,         e.contract.n_reads)) {

                if (incoming.priority == e.priority) {
                    if (worst.cls < ConflictClass::Order) {
                        worst = ConflictResult{
                            ConflictClass::Order,
                            "hook writes a domain read by another hook at equal priority: result depends on load order"
                        };
                    }
                }
            }
        }
    }

    return worst;
}

} // namespace augment