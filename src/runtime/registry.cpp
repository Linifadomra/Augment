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

#include "runtime/registry.hpp"
#include "runtime/conflict.hpp"
#include "augment/manifest_internal.hpp"
#include "augment/augment.hpp"

#include "internal.hpp"

#include <cstdarg>
#include <vector>
#include <mutex>
#include <cstdio>

static AugmentLogFn s_logger = nullptr;

void augment_set_logger(AugmentLogFn fn) {
    s_logger = fn;
}

void augment_log(const char* tag, const char* fmt, ...) {
    char buf[512];
    va_list args;
    va_start(args, fmt);
    vsnprintf(buf, sizeof(buf), fmt, args);
    va_end(args);
    if (s_logger) s_logger(tag, buf);
    else fprintf(stderr, "[%s] %s\n", tag, buf);
}

namespace augment::plat {
    bool hook_install  (void* target, void* replacement, void** out_original);
    bool hook_remove   (void* target);
    void* sym_resolve  (const char* symbol);
    bool self_test     (void);
    intptr_t image_slide();
}

namespace augment::manifest {
    class Reader;
    Reader& global_reader();
}

namespace augment {

Registry& Registry::instance() {
    static Registry s_instance;
    return s_instance;
}

Chain* Registry::get_or_create_chain(const std::string& symbol) {
    auto it = m_chains.find(symbol);
    if (it != m_chains.end()) return &it->second;
    Chain& c = m_chains[symbol];
    c.symbol = symbol;
    return &c;
}

Chain* Registry::get_chain(const std::string& symbol) {
    auto it = m_chains.find(symbol);
    return it != m_chains.end() ? &it->second : nullptr;
}

// PUBLIC API

bool Registry::register_augment(const char* symbol, AugmentPhase phase,
                              AugmentFn fn, void* userdata,
                              const AugmentRegOpts* opts) {
    if (!symbol || !fn) return false;

    Entry e{};
    e.phase    = phase;
    e.fn       = fn;
    e.userdata = userdata;

    if (opts) {
        e.priority = opts->priority;
        e.tag      = opts->tag    ? opts->tag    : "";
        e.augment_id   = opts->augment_id ? opts->augment_id : "";
        e.contract = opts->contract;
    }

    std::unique_lock lock(m_mutex);
    Chain* chain = get_or_create_chain(symbol);

    ConflictResult cr = conflict_check(*chain, e);

    if (cr.cls == ConflictClass::Hard) {
        augment_log("augment", "CONFLICT (class 3) augment='%s' symbol='%s': %s",
                    e.augment_id.c_str(), symbol, cr.reason);
        return false;
    }

    if (cr.cls == ConflictClass::Order) {
        augment_log("augment", "WARNING (class 2) augment='%s' symbol='%s': %s",
                    e.augment_id.c_str(), symbol, cr.reason);
    }

    chain->add(e);

    if (m_installed && !chain->installed) {
        std::string sym = symbol;
        lock.unlock();
        install_chain(sym, *chain);
    }

    return true;
}

void Registry::register_ptr(const char* symbol, void* ptr) {
    if (!symbol || !ptr) return;
    std::unique_lock lock(m_mutex);
    Chain* chain = get_or_create_chain(symbol);
    chain->target_ptr = ptr;
}

void* Registry::resolve_target(const std::string& symbol) {
    if (void* p = plat::sym_resolve(symbol.c_str()))
        return p;

    uint64_t rva = manifest::global_reader().rva_of(symbol.c_str());
    if (rva) {
        if (void* p = reinterpret_cast<void*>(static_cast<uintptr_t>(rva + plat::image_slide())))
            return p;
    }

    augment::manifest::Reader& reader = manifest::global_reader();
    augment::manifest::FuncView fv{};
    const uint32_t overloadCount = reader.func_count(symbol.c_str());
    for (uint32_t i = 0; i < overloadCount; ++i) {
        if (!reader.func_at(symbol.c_str(), i, &fv) || !fv.mangled || !*fv.mangled) continue;
        if (void* p = plat::sym_resolve(fv.mangled))
            return p;
    }

    if (reader.func_by_mangled(symbol.c_str(), &fv) && fv.mangled && *fv.mangled) {
        if (void* p = plat::sym_resolve(fv.mangled))
            return p;
    }

    return nullptr;
}

bool Registry::install_chain(const std::string& symbol, Chain& chain) {
    void* repl = chain.target_ptr ? chain.target_ptr : augment_make_closure(symbol.c_str());
    if (!repl) {
        augment_log("augment", "no trampoline or signature for '%s' (not in manifest?)", symbol.c_str());
        return false;
    }

    void* target = resolve_target(symbol);
    if (!target) {
        augment_log("augment", "sym_resolve failed for '%s'. (function inlined?)", symbol.c_str());
        return false;
    }

    void* orig = nullptr;
    if (!plat::hook_install(target, repl, &orig)) {
        augment_log("augment", "hook_install failed for '%s'", symbol.c_str());
        return false;
    }

    chain.saved     = orig;
    chain.installed = true;
    return true;
}

void Registry::unregister_augment(const char* augment_id) {
    if (!augment_id) return;
    std::string id = augment_id;

    std::unique_lock lock(m_mutex);
    for (auto it = m_chains.begin(); it != m_chains.end(); ) {
        Chain& c = it->second;
        c.remove_augment(id);
        if (c.empty()) {
            if (c.installed && c.saved) {
                plat::hook_remove(resolve_target(c.symbol));
                c.installed = false;
            }
            it = m_chains.erase(it);
        } else {
            ++it;
        }
    }
}

void Registry::install_all() {
    std::vector<std::pair<std::string, Chain*>> pending;
    {
        std::unique_lock lock(m_mutex);
        if (m_installed) return;
        m_installed = true;
        pending.reserve(m_chains.size());
        for (auto& [symbol, chain] : m_chains) {
            if (!chain.installed && !chain.empty())
                pending.emplace_back(symbol, &chain);
        }
    }
    for (auto& [symbol, chain] : pending)
        install_chain(symbol, *chain);
}

void Registry::clear() {
    std::unique_lock lock(m_mutex);
    for (auto& [symbol, chain] : m_chains) {
        if (chain.installed) {
            void* target = resolve_target(symbol);
            if (target) plat::hook_remove(target);
            chain.installed = false;
        }
    }
    m_chains.clear();
    m_installed = false;
}

bool Registry::dispatch(const char* symbol, AugmentCtx& ctx) {
    std::shared_lock lock(m_mutex);
    Chain* chain = get_chain(symbol);
    if (!chain) return false;
    chain->dispatch(ctx);
    return true;
}

void* Registry::before(const char* symbol, AugmentCtx& ctx) {
    std::shared_lock lock(m_mutex);
    Chain* chain = get_chain(symbol);
    if (!chain) return nullptr;
    return chain->run_before(ctx) ? chain->saved : nullptr;
}

void Registry::after(const char* symbol, AugmentCtx& ctx) {
    std::shared_lock lock(m_mutex);
    Chain* chain = get_chain(symbol);
    if (chain) chain->run_after(ctx);
}

bool Registry::enter(const char* symbol, AugmentCtx& ctx) {
    std::shared_lock lock(m_mutex);
    Chain* chain = get_chain(symbol);
    if (!chain) return true;
    return chain->run_before(ctx);
}

const char* Registry::inspect(const char* symbol) {
    std::shared_lock lock(m_mutex);
    m_inspect_buf.clear();

    if (!symbol) { m_inspect_buf = "[]"; return m_inspect_buf.c_str(); }

    Chain* chain = get_chain(symbol);
    if (!chain) { m_inspect_buf = "[]"; return m_inspect_buf.c_str(); }

    chain->sort();
    m_inspect_buf = "[";
    char buf[512];
    for (size_t i = 0; i < chain->entries.size(); ++i) {
        const Entry& e = chain->entries[i];
        const char* phase =
            e.phase == AUGMENT_PHASE_BEFORE  ? "before"  :
            e.phase == AUGMENT_PHASE_AFTER   ? "after"   : "replace";
        std::snprintf(buf, sizeof(buf),
            "%s{\"augment\":\"%s\",\"phase\":\"%s\",\"priority\":%d,\"tag\":\"%s\"}",
            i ? "," : "",
            e.augment_id.c_str(), phase, e.priority, e.tag.c_str());
        m_inspect_buf += buf;
    }
    m_inspect_buf += "]";
    return m_inspect_buf.c_str();
}

// C API

extern "C" {

void augment_invoke(const char* symbol, AugmentCtx* ctx) {
    augment::Registry::instance().dispatch(symbol, *ctx);
}

void* augment_before(const char* symbol, AugmentCtx* ctx) {
    return augment::Registry::instance().before(symbol, *ctx);
}

void augment_after(const char* symbol, AugmentCtx* ctx) {
    augment::Registry::instance().after(symbol, *ctx);
}

int augment_enter(const char* symbol, AugmentCtx* ctx) {
    return augment::Registry::instance().enter(symbol, *ctx) ? 1 : 0;
}

int augment_register(const char* symbol, AugmentPhase phase,
                     AugmentFn fn, void* userdata,
                     const AugmentRegOpts* opts) {
    return augment::Registry::instance().register_augment(symbol, phase, fn, userdata, opts) ? 1 : 0;
}

void augment_register_ptr(const char* symbol, void* ptr) {
    augment::Registry::instance().register_ptr(symbol, ptr);
}

void augment_unregister(const char* augment_id) {
    augment::Registry::instance().unregister_augment(augment_id);
}

void augment_install_all(void) {
    if (!augment::plat::self_test()) {
        augment_log("augment", "self-test FAILED: hooks will not fire");
        return;
    }
    augment::Registry::instance().install_all();
}

int augment_self_test(void) {
    return augment::plat::self_test() ? 1 : 0;
}

void augment_clear(void) {
    augment::Registry::instance().clear();
}

const char* augment_inspect(const char* symbol) {
    return augment::Registry::instance().inspect(symbol);
}

void* augment_resolve(const char* symbol) {
    return augment::Registry::instance().resolve_target(std::string(symbol));
}

} // extern "C"

} // namespace augment