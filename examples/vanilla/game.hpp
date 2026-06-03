#pragma once

#define HOOKABLE __attribute__((visibility("default")))

struct Entity {
    float health = 100.f;
    bool  dead   = false;
    HOOKABLE void die();
};

class Combat {
public:
    HOOKABLE float calculateDamage(float base, float multiplier);
    HOOKABLE void applyDamage(Entity& target, float amount);
};