// fixtures/simple.hpp
// Basic member functions: value params, mixed return types.
#pragma once

class Combat {
public:
    float calculateDamage(float base, float multiplier);
    void  applyDamage(float amount);
    int   countHits();
};