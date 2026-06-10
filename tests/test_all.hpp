#pragma once

struct Entity {
    float health = 100.f;
    bool  dead   = false;
    void die();
};

class Combat {
public:
    float calculateDamage(float base, float multiplier);
    void applyDamage(Entity& target, float amount);
};