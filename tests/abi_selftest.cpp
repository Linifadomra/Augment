#include "augment/augment.hpp"
#include "augment/platform_compat.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>

struct Vec3 { float x, y, z; };

extern "C" AUGMENT_NOINLINE AUGMENT_EXPORT float abitest_scale(float a, int n) { 
    volatile float r = a * (float)n; 
    return r; 
}

AUGMENT_NOINLINE AUGMENT_EXPORT Vec3 abitest_make(Vec3 base, float k) { 
    return { base.x + k, base.y + k, base.z + k }; 
}

struct Obj {
    int life;
    AUGMENT_NOINLINE AUGMENT_EXPORT
    int hit(int dmg) { 
        volatile int r = life - dmg; 
        return r; 
    }
};

static void before_scale(AugmentCtx* ctx, void*) {
    *(int*)ctx->args[1] += 1;
}
static void before_make(AugmentCtx* ctx, void*) {
    ((Vec3*)ctx->args[0])->x += 100.f;
}
static void before_hit(AugmentCtx* ctx, void*) {
    ((Obj*)ctx->self)->life = 50;
}

int main() {
    { const char* a[2] = {"f32","i32"};
      augment_register_signature("abitest_scale", 0, "f32", a, 2);
      AugmentRegOpts o{}; o.augment_id = "s";
      augment_register("abitest_scale", AUGMENT_PHASE_BEFORE, before_scale, nullptr, &o); }
    {
        const char* mem[3] = {"f32", "f32", "f32"};
        augment_register_struct("Vec3", mem, 3);
        const char* a[2] = {"struct:Vec3", "f32"};
        augment_register_signature("abitest_make", 0, "struct:Vec3", a, 2);
        AugmentRegOpts o{}; o.augment_id = "m";
        augment_register("abitest_make", AUGMENT_PHASE_BEFORE, before_make, nullptr, &o);
    }
    { const char* a[1] = {"i32"};
      augment_register_signature("Obj::hit", 1, "i32", a, 1);
      AugmentRegOpts o{}; o.augment_id = "h";
      augment_register("Obj::hit", AUGMENT_PHASE_BEFORE, before_hit, nullptr, &o); }

    augment_install_all();

    int ok = 1;
    float s = abitest_scale(2.0f, 3);
    if (s != 8.0f) { std::printf("FAIL scale: %f\n", s); ok = 0; }

    Vec3 v = abitest_make({1,2,3}, 10);
    if (v.x != 111.f || v.y != 12.f) { std::printf("FAIL make: %f %f\n", v.x, v.y); ok = 0; }

    Obj obj{200};
    int r = obj.hit(10);
    if (r != 40) { std::printf("FAIL hit: %d\n", r); ok = 0; }

    std::printf("%s abi_selftest\n", ok ? "PASS" : "FAIL");
    return ok ? 0 : 1;
}
