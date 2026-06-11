#include "game.hpp"

void Entity::die() { dead = true; }

float Combat::calculateDamage(float base, float multiplier) {
    return base * multiplier;
}

void Combat::applyDamage(Entity& target, float amount) {
    target.health -= amount;
    if (target.health <= 0.f) target.die();
}  