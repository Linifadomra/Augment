#pragma once

#ifndef AUGMENT_CHAIN_HPP
#define AUGMENT_CHAIN_HPP

#include "augment/augment.hpp"
#include <string>
#include <vector>

namespace augment {

struct Entry {
    AugmentPhase    phase;
    AugmentFn       fn;
    void*           userdata;
    int             priority;
    std::string     tag;
    std::string     mod_id;
    AugmentContract contract;
};

struct Chain {
    std::string        symbol;
    std::vector<Entry> entries;
    void*              saved    = nullptr;
    bool               dirty    = false;
    bool               installed = false;
    int                tier     = 0;

    void add(const Entry& e);
    void remove_mod(const std::string& mod_id);
    void sort();

    int dispatch(AugmentCtx& ctx);

    int replace_count() const;
    bool empty() const { return entries.empty(); }
};

} // namespace augment

#endif /* AUGMENT_CHAIN_HPP */