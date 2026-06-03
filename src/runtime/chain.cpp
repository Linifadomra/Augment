//    Augment Copyright (C) 2026 Liam
//
//    This program is free software: you can redistribute it and/or modify
//    it under the terms of the GNU General Public License as published by
//    the Free Software Foundation, either version 3 of the License, or
//    (at your option) any later version.
//
//    This program is distributed in the hope that it will be useful,
//    but WITHOUT ANY WARRANTY; without even the implied warranty of
//    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
//    GNU General Public License for more details.
//
//    You should have received a copy of the GNU General Public License
//    along with this program.  If not, see <https://www.gnu.org/licenses/>.

#include "runtime/chain.hpp"
#include <algorithm>

namespace augment {

void Chain::add(const Entry& e) {
    entries.push_back(e);
    dirty = true;
}

void Chain::remove_augment(const std::string& augment_id) {
    auto prev = entries.size();
    entries.erase(
        std::remove_if(entries.begin(), entries.end(),
            [&](const Entry& e) { return e.augment_id == augment_id; }),
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

bool Chain::run_before(AugmentCtx& ctx) {
    sort();

    for (auto& e : entries) {
        if (e.phase != AUGMENT_PHASE_BEFORE) continue;
        e.fn(&ctx, e.userdata);
        if (ctx.cancelled) return false;
    }

    for (auto& e : entries) {
        if (e.phase != AUGMENT_PHASE_REPLACE) continue;
        e.fn(&ctx, e.userdata);
        return false;
    }

    return true;
}

void Chain::run_after(AugmentCtx& ctx) {
    for (auto& e : entries) {
        if (e.phase != AUGMENT_PHASE_AFTER) continue;
        e.fn(&ctx, e.userdata);
    }
}

int Chain::dispatch(AugmentCtx& ctx) {
    if (run_before(ctx) && saved) {
        using OrigFn = int(*)(void*);
        auto orig = reinterpret_cast<OrigFn>(saved);
        int r = orig(ctx.self);
        ctx.ret = reinterpret_cast<void*>(static_cast<uintptr_t>(r));
    }
    run_after(ctx);
    return static_cast<int>(reinterpret_cast<uintptr_t>(ctx.ret));
}

int Chain::replace_count() const {
    int n = 0;
    for (const auto& e : entries)
        if (e.phase == AUGMENT_PHASE_REPLACE) ++n;
    return n;
}

} // namespace augment