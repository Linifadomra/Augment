// fixtures/mixed_classes.hpp
// Two classes used to test --symbol-prefix filtering.
// Walking with --symbol-prefix Combat:: must exclude Audio entirely.
#pragma once

class Combat {
public:
    float calculateDamage(float base, float multiplier);
    void  applyDamage(float amount);
};

class Audio {
public:
    void playSound(int id);
    void stopAll();
};