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

#ifndef AUGMENT_CONFLICT_HPP
#define AUGMENT_CONFLICT_HPP

#include "chain.hpp"

namespace augment {

enum class ConflictClass {
    None    = 1, // composable, no issue
    Order   = 2, // order-sensitive, priority resolves, warn
    Hard    = 3, // structural incompatibility, reject
};

struct ConflictResult {
    ConflictClass cls     = ConflictClass::None;
    const char*   reason  = nullptr; // static string, never null on Order/Hard
};

// Check whether incoming entry is compatible with the existing chain.
// Returns the worst conflict found.
ConflictResult conflict_check(const Chain& chain, const Entry& incoming);

} // namespace augment

#endif /* AUGMENT_CONFLICT_HPP */