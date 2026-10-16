#include "augment/augment.hpp"
#include <cassert>
#include <stdio.h>

struct Entity {
    float satiety  = 100.0f;
    bool  starving = false;
    void yelp() { printf("I'm so hungry! :(\n"); } 
};

void eatFood(Entity& target, float amount) {
    target.satiety += amount;
    target.starving = target.satiety < 50.0f;
    if (target.starving) target.yelp();
}

void burnCalories(Entity& target, float amount) {
    target.satiety -= amount;
    target.starving = target.satiety < 50.0f;
    if (target.starving) target.yelp();
}

struct REntity {
    float _f1  = 100.0f;
    bool  _b1 = false;
    void yelp() { printf("I'm so hungry! :(\n"); } 
};

void hook_eat_food(REntity& target, float amount) {
    (void)amount;
    target._f1 += 100.0f;
}

int main() {
    Entity person{};
    burnCalories(person, 50.0f);
    assert(person.satiety == 50.0f && "Original function does not behave correctly: (expected 50.0f)");
    augment_hook_ptr(reinterpret_cast<void*>(&eatFood), reinterpret_cast<void*>(&hook_eat_food), nullptr);
    eatFood(person, 50.0f);
    assert(person.satiety == 150.0f && "Hooked function does not behave correctly: (expected 150.0f)");
}
