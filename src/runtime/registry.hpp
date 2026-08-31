// Augment Copyright (C) 2026 Liam
//
// Licensed under the MIT License.
// See LICENSE for details.

#pragma once

#include "augment/augment.hpp"
#include "chain.hpp"

#include <shared_mutex>
#include <string>
#include <unordered_map>

namespace augment {

class Registry {
public:
    // Returns false and logs on hard conflict. Warns on order conflict.
    bool        register_augment(const char* symbol, AugmentPhase phase,
                              AugmentFn fn, void* userdata,
                              const AugmentRegOpts* opts);

    void        register_ptr(const char* symbol, void* ptr);

    void        unregister_augment(const char* augment_id);
    void        install_all();
    void        clear();
    const char* inspect(const char* symbol);

    // Called by the platform layer trampoline: dispatches the chain for symbol.
    // Returns 0 if no chain exists (caller should invoke original directly).
    bool        dispatch(const char* symbol, AugmentCtx& ctx);

    void*       before(const char* symbol, AugmentCtx& ctx);
    void        after(const char* symbol, AugmentCtx& ctx);
    bool        enter(const char* symbol, AugmentCtx& ctx);
    void*       resolve_target(const std::string& symbol);

    static Registry& instance();

private:
    Chain*      get_or_create_chain(const std::string& symbol); // call under unique_lock
    Chain*      get_chain(const std::string& symbol);           // call under any lock
    bool        install_chain(const std::string& symbol, Chain& chain); // call under unique_lock

    std::unordered_map<std::string, Chain> m_chains;
    mutable std::shared_mutex              m_mutex;
    bool                                   m_installed = false;

    // inspect() returns a pointer to this buffer; valid until next inspect() call
    std::string m_inspect_buf;
};

} // namespace augment