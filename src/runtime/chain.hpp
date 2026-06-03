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
    std::string     augment_id;
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
    void remove_augment(const std::string& augment_id);
    void sort();

    int dispatch(AugmentCtx& ctx);

    int replace_count() const;
    bool empty() const { return entries.empty(); }
};

} // namespace augment

#endif /* AUGMENT_CHAIN_HPP */