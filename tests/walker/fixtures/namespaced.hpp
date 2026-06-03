// fixtures/namespaced.hpp
// Exercises qualified_name and ctx_struct_name.
#pragma once

namespace Game {
namespace Combat {

class System {
public:
    float calculateDamage(float base, float multiplier);
    void  applyDamage(float amount);
};

} // namespace Combat
} // namespace Game
