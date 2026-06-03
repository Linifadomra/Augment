// fixtures/void_return.hpp
// Void return functions: __return field must be omitted from ctx struct.
#pragma once

class Effects {
public:
    void applyBurn(float duration);
    void clearAllEffects();
    void applyPoison(float damage, float duration);
};