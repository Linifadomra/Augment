// Augment Copyright (C) 2026 Liam
//
// Licensed under the MIT License.
// See LICENSE for details.

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