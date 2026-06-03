// fixtures/refs_and_ptrs.hpp
// Exercises the ref->pointer and pointer passthrough logic in ctx_field_type().
#pragma once

struct Entity {
    float health;
    bool  dead;
};

class Combat {
public:
    void applyDamage(Entity& target, float amount);
    void applyDamagePtr(Entity* target, float amount);
    void applyDamageConst(const Entity& target, float amount) const;
};