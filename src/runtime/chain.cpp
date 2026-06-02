#include "runtime/chain.hpp"
#include <algorithm>

namespace augment {

void Chain::add(const Entry& e) {
    entries.push_back(e);
    dirty = true;
}

void Chain::remove_mod(const std::string& mod_id) {
    auto prev = entries.size();
    entries.erase(
        std::remove_if(entries.begin(), entries.end(),
            [&](const Entry& e) { return e.mod_id == mod_id; }),
        entries.end()
    );
    if (entries.size() != prev) dirty = true;
}

void Chain::sort() {
    if (!dirty) return;
    std::stable_sort(entries.begin(), entries.end(),
        [](const Entry& a, const Entry& b) { return a.priority > b.priority; });
    dirty = false;
}

int Chain::dispatch(AugmentCtx& ctx) {
    sort();

    for (auto& e : entries) {
        if (e.phase != AUGMENT_PHASE_BEFORE) continue;
        e.fn(&ctx, e.userdata);
        if (ctx.cancelled) goto after;
    }

    for (auto& e : entries) {
        if (e.phase != AUGMENT_PHASE_REPLACE) continue;
        e.fn(&ctx, e.userdata);
        goto after;
    }

    if (saved) {
        using OrigFn = int(*)(void*);
        ctx.user = saved;
        auto orig = reinterpret_cast<OrigFn>(saved);
        int r = orig(ctx.self);
        ctx.ret = reinterpret_cast<void*>(static_cast<uintptr_t>(r));
    }

after:
    for (auto& e : entries) {
        if (e.phase != AUGMENT_PHASE_AFTER) continue;
        e.fn(&ctx, e.userdata);
    }

    return static_cast<int>(reinterpret_cast<uintptr_t>(ctx.ret));
}

int Chain::replace_count() const {
    int n = 0;
    for (const auto& e : entries)
        if (e.phase == AUGMENT_PHASE_REPLACE) ++n;
    return n;
}

} // namespace augment